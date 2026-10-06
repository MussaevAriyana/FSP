"""Модель синтетических кандидатов — основа демо-данных и валидации (docs/DOCUMENTATION.md, §6).

У кандидата есть скрытая «способность» θ (в единицах грейда: 0 = стажёр … 3 = senior).
Вероятность верного ответа на задание уровня L — логистическая функция от θ − b_L
(b_L = L − 1; θ специалиста грейда g = g + THETA_OFFSET, т.е. он уверенно решает уровень g+1) плюс угадывание
для заданий с выбором (1/4). Числовые ответы угадать нельзя.

ВАЖНО: это модель, а не реальные данные. Она проверяет, что *конвейер* (генерация → скоринг →
порог → категория) ведёт себя разумно при заданных допущениях; содержательную валидность
(что наши задания измеряют именно «грейд») нужно калибровать на реальных кандидатах и
экспертной разметке — см. §6.4 документации.
"""
import math
import random

K = 1.8          # крутизна: насколько резко растёт вероятность с ростом разрыва θ − сложность
THETA_SD = 0.35  # разброс способности внутри грейда
THETA_OFFSET = 1.2  # допущение-определение: «специалист грейда g» уверенно (≈85–90%) решает задания уровня g+1;
                    # без сдвига он решал бы их лишь в половине случаев и не проходил бы порог зачёта.
                    # Чувствительность результатов к этому допущению — validate.py, раздел G


def p_correct(theta: float, level: int, kind: str) -> float:
    p = 1.0 / (1.0 + math.exp(-K * (theta - (level - 1.0))))
    p = 0.97 * p + 0.01
    return 0.25 + 0.75 * p if kind == "choice" else p


def draw_theta(true_grade_idx: int, rng: random.Random) -> float:
    return true_grade_idx + THETA_OFFSET + rng.gauss(0, THETA_SD)


def simulate_answers(questions: list[dict], theta: float, rng: random.Random) -> dict:
    """Ответы кандидата со способностью theta: верный — с вероятностью p_correct, иначе неверный."""
    answers = {}
    for q in questions:
        ok = rng.random() < p_correct(theta, q["level"], q["kind"])
        if q["kind"] == "choice":
            answers[q["id"]] = q["answer"] if ok else rng.choice([i for i in range(4) if i != q["answer"]])
        else:
            answers[q["id"]] = q["answer"] if ok else q["answer"] + rng.choice([-3, -2, -1, 1, 2, 5, 10])
    return answers
