"""Сквозные тесты: сценарий из ТЗ и обязательные правила видимости/доступа."""
import io
import json
from datetime import datetime, timedelta, timezone

from helpers import onboard, set_db, solve

from app import db as D


def ts(days_ago):
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


# ------------------------------------------------------------------------------ регистрация и доступ
def test_registration_requires_consent_and_email_confirmation(client):
    r = client.post("/api/auth/register", json={"email": "a@b.ru", "password": "Passw0rd1", "role": "candidate", "consent_pd": False})
    assert r.status_code == 422
    r = client.post("/api/auth/register", json={"email": "a@b.ru", "password": "Passw0rd1", "role": "candidate", "consent_pd": True})
    assert r.status_code == 201
    login = client.post("/api/auth/login", json={"email": "a@b.ru", "password": "Passw0rd1"})
    assert login.status_code == 403 and login.json["error"] == "email_not_confirmed"
    assert client.post("/api/auth/confirm", json={"token": r.json["dev_token"]}).status_code == 200
    assert client.post("/api/auth/login", json={"email": "a@b.ru", "password": "Passw0rd1"}).status_code == 200
    assert client.post("/api/auth/login", json={"email": "a@b.ru", "password": "wrong"}).status_code == 401
    assert client.post("/api/auth/register", json={"email": "a@b.ru", "password": "Passw0rd1", "role": "candidate", "consent_pd": True}).status_code == 409


def test_role_separation(make):
    cand, emp = make("c@x.ru", "candidate"), make("e@x.ru", "employer", company_name="Acme")
    assert cand.get("/api/employer/candidates").status_code == 403
    assert emp.get("/api/candidate/me").status_code == 403
    assert emp.c.get("/api/employer/candidates").status_code == 401


# ------------------------------------------------------------------------------ обязательный путь кандидата
def test_test_requires_survey_and_assigns_category_only_by_test(app, make):
    cand = make("c@x.ru", "candidate")
    assert cand.post("/api/candidate/tests", {"spec": "backend", "grade": "junior"}).status_code == 409
    cand.post("/api/candidate/survey", {"industry": "Другое", "spec": "backend", "grade": "senior", "stack": ["python"]})
    state = cand.get("/api/candidate/me").json
    assert state["category"]["grade"] is None, "самоописание/опрос не должны присваивать категорию"

    r, _ = solve(app, cand, "backend", "senior", correct=False)
    assert r.json["passed"] is False
    assert r.json["outcome"]["suggest_lower"]["grade"] == "middle"       # предлагаем тест на уровень ниже
    assert cand.get("/api/candidate/me").json["category"]["grade"] is None

    r, _ = solve(app, cand, "backend", "middle", correct=True)
    assert r.json["passed"] and r.json["outcome"]["new_category"]["grade"] == "middle"
    assert cand.get("/api/candidate/me").json["category"]["label"] == "Backend · Middle"


def test_tests_are_unique_per_attempt(app, make):
    cand = make("c@x.ru", "candidate")
    cand.post("/api/candidate/survey", {"industry": "Другое", "spec": "backend", "grade": "junior"})
    seen = []
    for _ in range(3):
        r = cand.post("/api/candidate/tests", {"spec": "backend", "grade": "junior"})
        aid = r.json["id"]
        seen.append(json.dumps([q["prompt"] for q in r.json["questions"]], ensure_ascii=False))
        assert "answer" not in json.dumps(r.json)                         # ответы не утекают клиенту
        set_db(app, "UPDATE test_attempts SET status = 'finished' WHERE id = ?", (aid,))
    assert len(set(seen)) == 3


def test_failed_attempt_never_downgrades_and_grade_change_is_limited(app, make):
    cand = make("c@x.ru", "candidate")
    onboard(app, cand, "backend", "middle")
    # проваленный тест на старший грейд внутри окна калибровки — категория не меняется
    r, _ = solve(app, cand, "backend", "senior", correct=False)
    assert r.json["passed"] is False
    assert cand.get("/api/candidate/me").json["category"]["grade"] == "middle"
    # окно калибровки (24 ч) закрыто → смена возможна не чаще раза в 90 дней
    set_db(app, "UPDATE candidates SET category_assigned_at = ? WHERE user_id = ?", (ts(10), cand.uid))
    blocked = cand.post("/api/candidate/tests", {"spec": "backend", "grade": "senior"})
    assert blocked.status_code == 409 and blocked.json["error"] == "grade_change_limited"
    assert cand.post("/api/candidate/tests", {"spec": "backend", "grade": "middle"}).status_code == 201   # повтор своего грейда доступен
    set_db(app, "UPDATE test_attempts SET status = 'finished' WHERE user_id = ?", (cand.uid,))
    set_db(app, "UPDATE candidates SET category_assigned_at = ? WHERE user_id = ?", (ts(100), cand.uid))
    r, _ = solve(app, cand, "backend", "senior", correct=True)
    assert r.json["passed"] and cand.get("/api/candidate/me").json["category"]["grade"] == "senior"
    # после смены снова действует ограничение
    assert cand.post("/api/candidate/tests", {"spec": "backend", "grade": "junior"}).status_code == 409


def test_suspicious_speed_is_flagged(app, make):
    cand = make("c@x.ru", "candidate")
    cand.post("/api/candidate/survey", {"industry": "Другое", "spec": "qa", "grade": "junior"})
    r, _ = solve(app, cand, "qa", "junior", correct=True, minutes_ago=0)
    assert r.json["integrity"]["review"] is True and "too_fast" in r.json["integrity"]["flags"]


# ------------------------------------------------------------------------------ ФСП
def test_fsp_link_and_empty_history(app, make):
    cand = make("fsp.star@example.com", "candidate")
    assert cand.post("/api/candidate/fsp", {"fsp_id": "FSP-100002"}).status_code == 403      # чужой ID (другой e-mail)
    assert cand.post("/api/candidate/fsp", {"fsp_id": "FSP-999999"}).status_code == 404
    r = cand.post("/api/candidate/fsp", {"fsp_id": "FSP-100001"})
    assert r.status_code == 200 and r.json["fsp"]["summary"]["events_count"] == 4
    other = make("nofsp@x.ru", "candidate")
    st = other.get("/api/candidate/me").json
    assert st["fsp"]["linked"] is False and st["fsp"]["summary"] is None                     # нет истории — штатно
    assert other.post("/api/candidate/fsp", {"fsp_id": "FSP-100001"}).status_code == 403


# ------------------------------------------------------------------------------ подбор и выход на контакт
def _setup_market(app, make):
    star = make("fsp.star@example.com", "candidate")
    star.post("/api/candidate/fsp", {"fsp_id": "FSP-100001"})
    plain = make("plain@x.ru", "candidate")
    onboard(app, star, "backend", "middle", full_name="Мария Звёздная")
    onboard(app, plain, "backend", "middle", full_name="Пётр Простов")
    frontend = make("front@x.ru", "candidate")
    onboard(app, frontend, "frontend", "middle", full_name="Фёдор Фронтов")
    emp = make("hr@acme.ru", "employer", company_name="Acme")
    return star, plain, frontend, emp


def test_matching_is_category_based_explainable_and_hides_contacts(app, make):
    star, plain, frontend, emp = _setup_market(app, make)
    need = emp.post("/api/employer/needs", {"title": "Backend в платежи", "spec": "backend", "grade": "middle", "stack": ["python", "sql"]})
    assert need.status_code == 201
    r = emp.get(f"/api/employer/needs/{need.json['id']}/matches")
    assert r.status_code == 200
    items = r.json["items"]
    assert {i["code"] for i in items} == {star.get("/api/candidate/me").json["code"], plain.get("/api/candidate/me").json["code"]}   # frontend не попал
    assert items[0]["code"] == star.get("/api/candidate/me").json["code"], "при равной категории выше кандидат с историей ФСП"
    assert items[0]["match"]["score"] > items[1]["match"]["score"]
    assert {x["factor"] for x in items[0]["match"]["reasons"]} >= {"category", "test", "stack", "fsp"}
    assert r.json["recommended_categories"][0]["label"] == "Backend · Middle"
    blob = json.dumps(r.json, ensure_ascii=False)
    for secret in ("Мария", "Простов", "plain@x.ru", "fsp.star@example.com", "+7999"):
        assert secret not in blob, f"утечка контактных данных: {secret}"
    assert all(i["revealed"] is False and "contacts" not in i for i in items)


def test_search_filters_keep_base_selection(app, make):
    star, plain, frontend, emp = _setup_market(app, make)
    need = emp.post("/api/employer/needs", {"title": "Backend", "spec": "backend", "grade": "middle", "stack": []}).json
    base = emp.get(f"/api/employer/needs/{need['id']}/matches").json
    filtered = emp.get(f"/api/employer/needs/{need['id']}/matches?has_fsp=true").json
    assert filtered["total"] == 1 and filtered["base_total"] == base["total"] == 2
    bank = emp.get("/api/employer/candidates?spec=frontend").json
    assert bank["total"] == 1 and bank["items"][0]["category"]["spec"] == "frontend"
    assert emp.get("/api/employer/candidates?grade=expert").status_code == 422


def test_candidate_without_consent_or_hidden_is_not_visible(app, make):
    cand = make("c@x.ru", "candidate")
    onboard(app, cand, "backend", "junior", publish=False)
    emp = make("hr@acme.ru", "employer", company_name="Acme")
    assert emp.get("/api/employer/candidates").json["total"] == 0
    cand.put("/api/candidate/settings", {"consent_publish": True, "privacy": {"visible_in_bank": True, "show_stack": False, "show_city": False}})
    res = emp.get("/api/employer/candidates").json
    assert res["total"] == 1 and res["items"][0]["stack_confirmed"] == [] and res["items"][0]["city"] is None
    assert emp.get("/api/employer/candidates?city=Казань").json["total"] == 0            # по скрытому городу не ищется
    cand.put("/api/candidate/settings", {"consent_publish": True, "privacy": {"visible_in_bank": False}})
    assert emp.get("/api/employer/candidates").json["total"] == 0


def test_invite_flow_salary_required_statuses_and_contact_reveal(app, make):
    star, plain, frontend, emp = _setup_market(app, make)
    code = plain.get("/api/candidate/me").json["code"]
    base = {"candidate_code": code, "title": "Backend-разработчик", "description": "Платёжный сервис, команда из 6 человек", "contact_method": "hr@acme.ru"}
    assert emp.post("/api/employer/invites", base).status_code == 422                                                     # зарплата обязательна
    assert emp.post("/api/employer/invites", {**base, "salary_from": 300000, "salary_to": 200000}).status_code == 422
    r = emp.post("/api/employer/invites", {**base, "salary_from": 200000, "salary_to": 300000})
    assert r.status_code == 201 and r.json["status"] == "sent"
    iid = r.json["id"]
    assert emp.post("/api/employer/invites", {**base, "salary_from": 200000, "salary_to": 300000}).status_code == 409    # повтор, пока нет ответа

    inv = plain.get("/api/candidate/invites").json["items"]
    assert len(inv) == 1 and inv[0]["salary_from"] == 200000 and inv[0]["salary_to"] == 300000 and inv[0]["company"]["name"] == "Acme"
    assert inv[0]["status"] == "sent"
    assert plain.get(f"/api/candidate/invites/{iid}").json["status"] == "viewed"
    mine = emp.get("/api/employer/invites").json["items"][0]
    assert mine["status"] == "viewed" and mine["candidate"]["revealed"] is False and "contacts" not in mine["candidate"]

    assert plain.post(f"/api/candidate/invites/{iid}/decision", {"decision": "accept"}).json["status"] == "accepted"
    mine = emp.get("/api/employer/invites").json["items"][0]
    assert mine["status"] == "accepted" and mine["candidate"]["contacts"]["email"] == "plain@x.ru"
    assert mine["candidate"]["contacts"]["full_name"] == "Пётр Простов"
    assert plain.post(f"/api/candidate/invites/{iid}/decision", {"decision": "decline"}).status_code == 409
    # теперь в банке контакты тоже открыты именно этому работодателю
    assert emp.get(f"/api/employer/candidates/{code}").json["contacts"]["phone"] == "+79990001122"
    # другой работодатель по-прежнему ничего не видит
    other = make("hr@other.ru", "employer", company_name="Other")
    assert "contacts" not in other.get(f"/api/employer/candidates/{code}").json


def test_decline_keeps_contacts_hidden_and_isolation(app, make):
    star, plain, frontend, emp = _setup_market(app, make)
    code = star.get("/api/candidate/me").json["code"]
    r = emp.post("/api/employer/invites", {"candidate_code": code, "title": "Backend", "description": "Описание предложения", "contact_method": "tg @acme",
                                           "salary_from": 150000, "salary_to": 250000})
    iid = r.json["id"]
    assert plain.get(f"/api/candidate/invites/{iid}").status_code == 404           # чужое приглашение не видно
    assert plain.post(f"/api/candidate/invites/{iid}/decision", {"decision": "accept"}).status_code == 404
    star.post(f"/api/candidate/invites/{iid}/decision", {"decision": "decline"})
    card = emp.get("/api/employer/invites").json["items"][0]["candidate"]
    assert card["revealed"] is False and "contacts" not in card
    assert emp.delete(f"/api/employer/invites/{iid}").status_code == 409            # решение принято — отозвать нельзя


# ------------------------------------------------------------------------------ вакансии, отклики, микро-задачи
def test_vacancies_and_applications(app, make):
    star, plain, frontend, emp = _setup_market(app, make)
    v = {"title": "Python-разработчик", "description": "Описание", "spec": "backend", "grade": "middle", "stack": ["python"], "salary_from": 180000, "salary_to": 260000}
    assert emp.post("/api/employer/vacancies", {k: x for k, x in v.items() if k != "salary_from"}).status_code == 422
    vid = emp.post("/api/employer/vacancies", v).json["id"]
    lst = plain.get("/api/candidate/vacancies").json["items"]
    assert lst[0]["salary_from"] == 180000 and lst[0]["fit"] == 1.0
    assert plain.post(f"/api/candidate/vacancies/{vid}/apply", {"message": "Здравствуйте"}).status_code == 201
    assert plain.post(f"/api/candidate/vacancies/{vid}/apply", {}).status_code == 409
    apps = emp.get(f"/api/employer/vacancies/{vid}/applications").json["items"]
    assert apps[0]["candidate"]["contacts"]["email"] == "plain@x.ru"                 # откликнулся сам → контакты открыты
    emp.post(f"/api/employer/applications/{apps[0]['id']}/status", {"status": "invited_to_talk"})
    assert plain.get("/api/candidate/applications").json["items"][0]["status"] == "invited_to_talk"
    emp.patch = None
    assert emp.c.patch(f"/api/employer/vacancies/{vid}/status", headers=emp.h(), json={"status": "closed"}).status_code == 200
    assert plain.get("/api/candidate/vacancies").json["total"] == 0


def test_microtasks_cycle(app, make):
    star, plain, frontend, emp = _setup_market(app, make)
    tid = emp.post("/api/employer/microtasks", {"title": "Идемпотентность платежей", "body": "Как бы вы обеспечили идемпотентность API платежей?",
                                                "spec": "backend", "grade": "middle", "kind": "approach"}).json["id"]
    mine = plain.get("/api/candidate/microtasks").json["items"]
    assert len(mine) == 1 and mine[0]["status"] == "assigned"
    assert frontend.get("/api/candidate/microtasks").json["items"] == []             # другая специализация
    assert plain.post(f"/api/candidate/microtasks/{tid}/answer", {"answer": "Idempotency-Key + уникальный индекс"}).status_code == 200
    subs = emp.get(f"/api/employer/microtasks/{tid}/submissions").json["items"]
    assert len(subs) == 1 and "contacts" not in subs[0]["candidate"]
    assert emp.post(f"/api/employer/assignments/{subs[0]['assignment_id']}/rate", {"rating": 5, "feedback": "Отлично"}).status_code == 200
    assert plain.get("/api/candidate/microtasks").json["items"][0]["rating"] == 5


# ------------------------------------------------------------------------------ PDF, права субъекта, OpenAPI
def test_pdf_generation_and_parsing(app, make):
    cand = make("c@x.ru", "candidate")
    onboard(app, cand, "backend", "junior", full_name="Иван Петров")
    pdf = cand.get("/api/candidate/profile.pdf")
    assert pdf.status_code == 200 and pdf.data.startswith(b"%PDF")
    r = cand.c.post("/api/candidate/resume/parse", headers=cand.h(), data={"file": (io.BytesIO(pdf.data), "cv.pdf")}, content_type="multipart/form-data")
    assert r.status_code == 200 and r.json["full_name"] == "Иван Петров" and r.json["email"] == "c@x.ru" and "python" in r.json["stack_declared"]
    bad = cand.c.post("/api/candidate/resume/parse", headers=cand.h(), data={"file": (io.BytesIO(b"hello"), "cv.pdf")}, content_type="multipart/form-data")
    assert bad.status_code == 400


def test_account_deletion_and_export(app, make):
    cand = make("c@x.ru", "candidate")
    onboard(app, cand, "backend", "junior")
    assert cand.get("/api/candidate/export").json["account"]["email"] == "c@x.ru"
    assert cand.delete("/api/auth/account", {"password": "bad"}).status_code == 403
    assert cand.delete("/api/auth/account", {"password": "Passw0rd!x"}).status_code == 200
    emp = make("hr@acme.ru", "employer", company_name="Acme")
    assert emp.get("/api/employer/candidates").json["total"] == 0
    with app.app_context():
        assert D.q1("SELECT COUNT(*) AS n FROM test_attempts")["n"] == 0                # каскадное удаление


def test_openapi_covers_all_routes(client, app):
    spec = client.get("/openapi.json").json
    declared = {(path, m) for path, ms in spec["paths"].items() for m in ms}
    flask_rules = {(__import__("re").sub(r"<(?:\w+:)?(\w+)>", r"{\1}", r.rule), m.lower()) for r in app.url_map.iter_rules()
                   for m in r.methods if m in ("GET", "POST", "PUT", "PATCH", "DELETE") and r.rule.startswith("/api/")}
    assert flask_rules <= declared, flask_rules - declared
    assert spec["components"]["securitySchemes"]["bearerAuth"]
