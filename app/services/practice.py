"""Тренировка: одиночные задания из того же генератора, что и тест, но без категории, прокторинга и лимитов.

Каждое задание порождается заново (параметры случайны), ответ хранится на сервере. После ответа показываются верный ответ и разбор.
Результаты тренировки не влияют на категорию и подбор — только на награды в профиле.
"""
import random

from .. import db as D
from ..apidoc import ApiError
from . import engine, testgen


def next_item(uid: int, spec: str, level: int) -> dict:
    # неотвеченное задание того же уровня отдаём повторно — нельзя «листать» вопросы, пока не ответил или не пропустил
    row = D.q1("SELECT * FROM practice_items WHERE user_id = ? AND spec = ? AND level = ? AND solved IS NULL ORDER BY id DESC LIMIT 1", (uid, spec, level))
    if row:
        return public(dict(row))
    fams = [f for f in testgen.families_for(spec) if level in f.levels]
    rng = random.Random()
    fam = rng.choices(fams, [f.weight for f in fams])[0]
    q = fam.fn(random.Random(rng.getrandbits(64)), level)
    q["level"], q["id"] = level, "p"
    iid = D.ex("INSERT INTO practice_items(user_id, spec, level, topic, question, created_at) VALUES (?,?,?,?,?,?)",
               (uid, spec, level, q["topic"], D.js(q), D.now()))
    return public(dict(D.q1("SELECT * FROM practice_items WHERE id = ?", (iid,))))


def public(row: dict) -> dict:
    q = D.jl(row["question"], {})
    out = {"id": row["id"], "spec": row["spec"], "level": row["level"], "topic": row["topic"], "kind": q["kind"], "prompt": q["prompt"]}
    if q["kind"] == "choice":
        out["options"] = q["options"]
    else:
        out["hint"] = "Введите число (дробную часть — через точку или запятую)"
    return out


def answer(uid: int, item_id: int, given) -> dict:
    row = D.q1("SELECT * FROM practice_items WHERE id = ? AND user_id = ?", (item_id, uid))
    if row is None:
        raise ApiError(404, "not_found", "Задание не найдено")
    if row["solved"] is not None:
        raise ApiError(409, "already_answered", "На это задание уже отвечено")
    q = D.jl(row["question"], {})
    ok = engine.is_correct(q, given)
    D.ex("UPDATE practice_items SET solved = ?, answered_at = ? WHERE id = ?", (int(ok), D.now(), item_id))
    if q["kind"] == "choice":
        correct = q["options"][q["answer"]]
    else:
        correct = q["answer"]
    return {"ok": ok, "correct": correct, "explanation": q.get("explanation", ""), "stats": stats(uid)}


def skip(uid: int, item_id: int) -> None:
    D.ex("UPDATE practice_items SET solved = 0, answered_at = ? WHERE id = ? AND user_id = ? AND solved IS NULL", (D.now(), item_id, uid))


def stats(uid: int) -> dict:
    rows = D.qa("SELECT level, solved, COUNT(*) AS n FROM practice_items WHERE user_id = ? AND solved IS NOT NULL GROUP BY level, solved", (uid,))
    by = {lv: {"ok": 0, "all": 0} for lv in range(1, 6)}
    for r in rows:
        by[r["level"]]["all"] += r["n"]
        if r["solved"] == 1:
            by[r["level"]]["ok"] += r["n"]
    ok = sum(v["ok"] for v in by.values())
    return {"solved": ok, "attempts": sum(v["all"] for v in by.values()), "hard_solved": by[4]["ok"] + by[5]["ok"],
            "by_level": [{"level": lv, **by[lv]} for lv in range(1, 6)]}
