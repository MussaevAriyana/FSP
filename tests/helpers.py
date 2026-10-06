import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
from app import db as D  # noqa: E402

REGISTRY = [
    {"fsp_id": "FSP-100001", "email": "fsp.star@example.com", "full_name": "Мария Звёздная", "events": [
        {"id": 1, "title": "Открытый кубок ФСП", "type": "contest", "date": "2026-06-10", "place": 4, "participants": 120, "points": 90},
        {"id": 2, "title": "Хакатон ФСП: город", "type": "hackathon", "date": "2026-03-01", "place": 2, "participants": 40, "points": 80},
        {"id": 3, "title": "Весенняя лига", "type": "contest", "date": "2025-12-01", "place": 15, "participants": 200, "points": 50},
        {"id": 4, "title": "Школа ФСП", "type": "training", "date": "2025-10-01", "place": 9, "participants": 60, "points": 30}]},
    {"fsp_id": "FSP-100002", "email": "someone.else@example.com", "full_name": "Другой Участник", "events": [
        {"id": 5, "title": "Открытый кубок ФСП", "type": "contest", "date": "2026-06-10", "place": 80, "participants": 120, "points": 10}]},
]


def make_app(tmp_path):
    reg = tmp_path / "reg.json"
    reg.write_text(json.dumps(REGISTRY, ensure_ascii=False), encoding="utf-8")
    return create_app({"TESTING": True, "DB_PATH": str(tmp_path / "t.db"), "FSP_REGISTRY_FILE": str(reg), "SECRET_KEY": "test-secret",
                       "DEV_MODE": True, "GRADE_COOLDOWN_DAYS": 90})


class Actor:
    def __init__(self, client, app, email, role, **extra):
        self.c, self.app, self.email, self.role = client, app, email, role
        r = client.post("/api/auth/register", json={"email": email, "password": "Passw0rd!x", "role": role, "consent_pd": True,
                                                    "full_name": extra.get("full_name", ""), "company_name": extra.get("company_name", "")})
        assert r.status_code == 201, r.json
        self.dev_token = r.json["dev_token"]
        self.uid = None
        self.token = None

    def confirm(self):
        r = self.c.post("/api/auth/confirm", json={"token": self.dev_token})
        assert r.status_code == 200, r.json
        self.token, self.uid = r.json["token"], r.json["user"]["id"]
        return self

    def h(self):
        return {"Authorization": f"Bearer {self.token}"}

    def get(self, url, **kw):
        return self.c.get(url, headers=self.h(), **kw)

    def post(self, url, json=None, **kw):
        return self.c.post(url, headers=self.h(), json=json, **kw)

    def put(self, url, json=None):
        return self.c.put(url, headers=self.h(), json=json)

    def delete(self, url, json=None):
        return self.c.delete(url, headers=self.h(), json=json)


def make_factory(client, app):
    def _make(email, role, **extra):
        return Actor(client, app, email, role, **extra).confirm()
    return _make


def solve(app, actor, spec, grade, correct=True, minutes_ago=15):
    """Проходит тест «как компетентный кандидат» (ответы берутся из БД) и завершает его."""
    r = actor.post("/api/candidate/tests", {"spec": spec, "grade": grade})
    assert r.status_code == 201, r.json
    aid = r.json["id"]
    with app.app_context():
        att = D.q1("SELECT * FROM test_attempts WHERE id = ?", (aid,))
        qs = json.loads(att["questions"])
        started = (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
        D.ex("UPDATE test_attempts SET started_at = ? WHERE id = ?", (started, aid))
    answers = {q["id"]: (q["answer"] if correct else (q["answer"] + 1 if q["kind"] == "choice" else -999)) for q in qs}
    return actor.post(f"/api/candidate/tests/{aid}/finish", {"answers": answers, "blur_count": 0}), aid


def onboard(app, cand, spec="backend", grade="junior", publish=True, full_name="Иван Тестов"):
    """Профиль → опрос → тест → публикация."""
    assert cand.put("/api/candidate/profile", {"full_name": full_name, "phone": "+79990001122", "city": "Казань", "headline": "Разработчик",
                                              "experience_years": 1.5, "stack_declared": ["python", "sql", "docker"]}).status_code == 200
    assert cand.post("/api/candidate/survey", {"industry": "Финтех и банки", "spec": spec, "stack": ["python", "sql"], "grade": grade, "format": "remote"}).status_code == 200
    r, aid = solve(app, cand, spec, grade)
    assert r.status_code == 200 and r.json["passed"], r.json
    if publish:
        assert cand.put("/api/candidate/settings", {"consent_publish": True, "privacy": {}}).status_code == 200
    return r.json


def set_db(app, sql, args=()):
    with app.app_context():
        D.ex(sql, args)
