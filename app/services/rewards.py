"""Награды в профиле: значки за заполненное резюме, пройденные тесты и решённые задачи тренировки.

Значки вычисляются по состоянию аккаунта; первое получение фиксируется в `achievements` (чтобы показать «новое»).
"""
import json

from .. import db as D
from . import practice

# code, название, описание, очки, группа
BADGES = [
    ("avatar", "Знакомство", "Добавлено фото профиля", 5, "profile"),
    ("profile_full", "Профиль заполнен", "ФИО, телефон, город, заголовок, «о себе» и не менее трёх технологий", 15, "profile"),
    ("resume_started", "Резюме начато", "В резюме есть место работы или проект", 10, "resume"),
    ("resume_full", "Резюме 100%", "Заполнены все разделы: опыт, проекты, образование, сертификаты и «о себе»", 30, "resume"),
    ("cert_added", "Подтверждено документом", "Добавлен диплом, сертификат или награда", 10, "resume"),
    ("survey", "Выбрал путь", "Пройден опрос по специализации", 5, "tests"),
    ("first_test", "Первый тест", "Завершён первый тест на грейд", 15, "tests"),
    ("category", "Категория присвоена", "Тест пройден — категория подтверждена", 30, "tests"),
    ("tests_3", "Три зачёта", "Три успешных теста", 25, "tests"),
    ("expert", "Expert", "Пройден экспертный тест", 50, "tests"),
    ("fsp", "Свой в ФСП", "Привязан ФСП ID", 15, "profile"),
    ("practice_1", "Первая задача", "Решена первая задача тренировки", 5, "practice"),
    ("practice_10", "Разминка", "Решено 10 задач тренировки", 15, "practice"),
    ("practice_50", "Набиваю руку", "Решено 50 задач тренировки", 30, "practice"),
    ("practice_100", "Сотня", "Решено 100 задач тренировки", 50, "practice"),
    ("hard_10", "Сложные не страшны", "Решено 10 задач сложности 4–5", 40, "practice"),
    ("apply", "Первый отклик", "Отправлен отклик на вакансию", 10, "career"),
    ("invite_accepted", "Нашли друг друга", "Принято приглашение работодателя", 20, "career"),
]
LEVELS = [(0, "Новичок"), (30, "Участник"), (80, "Практик"), (150, "Профи"), (250, "Мастер")]
INFO = {b[0]: b for b in BADGES}


def resume_progress(resume: dict) -> dict:
    parts = {"summary": bool(resume.get("summary")), "experience": bool(resume.get("experience")), "projects": bool(resume.get("projects")),
             "education": bool(resume.get("education")), "certificates": bool(resume.get("certificates")),
             "position": bool(resume.get("desired_position"))}
    return {"parts": parts, "percent": round(100 * sum(parts.values()) / len(parts))}


def _earned(uid: int) -> set:
    c = D.q1("SELECT * FROM candidates WHERE user_id = ?", (uid,))
    if c is None:
        return set()
    u = D.q1("SELECT avatar FROM users WHERE id = ?", (uid,))
    resume = D.jl(c["resume"], {})
    st = practice.stats(uid)
    passed = D.q1("SELECT COUNT(*) AS n FROM test_attempts WHERE user_id = ? AND passed = 1 AND review_state != 'annulled'", (uid,))["n"]
    done = D.q1("SELECT COUNT(*) AS n FROM test_attempts WHERE user_id = ? AND status IN ('finished','expired')", (uid,))["n"]
    got = set()
    checks = {
        "avatar": bool(u and u["avatar"]),
        "profile_full": all([c["full_name"], c["phone"], c["city"], c["headline"], c["about"]]) and len(D.jl(c["stack_declared"], [])) >= 3,
        "resume_started": bool(resume.get("experience") or resume.get("projects")),
        "resume_full": resume_progress(resume)["percent"] == 100,
        "cert_added": bool(resume.get("certificates")),
        "survey": bool(D.jl(c["survey"], {})),
        "first_test": done >= 1, "category": c["grade"] is not None, "tests_3": passed >= 3, "expert": bool(c["expert"]),
        "fsp": bool(c["fsp_id"]),
        "practice_1": st["solved"] >= 1, "practice_10": st["solved"] >= 10, "practice_50": st["solved"] >= 50, "practice_100": st["solved"] >= 100,
        "hard_10": st["hard_solved"] >= 10,
        "apply": bool(D.q1("SELECT 1 FROM applications WHERE candidate_id = ?", (uid,))),
        "invite_accepted": bool(D.q1("SELECT 1 FROM invites WHERE candidate_id = ? AND status = 'accepted'", (uid,))),
    }
    for k, v in checks.items():
        if v:
            got.add(k)
    return got


def sync(uid: int) -> dict:
    """Фиксирует новые значки и возвращает полную картину: значки, очки, уровень, прогресс до следующего."""
    earned = _earned(uid)
    have = {r["code"]: r for r in D.qa("SELECT code, at, seen FROM achievements WHERE user_id = ?", (uid,))}
    new = []
    for code in earned - set(have):
        D.ex("INSERT INTO achievements(user_id, code, at, seen) VALUES (?,?,?,0)", (uid, code, D.now()))
        new.append(code)
    have = {r["code"]: r for r in D.qa("SELECT code, at, seen FROM achievements WHERE user_id = ?", (uid,))}
    points = sum(INFO[c][3] for c in have if c in INFO)
    lvl = max((i for i, (p, _) in enumerate(LEVELS) if points >= p), default=0)
    nxt = LEVELS[lvl + 1] if lvl + 1 < len(LEVELS) else None
    badges = [{"code": b[0], "title": b[1], "description": b[2], "points": b[3], "group": b[4], "earned": b[0] in have,
               "at": have[b[0]]["at"] if b[0] in have else None, "new": b[0] in new} for b in BADGES]
    return {"points": points, "level": {"index": lvl + 1, "title": LEVELS[lvl][1]},
            "next": {"title": nxt[1], "at": nxt[0], "left": nxt[0] - points} if nxt else None,
            "earned": len(have), "total": len(BADGES), "badges": badges, "new": [INFO[c][1] for c in new]}
