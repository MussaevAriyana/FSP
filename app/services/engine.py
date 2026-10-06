"""Движок тестирования: блюпринт, сборка уникального теста, проверка, выводы по грейду.

Сопоставимость сложности. Тест для грейда строится по фиксированному *блюпринту* — числу
заданий каждого уровня сложности (1–4). Все кандидаты одного грейда получают одинаковый профиль
сложности (одинаковый максимальный балл и одинаковое распределение уровней); различаются только
семейства (в пределах уровня) и случайные параметры. Вес задания = его уровню.

Зачёт: взвешенная доля ≥ PASS_THRESHOLD *и* не менее половины заданий «ядра» (уровня заявленного
грейда) решены верно — чтобы нельзя было набрать порог на лёгких заданиях.
"""
import random
import secrets
from collections import Counter, defaultdict
from typing import Optional

from ..taxonomy import GRADE_ORDER, GRADES, TOPIC_STACK
from .testgen import families_for

BLUEPRINT = {
    "trainee": [1] * 8 + [2] * 4,
    "junior":  [1] * 3 + [2] * 6 + [3] * 3,
    "middle":  [2] * 3 + [3] * 6 + [4] * 3,
    "senior":  [2] * 2 + [3] * 4 + [4] * 6,
}
CORE_MIN_SHARE = 0.5
CORE_MIN_SHARE_BY_GRADE = {"senior": 2 / 3}  # у старшего грейда потолок уровней заканчивается: порог по «ключевым» заданиям строже
MAX_FAMILY_REPEAT = 2
MAX_POOL_QUESTIONS = 3
CONFIDENT_RATIO = 0.85  # выше — предлагаем попробовать следующий грейд


def new_seed() -> str:
    return secrets.token_hex(8)


def build_test(spec: str, target_grade: str, seed: str) -> list[dict]:
    """Собирает полный набор заданий (с ответами). Детерминирован по (spec, grade, seed)."""
    rng = random.Random(f"{spec}:{target_grade}:{seed}")
    fams = families_for(spec)
    used: Counter = Counter()
    pool_used = 0
    prompts: set = set()
    out: list[dict] = []
    for lvl in sorted(BLUEPRINT[target_grade]):
        cands = [f for f in fams if lvl in f.levels and used[f.name] < MAX_FAMILY_REPEAT
                 and not (f.name == "pool" and pool_used >= MAX_POOL_QUESTIONS)]
        q = None
        for _ in range(8):  # защита от повторов одного и того же текста
            weights = [f.weight * (0.25 ** used[f.name]) for f in cands]
            fam = rng.choices(cands, weights)[0]
            q = fam.fn(random.Random(rng.getrandbits(64)), lvl)
            key = (q["prompt"], tuple(sorted(q.get("options", ()))))  # порядок вариантов не делает вопрос «новым»
            if key not in prompts:
                prompts.add(key)
                used[fam.name] += 1
                pool_used += fam.name == "pool"
                break
        q["level"] = lvl
        q["id"] = f"q{len(out) + 1}"
        out.append(q)
    return out


def public_view(questions: list[dict]) -> list[dict]:
    """Что видит кандидат: без ответов, семейства и объяснений."""
    res = []
    for i, q in enumerate(questions, 1):
        item = {"id": q["id"], "n": i, "kind": q["kind"], "prompt": q["prompt"]}
        if q["kind"] == "choice":
            item["options"] = q["options"]
        else:
            item["hint"] = "Введите число (дробную часть — через точку или запятую)"
        res.append(item)
    return res


def _parse_number(v) -> Optional[float]:
    try:
        return float(str(v).strip().replace(",", ".").replace(" ", ""))
    except (TypeError, ValueError):
        return None


def is_correct(q: dict, given) -> bool:
    if given is None or given == "":
        return False
    if q["kind"] == "choice":
        try:
            return int(given) == q["answer"]
        except (TypeError, ValueError):
            return False
    val = _parse_number(given)
    return val is not None and abs(val - float(q["answer"])) <= float(q.get("tol", 0)) + 1e-9


def grade_answers(questions: list[dict], answers: dict, target_grade: str, threshold: float) -> dict:
    core_level = GRADES[target_grade]["level"]
    score = max_score = 0.0
    core_total = core_ok = 0
    topics: dict = defaultdict(lambda: {"c": 0, "n": 0, "max_level": 0, "hard_ok": 0})
    detail = []
    for q in questions:
        ok = is_correct(q, answers.get(q["id"]))
        w = q["level"]
        max_score += w
        score += w * ok
        if q["level"] == core_level:
            core_total += 1
            core_ok += ok
        t = topics[q["topic"]]
        t["n"] += 1
        t["c"] += ok
        t["max_level"] = max(t["max_level"], q["level"])
        t["hard_ok"] += bool(ok and q["level"] >= 3)
        detail.append({"id": q["id"], "ok": bool(ok), "level": q["level"], "topic": q["topic"]})
    ratio = score / max_score if max_score else 0.0
    core_share = core_ok / core_total if core_total else 1.0
    passed = ratio >= threshold and core_share >= CORE_MIN_SHARE_BY_GRADE.get(target_grade, CORE_MIN_SHARE) - 1e-9
    return {"score": score, "max_score": max_score, "ratio": round(ratio, 4), "passed": passed,
            "core_share": round(core_share, 3), "topics": dict(topics), "detail": detail}


def confirmed_stack(topics: dict) -> list[str]:
    """Технологии, подтверждённые результатом теста (а не самоописанием)."""
    tags: set = set()
    for topic, t in topics.items():
        if (t["n"] >= 2 and t["c"] / t["n"] >= 0.66) or (t["n"] == 1 and t["c"] == 1 and t["max_level"] >= 3) or t["hard_ok"] >= 1:
            tags.update(TOPIC_STACK.get(topic, []))
    return sorted(tags)


def integrity_flags(duration_sec: float, n_questions: int, blur_count: int, late: bool) -> dict:
    flags = []
    if duration_sec / max(n_questions, 1) < 10:
        flags.append("too_fast")
    if blur_count >= 6:
        flags.append("many_tab_switches")
    if late:
        flags.append("late")
    return {"flags": flags, "review": bool({"too_fast", "many_tab_switches"} & set(flags)), "duration_sec": round(duration_sec),
            "blur_count": blur_count}


def next_grade(g: str) -> Optional[str]:
    i = GRADE_ORDER.index(g)
    return GRADE_ORDER[i + 1] if i + 1 < len(GRADE_ORDER) else None


def prev_grade(g: str) -> Optional[str]:
    i = GRADE_ORDER.index(g)
    return GRADE_ORDER[i - 1] if i > 0 else None
