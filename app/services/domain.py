"""Доменная логика: карточки кандидатов и правила видимости, жизненный цикл теста, смена грейда."""
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from flask import current_app

from .. import db as D
from ..apidoc import ApiError
from ..taxonomy import GRADES, SPECS, category_label
from . import engine, fsp as fsp_mod, matching

DEFAULT_PRIVACY = {"show_stack": True, "show_fsp": True, "show_experience": True, "show_city": False, "visible_in_bank": True}
CALIBRATION_HOURS = 24


# ------------------------------------------------------------------------------ общие
def registry() -> fsp_mod.FileRegistry:
    return fsp_mod.FileRegistry(current_app.config["FSP_REGISTRY_FILE"])


def new_pseudo_code() -> str:
    while True:
        code = "C-" + secrets.token_hex(3).upper()
        if not D.q1("SELECT 1 FROM candidates WHERE pseudo_code = ?", (code,)):
            return code


def touch(user_id: int) -> None:
    D.ex("UPDATE candidates SET last_activity_at = ? WHERE user_id = ?", (D.now(), user_id))


def get_candidate(user_id: int) -> dict:
    row = D.q1("SELECT c.*, u.email FROM candidates c JOIN users u ON u.id = c.user_id WHERE c.user_id = ?", (user_id,))
    if row is None:
        raise ApiError(404, "not_found", "Профиль кандидата не найден")
    return hydrate(dict(row))


def hydrate(c: dict) -> dict:
    for k in ("roles", "soft_skills", "stack_declared", "stack_confirmed"):
        c[k] = D.jl(c.get(k), [])
    c["survey"] = D.jl(c.get("survey"), {})
    c["privacy"] = {**DEFAULT_PRIVACY, **D.jl(c.get("privacy"), {})}
    return c


def fsp_summary(c: dict) -> Optional[dict]:
    if not c.get("fsp_id"):
        return None
    return fsp_mod.summarize(registry().get(c["fsp_id"]))


def last_passed_integrity(user_id: int) -> bool:
    """True, если последняя успешная попытка помечена как «требует проверки»."""
    row = D.q1("SELECT flags FROM test_attempts WHERE user_id = ? AND passed = 1 ORDER BY id DESC LIMIT 1", (user_id,))
    return bool(row and D.jl(row["flags"], {}).get("review"))


# ------------------------------------------------------------------------------ видимость и карточки
def visible_candidate_rows() -> list[dict]:
    rows = D.qa("""SELECT c.*, u.email FROM candidates c JOIN users u ON u.id = c.user_id
                   WHERE c.grade IS NOT NULL AND c.spec IS NOT NULL AND c.consent_publish = 1 AND u.email_confirmed = 1""")
    out = [hydrate(dict(r)) for r in rows]
    return [c for c in out if c["privacy"]["visible_in_bank"]]


def revealed_ids(employer_id: int) -> set:
    """Кандидаты, чьи контакты открыты этому работодателю: приняли его приглашение или сами откликнулись на его вакансию."""
    a = D.qa("SELECT candidate_id FROM invites WHERE employer_id = ? AND status = 'accepted'", (employer_id,))
    b = D.qa("""SELECT a.candidate_id FROM applications a JOIN vacancies v ON v.id = a.vacancy_id WHERE v.employer_id = ?""", (employer_id,))
    return {r["candidate_id"] for r in a} | {r["candidate_id"] for r in b}


def contacts_revealed(employer_id: int, candidate_id: int) -> bool:
    return candidate_id in revealed_ids(employer_id)


def integrity_map() -> dict:
    """user_id -> True, если последняя успешная попытка помечена «требует проверки»."""
    res: dict = {}
    for r in D.qa("SELECT user_id, flags FROM test_attempts WHERE passed = 1 ORDER BY id"):
        res[r["user_id"]] = bool(D.jl(r["flags"], {}).get("review"))
    return res


def internal_view(c: dict, integ: Optional[dict] = None) -> dict:
    """Расширенный вид для расчёта подбора (до применения приватности)."""
    review = integ.get(c["user_id"], False) if integ is not None else last_passed_integrity(c["user_id"])
    return {"spec": c["spec"], "grade": c["grade"], "ratio": c["best_score"], "stack_confirmed": c["stack_confirmed"],
            "fsp": fsp_summary(c), "last_activity_at": c["last_activity_at"], "micro_bonus": c["micro_bonus"],
            "integrity_review": review}


def employer_card(c: dict, employer_id: int, need: Optional[dict] = None, detailed: bool = False,
                  integ: Optional[dict] = None, revealed: Optional[set] = None) -> dict:
    """Карточка кандидата для работодателя. Имя и контакты — только после принятия/отклика."""
    internal = internal_view(c, integ)
    p = c["privacy"]
    is_revealed = (c["user_id"] in revealed) if revealed is not None else contacts_revealed(employer_id, c["user_id"])
    card = {
        "code": c["pseudo_code"],
        "category": {"spec": c["spec"], "grade": c["grade"], "label": category_label(c["spec"], c["grade"])},
        "test_score": round(c["best_score"] * 100),
        "headline": c["headline"] if detailed else "",
        "stack_confirmed": c["stack_confirmed"] if p["show_stack"] else [],
        "stack_declared": [t for t in c["stack_declared"] if t not in c["stack_confirmed"]] if p["show_stack"] else [],
        "experience_years": c["experience_years"] if p["show_experience"] else None,
        "city": c["city"] if (p["show_city"] or is_revealed) else None,
        "fsp": (internal["fsp"] if p["show_fsp"] else None),
        "has_fsp": bool(internal["fsp"]) and p["show_fsp"],
        "last_activity_at": c["last_activity_at"],
        "revealed": is_revealed,
    }
    if detailed:
        card["about"] = c["about"] if p["show_experience"] else ""
        card["soft_skills"] = c["soft_skills"]
        card["roles"] = c["roles"] if p["show_experience"] else []
    if is_revealed:
        card["contacts"] = {"full_name": c["full_name"], "email": c["email"], "phone": c["phone"]}
    if need:
        card["match"] = matching.score_candidate(need, internal)
    return card


def candidate_by_user_id(uid: int) -> dict:
    return get_candidate(uid)


def visible_by_code(code: str) -> dict:
    for c in visible_candidate_rows():
        if c["pseudo_code"] == code.upper():
            return c
    raise ApiError(404, "not_found", "Кандидат не найден или скрыл свой профиль")


# ------------------------------------------------------------------------------ тестирование
def cooldown_state(c: dict, spec: str, grade: str, now: Optional[datetime] = None) -> dict:
    """Можно ли сейчас проходить тест на (spec, grade) — с учётом ограничения на смену грейда."""
    now = now or datetime.now(timezone.utc)
    cooldown = timedelta(days=current_app.config["GRADE_COOLDOWN_DAYS"])
    if c["grade"] is None:
        return {"allowed": True, "reason": "first_category", "change": False}
    if spec == c["spec"] and grade == c["grade"]:
        return {"allowed": True, "reason": "same_category", "change": False}
    assigned = D.parse_ts(c["category_assigned_at"])
    if c["last_grade_change_at"] is None and now - assigned < timedelta(hours=CALIBRATION_HOURS):
        return {"allowed": True, "reason": "calibration_window", "change": True, "calibration": True}
    ref = D.parse_ts(c["last_grade_change_at"]) if c["last_grade_change_at"] else assigned
    if now - ref >= cooldown:
        return {"allowed": True, "reason": "cooldown_passed", "change": True}
    nxt = ref + cooldown
    return {"allowed": False, "reason": "cooldown", "change": True, "next_allowed_at": nxt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "days_left": (nxt - now).days + 1}


def _expire_stale(user_id: int) -> None:
    D.ex("UPDATE test_attempts SET status = 'expired' WHERE user_id = ? AND status = 'active' AND deadline_at < ?",
         (user_id, (datetime.now(timezone.utc) - timedelta(seconds=45)).strftime("%Y-%m-%dT%H:%M:%SZ")))


def start_attempt(user_id: int, spec: str, grade: str) -> dict:
    c = get_candidate(user_id)
    if not c["survey"]:
        raise ApiError(409, "survey_required", "Сначала пройдите опрос по отрасли и специализации")
    _expire_stale(user_id)
    active = D.q1("SELECT * FROM test_attempts WHERE user_id = ? AND status = 'active'", (user_id,))
    if active:
        if active["spec"] == spec and active["target_grade"] == grade:
            return dict(active)  # продолжаем незавершённую попытку
        raise ApiError(409, "attempt_active", "У вас есть незавершённая попытка. Завершите её или дождитесь окончания времени")
    st = cooldown_state(c, spec, grade)
    if not st["allowed"]:
        raise ApiError(409, "grade_change_limited",
                       f"Смена грейда или специализации доступна не чаще одного раза в {current_app.config['GRADE_COOLDOWN_DAYS']} дней. "
                       f"Следующая попытка — через {st['days_left']} дн.", st)
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    n = D.q1("SELECT COUNT(*) AS n FROM test_attempts WHERE user_id = ? AND started_at >= ?", (user_id, since))["n"]
    if n >= current_app.config["TEST_ATTEMPTS_PER_DAY"]:
        raise ApiError(429, "too_many_attempts", "Достигнут лимит попыток тестирования за сутки")
    seed = engine.new_seed()
    questions = engine.build_test(spec, grade, seed)
    started = datetime.now(timezone.utc)
    deadline = started + timedelta(minutes=current_app.config["TEST_TIME_LIMIT_MIN"])
    aid = D.ex("""INSERT INTO test_attempts(user_id, spec, target_grade, seed, status, started_at, deadline_at, questions)
                  VALUES (?,?,?,?, 'active', ?,?,?)""",
               (user_id, spec, grade, seed, started.strftime("%Y-%m-%dT%H:%M:%SZ"), deadline.strftime("%Y-%m-%dT%H:%M:%SZ"), D.js(questions)))
    return dict(D.q1("SELECT * FROM test_attempts WHERE id = ?", (aid,)))


def attempt_public(att: dict) -> dict:
    qs = D.jl(att["questions"], [])
    return {"id": att["id"], "spec": att["spec"], "grade": att["target_grade"], "status": att["status"],
            "started_at": att["started_at"], "deadline_at": att["deadline_at"],
            "time_limit_min": current_app.config["TEST_TIME_LIMIT_MIN"], "questions": engine.public_view(qs)}


def finish_attempt(user_id: int, attempt_id: int, answers: dict, blur_count: int) -> dict:
    att = D.q1("SELECT * FROM test_attempts WHERE id = ? AND user_id = ?", (attempt_id, user_id))
    if att is None:
        raise ApiError(404, "not_found", "Попытка не найдена")
    if att["status"] != "active":
        raise ApiError(409, "attempt_closed", "Попытка уже завершена или истекла")
    now = datetime.now(timezone.utc)
    late = now > D.parse_ts(att["deadline_at"]) + timedelta(seconds=45)
    questions = D.jl(att["questions"], [])
    res = engine.grade_answers(questions, answers, att["target_grade"], current_app.config["PASS_THRESHOLD"])
    if late:
        res["passed"] = False
    duration = (now - D.parse_ts(att["started_at"])).total_seconds()
    integ = engine.integrity_flags(duration, len(questions), blur_count, late)
    c = get_candidate(user_id)
    outcome = apply_outcome(c, att, res, integ)
    D.ex("""UPDATE test_attempts SET status = ?, finished_at = ?, answers = ?, score = ?, max_score = ?, ratio = ?, passed = ?,
            topic_stats = ?, flags = ?, outcome = ? WHERE id = ?""",
         ("expired" if late else "finished", D.now(), D.js(answers), res["score"], res["max_score"], res["ratio"], int(res["passed"]),
          D.js(res["topics"]), D.js(integ), D.js(outcome), attempt_id))
    return result_view(D.q1("SELECT * FROM test_attempts WHERE id = ?", (attempt_id,)))


def apply_outcome(c: dict, att, res: dict, integ: dict) -> dict:
    """Применяет результат к профилю. Грейд никогда не понижается принудительно."""
    spec, grade = att["spec"], att["target_grade"]
    uid = c["user_id"]
    out = {"category_changed": False, "new_category": None, "can_try_higher": None, "suggest_lower": None, "message": ""}
    confirmed = engine.confirmed_stack(res["topics"])
    if res["passed"]:
        st = cooldown_state(c, spec, grade)
        merged = sorted(set(c["stack_confirmed"]) | set(confirmed))
        now = D.now()
        if c["grade"] is None:
            D.ex("""UPDATE candidates SET spec=?, grade=?, best_score=?, category_assigned_at=?, stack_confirmed=?, last_activity_at=? WHERE user_id=?""",
                 (spec, grade, res["ratio"], now, D.js(merged), now, uid))
            D.ex("INSERT INTO grade_history(user_id, spec, old_grade, new_grade, reason, at) VALUES (?,?,?,?,?,?)", (uid, spec, None, grade, "initial", now))
            out.update(category_changed=True, message="Категория присвоена")
        elif spec == c["spec"] and grade == c["grade"]:
            D.ex("UPDATE candidates SET best_score=?, stack_confirmed=?, last_activity_at=? WHERE user_id=?", (res["ratio"], D.js(merged), now, uid))
            out["message"] = "Результат подтверждён, профиль обновлён"
        else:
            sets = "spec=?, grade=?, best_score=?, stack_confirmed=?, last_activity_at=?"
            args = [spec, grade, res["ratio"], D.js(merged), now]
            if not st.get("calibration"):
                sets += ", last_grade_change_at=?"
                args.append(now)
            D.ex(f"UPDATE candidates SET {sets} WHERE user_id=?", (*args, uid))
            D.ex("INSERT INTO grade_history(user_id, spec, old_grade, new_grade, reason, at) VALUES (?,?,?,?,?,?)",
                 (uid, spec, c["grade"], grade, "calibration" if st.get("calibration") else "retest", now))
            out.update(category_changed=True, message="Категория изменена")
        out["new_category"] = {"spec": spec, "grade": grade, "label": category_label(spec, grade)}
        nxt = engine.next_grade(grade)
        if nxt and res["ratio"] >= engine.CONFIDENT_RATIO:
            out["can_try_higher"] = {"grade": nxt, "label": GRADES[nxt]["title"]}
    else:
        touch(uid)
        prv = engine.prev_grade(grade)
        if prv:
            out["suggest_lower"] = {"grade": prv, "label": GRADES[prv]["title"]}
        out["message"] = ("Тест не пройден. Грейд не понижается автоматически — вы можете пройти тест на уровень ниже."
                          if c["grade"] is None else "Тест не пройден. Ваша текущая категория сохранена.")
    out["integrity_review"] = integ["review"]
    return out


def result_view(att, with_answers: bool = True) -> dict:
    qs = D.jl(att["questions"], [])
    answers = D.jl(att["answers"], {})
    detail = []
    for q in qs:
        given = answers.get(q["id"])
        item = {"id": q["id"], "level": q["level"], "topic": q["topic"], "prompt": q["prompt"], "ok": engine.is_correct(q, given),
                "given": given}
        if q["kind"] == "choice":
            item["options"] = q["options"]
            item["correct"] = q["answer"]
        else:
            item["correct"] = q["answer"]
        detail.append(item)
    return {"id": att["id"], "spec": att["spec"], "grade": att["target_grade"], "status": att["status"], "started_at": att["started_at"],
            "finished_at": att["finished_at"], "score_pct": round((att["ratio"] or 0) * 100), "passed": bool(att["passed"]),
            "outcome": D.jl(att["outcome"], {}), "integrity": D.jl(att["flags"], {}), "topics": D.jl(att["topic_stats"], {}),
            "detail": detail if with_answers else []}


def candidate_state(c: dict) -> dict:
    """Единый «снимок» для кабинета кандидата."""
    fsp_rec = registry().get(c["fsp_id"]) if c.get("fsp_id") else None
    return {
        "profile": {k: c[k] for k in ("full_name", "phone", "city", "headline", "about", "experience_years", "roles", "soft_skills", "stack_declared")},
        "email": c["email"], "code": c["pseudo_code"],
        "category": {"spec": c["spec"], "grade": c["grade"], "label": category_label(c["spec"], c["grade"]),
                     "score_pct": round(c["best_score"] * 100) if c["grade"] else None, "assigned_at": c["category_assigned_at"],
                     "last_change_at": c["last_grade_change_at"]},
        "stack_confirmed": c["stack_confirmed"], "survey": c["survey"],
        "fsp": {"linked": bool(c["fsp_id"]), "fsp_id": c["fsp_id"], "summary": fsp_mod.summarize(fsp_rec),
                "full_name": (fsp_rec or {}).get("full_name")},
        "settings": {"consent_publish": bool(c["consent_publish"]), "privacy": c["privacy"]},
        "steps": {"profile": bool(c["full_name"]), "survey": bool(c["survey"]), "test": c["grade"] is not None,
                  "publish": bool(c["consent_publish"])},
        "visible_to_employers": bool(c["grade"] and c["consent_publish"] and c["privacy"]["visible_in_bank"]),
        # можно ли прямо сейчас пройти тест на ДРУГОЙ грейд/специализацию (для текущей категории повтор всегда доступен)
        "grade_change": cooldown_state(c, c["spec"], "__change__") if c["grade"] else {"allowed": True, "reason": "first_category"},
        "cooldown_days": current_app.config["GRADE_COOLDOWN_DAYS"],
    }
