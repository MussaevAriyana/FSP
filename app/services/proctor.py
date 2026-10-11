"""Прокторинг теста: журнал событий, оценка риска, автоматическое прекращение, разбор модератором.

Что делает платформа (подробно — docs/DOCUMENTATION.md, §4.5):
  * браузер кандидата (static/proctor.js) фиксирует: уход со вкладки/окна, выход из полноэкранного режима,
    копирование/вставку/контекстное меню, подозрительные сочетания клавиш, признаки открытых инструментов
    разработчика, пропадание камеры, закрытую камеру, а также периодически делает снимок с веб-камеры;
  * сервер сам ставит время, взвешивает события (WEIGHTS), ограничивает вклад каждого вида (CAPS),
    сопоставляет «сессии» (вторая вкладка с той же попыткой), проверяет скорость ответов и «дыры» в съёмке;
  * риск ≥ FLAG_AT — попытка попадает в очередь модератора, вес профиля в подборе снижается;
    риск ≥ TERMINATE_AT — попытка немедленно прекращается без изменения категории;
  * модератор видит журнал и снимки и либо снимает отметку (clear), либо аннулирует попытку (annul):
    если категория была присвоена этой попыткой, она снимается, и кандидату нужно пройти тест заново.

Ограничение (честно): всё, что делает браузер, можно обойти на уровне ОС (вторая камера, второй компьютер,
подсказчик за спиной). Прокторинг не доказывает честность — он делает нечестность дорогой и заметной.
"""
import base64
import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from flask import current_app

from .. import db as D
from ..apidoc import ApiError

# вес одного события
WEIGHTS = {
    "tab_hidden": 3.0, "window_blur": 1.0, "fullscreen_exit": 4.0, "copy": 2.0, "cut": 2.0, "paste": 4.0, "contextmenu": 1.0,
    "devtools": 5.0, "shortcut": 1.0, "print": 3.0, "resize": 1.0, "camera_off": 6.0, "camera_covered": 5.0, "no_face": 3.0,
    "multi_face": 6.0, "phone_detected": 6.0, "multi_person": 5.0, "multi_session": 8.0, "fast_answers": 4.0, "camera_gaps": 8.0, "info": 0.0,
}
# максимальный суммарный вклад одного вида событий (чтобы шум одного вида не «топил» кандидата)
CAPS = {
    "tab_hidden": 24, "window_blur": 6, "fullscreen_exit": 24, "copy": 8, "cut": 8, "paste": 12, "contextmenu": 3, "devtools": 15,
    "shortcut": 4, "print": 6, "resize": 3, "camera_off": 12, "camera_covered": 15, "no_face": 12, "multi_face": 18, "phone_detected": 24, "multi_person": 15,
    "multi_session": 16, "fast_answers": 12, "camera_gaps": 8, "info": 0,
}
FLAG_AT = 12.0
TERMINATE_AT = 45.0
MAX_SNAPSHOTS = 150
MAX_SNAPSHOT_CHARS = 95_000
MAX_EVENTS_PER_BATCH = 60
KINDS = tuple(WEIGHTS)

LABELS = {
    "tab_hidden": "Уход на другую вкладку", "window_blur": "Окно потеряло фокус", "fullscreen_exit": "Выход из полноэкранного режима",
    "copy": "Копирование", "cut": "Вырезание", "paste": "Вставка", "contextmenu": "Контекстное меню", "devtools": "Признаки инструментов разработчика",
    "shortcut": "Запрещённое сочетание клавиш", "print": "Печать / сохранение страницы", "resize": "Изменение размера окна",
    "camera_off": "Камера отключена", "camera_covered": "Камера закрыта или кадр тёмный", "no_face": "В кадре нет лица",
    "multi_face": "В кадре несколько лиц", "phone_detected": "В кадре обнаружен телефон", "multi_person": "В кадре больше одного человека", "multi_session": "Попытка открыта в другой вкладке/устройстве", "fast_answers": "Слишком быстрые ответы на сложные задания",
    "camera_gaps": "Мало снимков с камеры", "info": "Служебное событие",
}


def _now() -> str:
    return D.now()


def risk_of(events: list) -> float:
    """Суммарный риск по списку (kind, weight) с ограничением вклада вида."""
    per: dict = {}
    for kind, w in events:
        per[kind] = per.get(kind, 0.0) + w
    return round(sum(min(v, CAPS.get(k, v)) for k, v in per.items()), 1)


def _all_events(attempt_id: int) -> list:
    return [(r["kind"], r["weight"]) for r in D.qa("SELECT kind, weight FROM proctor_events WHERE attempt_id = ?", (attempt_id,))]


def _add(attempt_id: int, kind: str, meta: Optional[dict] = None, weight: Optional[float] = None) -> None:
    D.ex("INSERT INTO proctor_events(attempt_id, at, kind, weight, meta) VALUES (?,?,?,?,?)",
         (attempt_id, _now(), kind, WEIGHTS.get(kind, 0.0) if weight is None else weight, json.dumps(meta or {}, ensure_ascii=False)))


def _recompute(att_id: int) -> float:
    risk = risk_of(_all_events(att_id))
    state = "flagged" if risk >= FLAG_AT else None
    row = D.q1("SELECT review_state FROM test_attempts WHERE id = ?", (att_id,))
    new_state = row["review_state"]
    if state and row["review_state"] == "clean":
        new_state = "flagged"
    D.ex("UPDATE test_attempts SET risk = ?, review_state = ? WHERE id = ?", (risk, new_state, att_id))
    return risk


def _terminate(att: dict) -> None:
    D.ex("""UPDATE test_attempts SET status = 'terminated', finished_at = ?, passed = 0, ratio = 0, score = 0, max_score = 0,
            review_state = 'flagged', outcome = ? WHERE id = ?""",
         (_now(), json.dumps({"category_changed": False, "message": "Тест прекращён: нарушены правила прохождения под прокторингом. "
                              "Категория не изменилась. Попытку можно оспорить, написав модератору.", "terminated": True}, ensure_ascii=False), att["id"]))


def record(att: dict, cid: str, events: list, snapshot: Optional[str], camera: bool) -> dict:
    """Принимает пакет событий от браузера. Возвращает текущее состояние для клиента."""
    if att["status"] != "active":
        return {"risk": att["risk"], "flagged": att["review_state"] == "flagged", "terminated": att["status"] == "terminated", "active": False}
    state = D.jl(att["proctor"], {})
    # вторая вкладка / другое устройство
    if state.get("cid") and state["cid"] != cid:
        _add(att["id"], "multi_session", {"was": state["cid"][:6], "now": cid[:6]})
    state["cid"] = cid
    state["last_seen"] = _now()
    if current_app.config["PROCTOR_CAMERA_REQUIRED"] and not camera:
        _add(att["id"], "camera_off", {})
    for ev in events[:MAX_EVENTS_PER_BATCH]:
        kind = ev.get("kind")
        if kind not in KINDS or kind in ("multi_session", "fast_answers", "camera_gaps", "camera_off"):
            continue  # эти виды формирует только сервер
        meta = ev.get("meta") if isinstance(ev.get("meta"), dict) else {}
        meta = {str(k)[:24]: (str(v)[:80] if not isinstance(v, (int, float, bool)) else v) for k, v in list(meta.items())[:6]}
        _add(att["id"], kind, meta)
    if snapshot:
        if not snapshot.startswith("data:image/jpeg;base64,") or len(snapshot) > MAX_SNAPSHOT_CHARS:
            raise ApiError(422, "bad_snapshot", "Недопустимый формат снимка")
        n = D.q1("SELECT COUNT(*) AS n FROM proctor_snapshots WHERE attempt_id = ?", (att["id"],))["n"]
        if n < MAX_SNAPSHOTS:
            D.ex("INSERT INTO proctor_snapshots(attempt_id, at, image) VALUES (?,?,?)", (att["id"], _now(), snapshot))
    D.ex("UPDATE test_attempts SET proctor = ? WHERE id = ?", (json.dumps(state), att["id"]))
    risk = _recompute(att["id"])
    terminated = risk >= TERMINATE_AT
    if terminated:
        _terminate(att)
    return {"risk": risk, "flagged": risk >= FLAG_AT, "terminated": terminated, "active": not terminated,
            "warning": _warning(risk)}


def _warning(risk: float) -> Optional[str]:
    if risk >= TERMINATE_AT * 0.75:
        return "Осторожно: ещё несколько нарушений — и тест будет прекращён."
    if risk >= FLAG_AT:
        return "Прохождение отмечено для проверки модератором."
    return None


def finalize(att: dict, times: dict, questions: list, duration_sec: float) -> float:
    """Серверные проверки при сдаче: скорость ответов и пропуски в съёмке. Возвращает итоговый риск."""
    fast = [q for q in questions if q["level"] >= 4 and 0 <= float(times.get(q["id"], 99)) < 6.0]
    if len(fast) >= 3:
        _add(att["id"], "fast_answers", {"count": len(fast)}, weight=min(12.0, 4.0 * (len(fast) - 2)))
    if current_app.config["PROCTOR_CAMERA_REQUIRED"] and duration_sec >= 180:
        n = D.q1("SELECT COUNT(*) AS n FROM proctor_snapshots WHERE attempt_id = ?", (att["id"],))["n"]
        expected = (duration_sec / 60.0) * 0.5
        if n < expected:
            _add(att["id"], "camera_gaps", {"snapshots": n, "expected": int(expected)})
    D.ex("UPDATE test_attempts SET times = ? WHERE id = ?", (json.dumps({k: round(float(v), 1) for k, v in times.items() if isinstance(v, (int, float))}), att["id"]))
    return _recompute(att["id"])


def summary(att_id: int) -> dict:
    row = D.q1("SELECT risk, review_state, status FROM test_attempts WHERE id = ?", (att_id,))
    counts: dict = {}
    for r in D.qa("SELECT kind, COUNT(*) AS n FROM proctor_events WHERE attempt_id = ? AND weight > 0 GROUP BY kind", (att_id,)):
        counts[r["kind"]] = r["n"]
    snaps = D.q1("SELECT COUNT(*) AS n FROM proctor_snapshots WHERE attempt_id = ?", (att_id,))["n"]
    return {"risk": row["risk"], "state": row["review_state"], "flag_at": FLAG_AT, "terminate_at": TERMINATE_AT, "snapshots": snaps,
            "events": [{"kind": k, "label": LABELS.get(k, k), "count": n} for k, n in sorted(counts.items(), key=lambda kv: -kv[1])],
            "terminated": row["status"] == "terminated"}


def purge_old(days: int) -> int:
    """Удаляет снимки старше срока хранения (минимизация биометрических данных, 152-ФЗ). Возвращает число удалённых."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    cur = D.db().execute("DELETE FROM proctor_snapshots WHERE at < ? AND attempt_id NOT IN "
                         "(SELECT id FROM test_attempts WHERE review_state = 'flagged')", (cutoff,))
    D.db().commit()
    return cur.rowcount


def jpeg_bytes(data_url: str) -> bytes:
    return base64.b64decode(data_url.split(",", 1)[1])


# ---------------------------------------------------------------------------------------------- модерация
def queue(state: str = "flagged", limit: int = 100) -> list:
    where = {"flagged": "a.review_state = 'flagged'", "decided": "a.review_state IN ('cleared','annulled')", "all": "a.risk > 0"}[state]
    rows = D.qa(f"""SELECT a.id, a.spec, a.target_grade, a.status, a.started_at, a.finished_at, a.risk, a.review_state, a.ratio, a.passed,
                          c.pseudo_code,
                          (SELECT COUNT(*) FROM proctor_snapshots s WHERE s.attempt_id = a.id) AS snaps,
                          (SELECT COUNT(*) FROM proctor_events e WHERE e.attempt_id = a.id AND e.weight > 0) AS evs
                   FROM test_attempts a JOIN candidates c ON c.user_id = a.user_id
                   WHERE {where} AND a.status != 'active' ORDER BY a.risk DESC, a.id DESC LIMIT ?""", (limit,))
    return [dict(r) for r in rows]


def detail(att_id: int) -> dict:
    a = D.q1("""SELECT a.*, c.pseudo_code FROM test_attempts a JOIN candidates c ON c.user_id = a.user_id WHERE a.id = ?""", (att_id,))
    if a is None:
        raise ApiError(404, "not_found", "Попытка не найдена")
    events = [{"at": r["at"], "kind": r["kind"], "label": LABELS.get(r["kind"], r["kind"]), "weight": r["weight"], "meta": D.jl(r["meta"], {})}
              for r in D.qa("SELECT * FROM proctor_events WHERE attempt_id = ? ORDER BY id", (att_id,))]
    snaps = [{"id": r["id"], "at": r["at"]} for r in D.qa("SELECT id, at FROM proctor_snapshots WHERE attempt_id = ? ORDER BY id", (att_id,))]
    log = [dict(r) for r in D.qa("SELECT decision, comment, at FROM moderation_log WHERE attempt_id = ? ORDER BY id", (att_id,))]
    return {"id": a["id"], "code": a["pseudo_code"], "spec": a["spec"], "grade": a["target_grade"], "status": a["status"], "started_at": a["started_at"],
            "finished_at": a["finished_at"], "ratio": a["ratio"], "passed": None if a["passed"] is None else bool(a["passed"]),
            "risk": a["risk"], "state": a["review_state"], "events": events, "snapshots": snaps, "decisions": log,
            "times": D.jl(a["times"], {})}


def decide(att_id: int, moderator_id: int, decision: str, comment: str) -> dict:
    a = D.q1("SELECT * FROM test_attempts WHERE id = ?", (att_id,))
    if a is None:
        raise ApiError(404, "not_found", "Попытка не найдена")
    if a["status"] == "active":
        raise ApiError(409, "attempt_active", "Попытка ещё идёт")
    now = _now()
    if decision == "clear":
        D.ex("UPDATE test_attempts SET review_state = 'cleared' WHERE id = ?", (att_id,))
    else:
        D.ex("UPDATE test_attempts SET review_state = 'annulled', passed = 0 WHERE id = ?", (att_id,))
        c = D.q1("SELECT * FROM candidates WHERE user_id = ?", (a["user_id"],))
        if c and c["category_attempt_id"] == att_id:
            D.ex("""UPDATE candidates SET spec = NULL, grade = NULL, best_score = 0, category_assigned_at = NULL, stack_confirmed = '[]',
                    category_attempt_id = NULL WHERE user_id = ?""", (a["user_id"],))
            D.ex("INSERT INTO grade_history(user_id, spec, old_grade, new_grade, reason, at) VALUES (?,?,?,?,?,?)",
                 (a["user_id"], c["spec"], c["grade"], None, "annulled", now))
    D.ex("INSERT INTO moderation_log(attempt_id, moderator_id, decision, comment, at) VALUES (?,?,?,?,?)", (att_id, moderator_id, decision, comment, now))
    return detail(att_id)
