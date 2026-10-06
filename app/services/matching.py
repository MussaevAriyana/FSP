"""Механика подбора: категория → сила подтверждённого профиля → объяснение.

Идея. Работодатель описывает потребность (специализация, грейд, стек). Система:
  1. определяет *рекомендованные категории* (связки «специализация × грейд») и считает в них кандидатов;
  2. внутри выдачи ранжирует кандидатов по «силе подтверждённого профиля»;
  3. к каждому кандидату прикладывает объяснение — из чего сложился балл.

Выдача строится ТОЛЬКО по присвоенным категориям и подтверждённым данным (результат теста,
подтверждённый тестом стек, история ФСП, актуальность). Самоописанное резюме в ранжировании
не участвует (требование ТЗ).

    итог = K(категория) × (0.15 + 0.85 × P(профиль))
    P = 0.35·тест + 0.30·подтверждённый_стек + 0.25·ФСП + 0.10·актуальность

Мультипликативная связка делает категорию главным фактором (кандидат «не той» категории не может
обогнать подходящего за счёт сильного профиля), а профиль — главным фактором *внутри* категории.
"""
from datetime import datetime, timezone
from typing import Optional

from ..taxonomy import GRADE_ORDER, GRADES, RELATED_SPECS, SPECS, category_label

W_TEST, W_STACK, W_FSP, W_FRESH = 0.35, 0.30, 0.25, 0.10
PASS_RATIO = 0.65
GRADE_FACTOR = {0: 1.0, 1: 0.60, -1: 0.55, 2: 0.25, -2: 0.20}   # ключ: grade(кандидата) − grade(потребности)
INTEGRITY_PENALTY = 0.85


def category_factor(need_spec: str, need_grade: str, c_spec: Optional[str], c_grade: Optional[str]) -> tuple[float, str]:
    """K(категория) ∈ [0,1] и пояснение."""
    if not c_spec or not c_grade:
        return 0.0, "категория не присвоена"
    diff = GRADE_ORDER.index(c_grade) - GRADE_ORDER.index(need_grade)
    gf = GRADE_FACTOR.get(diff, 0.0)
    if c_spec == need_spec:
        if diff == 0:
            return 1.0, f"категория точно совпадает: {category_label(c_spec, c_grade)}"
        word = "выше" if diff > 0 else "ниже"
        return gf, f"та же специализация, грейд на {abs(diff)} ступ. {word} запрошенного ({GRADES[c_grade]['title']})"
    rel = RELATED_SPECS.get(need_spec, {}).get(c_spec, 0.0)
    if rel and diff in (0, 1, -1):
        return round(rel * gf, 3), f"смежная специализация ({SPECS[c_spec]['short']}), грейд {GRADES[c_grade]['title']}"
    return 0.0, "другая специализация"


def freshness(last_activity: Optional[str], micro_bonus: float, now: Optional[datetime] = None) -> float:
    if not last_activity:
        return 0.0
    now = now or datetime.now(timezone.utc)
    last = datetime.strptime(last_activity, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    days = max((now - last).days, 0)
    base = max(0.0, 1.0 - days / 120)
    return min(1.0, base * 0.8 + min(micro_bonus, 1.0) * 0.2)


def score_candidate(need: dict, cand: dict, now: Optional[datetime] = None) -> dict:
    """need: {spec, grade, stack[]}; cand: карточка кандидата (внутренний вид, с ratio/fsp/…)."""
    k, k_reason = category_factor(need["spec"], need["grade"], cand["spec"], cand["grade"])
    test = max(0.0, min(1.0, (cand["ratio"] - PASS_RATIO) / (1 - PASS_RATIO)))
    need_stack = [s.lower() for s in need.get("stack", [])]
    confirmed = set(cand["stack_confirmed"])
    matched = [s for s in need_stack if s in confirmed]
    stack = (len(matched) / len(need_stack)) if need_stack else 0.5
    fsp = cand["fsp"]["strength"] if cand.get("fsp") else 0.0
    fresh = freshness(cand.get("last_activity_at"), cand.get("micro_bonus", 0.0), now)
    profile = W_TEST * test + W_STACK * stack + W_FSP * fsp + W_FRESH * fresh
    if cand.get("integrity_review"):
        profile *= INTEGRITY_PENALTY
    total = k * (0.15 + 0.85 * profile)

    reasons = [{"factor": "category", "label": "Категория", "value": round(k, 2), "text": k_reason}]
    reasons.append({"factor": "test", "label": "Результат теста", "value": round(test, 2),
                    "text": f"{round(cand['ratio'] * 100)}% при пороге зачёта {round(PASS_RATIO * 100)}%"})
    if need_stack:
        txt = (f"подтверждено {len(matched)} из {len(need_stack)}: {', '.join(matched)}" if matched
               else f"из требуемых ({', '.join(need_stack)}) тестом пока ничего не подтверждено")
    else:
        txt = "стек в потребности не задан"
    reasons.append({"factor": "stack", "label": "Подтверждённый стек", "value": round(stack, 2), "text": txt})
    if cand.get("fsp"):
        f = cand["fsp"]
        reasons.append({"factor": "fsp", "label": "Опыт ФСП", "value": round(fsp, 2),
                        "text": f"{f['events_count']} мероприятий, лучший результат — топ-{f['best_top_percent']:g}% ({f['best_event']})"})
    else:
        reasons.append({"factor": "fsp", "label": "Опыт ФСП", "value": 0.0, "text": "истории участия в ФСП нет (не снижает категорию)"})
    reasons.append({"factor": "fresh", "label": "Актуальность профиля", "value": round(fresh, 2),
                    "text": "профиль обновлялся недавно" if fresh > 0.6 else "профиль давно не обновлялся" if fresh < 0.3 else "умеренная актуальность"})
    if cand.get("integrity_review"):
        reasons.append({"factor": "integrity", "label": "Проверка прохождения", "value": -0.15,
                        "text": "тест пройден с подозрительной скоростью/переключениями вкладок — вес профиля снижен"})
    return {"score": round(total * 100, 1), "profile": round(profile * 100, 1), "reasons": reasons, "matched_stack": matched}


def recommend_categories(need: dict, cats: dict) -> list[dict]:
    """cats: {(spec, grade): число кандидатов}. Возвращает категории, релевантные потребности."""
    out = []
    for (spec, grade), n in cats.items():
        k, why = category_factor(need["spec"], need["grade"], spec, grade)
        if k >= 0.2 and n:
            out.append({"spec": spec, "grade": grade, "label": category_label(spec, grade), "count": n,
                        "fit": round(k, 2), "why": why})
    return sorted(out, key=lambda c: (-c["fit"], -c["count"]))
