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
    assert cand.post("/api/candidate/tests", {"spec": "backend", "grade": "junior", "consent_proctoring": True, "camera_ready": True}).status_code == 409
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
        r = cand.post("/api/candidate/tests", {"spec": "backend", "grade": "junior", "consent_proctoring": True, "camera_ready": True})
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
    blocked = cand.post("/api/candidate/tests", {"spec": "backend", "grade": "senior", "consent_proctoring": True, "camera_ready": True})
    assert blocked.status_code == 409 and blocked.json["error"] == "grade_change_limited"
    assert cand.post("/api/candidate/tests", {"spec": "backend", "grade": "middle", "consent_proctoring": True, "camera_ready": True}).status_code == 201   # повтор своего грейда доступен
    set_db(app, "UPDATE test_attempts SET status = 'finished' WHERE user_id = ?", (cand.uid,))
    set_db(app, "UPDATE candidates SET category_assigned_at = ? WHERE user_id = ?", (ts(100), cand.uid))
    r, _ = solve(app, cand, "backend", "senior", correct=True)
    assert r.json["passed"] and cand.get("/api/candidate/me").json["category"]["grade"] == "senior"
    # после смены снова действует ограничение
    assert cand.post("/api/candidate/tests", {"spec": "backend", "grade": "junior", "consent_proctoring": True, "camera_ready": True}).status_code == 409


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


# ------------------------------------------------------------------------------ прокторинг, модерация, каталог, подвал
JPEG = ("data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDABQODxIPDRQSEBIXFRQYHjIhHhwcHj0sLiQySUBMS0dARkVQWnNiUFVtVkVGZIhlbXd7gYKB"
        "TmCNl4x9lnN+gXz/wAARCAAwAEADASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/9oADAMBAAIRAxEAPwDLooortLCiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKAP/2Q==")


def _survey(cand, spec="backend", grade="junior"):
    cand.put("/api/candidate/profile", {"full_name": "Иван Тестов"})
    assert cand.post("/api/candidate/survey", {"industry": "Финтех и банки", "spec": spec, "stack": ["python"], "grade": grade, "format": "remote"}).status_code == 200


def test_test_start_requires_proctoring_consent_and_camera(app, make):
    cand = make("p1@x.ru", "candidate")
    _survey(cand)
    body = {"spec": "backend", "grade": "junior"}
    r = cand.post("/api/candidate/tests", {**body, "camera_ready": True})
    assert r.status_code == 422 and r.json["error"] == "proctoring_consent_required"
    r = cand.post("/api/candidate/tests", {**body, "consent_proctoring": True})
    assert r.status_code == 422 and r.json["error"] == "camera_required"
    r = cand.post("/api/candidate/tests", {**body, "consent_proctoring": True, "camera_ready": True})
    assert r.status_code == 201 and r.json["proctoring"]["camera_required"] is True
    assert len(r.json["questions"]) == 20


def test_proctoring_flags_terminates_and_moderator_can_annul(app, make):
    cand = make("p2@x.ru", "candidate")
    _survey(cand)
    r = cand.post("/api/candidate/tests", {"spec": "backend", "grade": "junior", "consent_proctoring": True, "camera_ready": True})
    aid = r.json["id"]
    push = lambda events, snap=None, cid="tab-aaaaaa": cand.post(f"/api/candidate/tests/{aid}/proctor", {"cid": cid, "events": events, "snapshot": snap, "camera": True})
    ok = push([], JPEG)
    assert ok.status_code == 200 and ok.json["risk"] == 0 and not ok.json["flagged"]
    assert push([], "data:text/html;base64,AAAA").status_code == 422                       # не JPEG — отказ
    assert push([{"kind": "multi_session"}]).json["risk"] == 0                               # серверные виды от клиента не принимаются
    r2 = push([{"kind": "paste"}] * 3)                                                       # 3 × 4 = 12 → отметка
    assert r2.json["flagged"] is True and r2.json["terminated"] is False
    assert push([], cid="tab-bbbbbb").json["risk"] > r2.json["risk"]                         # вторая вкладка — нарушение
    # честный кандидат даже с отметкой: попытка идёт, результат засчитывается, но вес профиля снижен до решения модератора
    with app.app_context():
        qs = json.loads(D.q1("SELECT questions FROM test_attempts WHERE id = ?", (aid,))["questions"])
        D.ex("UPDATE test_attempts SET started_at = ? WHERE id = ?", ((datetime.now(timezone.utc) - timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ"), aid))
    fin = cand.post(f"/api/candidate/tests/{aid}/finish", {"answers": {q["id"]: q["answer"] for q in qs}, "blur_count": 0})
    assert fin.status_code == 200 and fin.json["passed"] and fin.json["outcome"]["integrity_review"] is True
    assert cand.get("/api/candidate/me").json["category"]["grade"] == "junior"
    # модератор
    from scripts.create_moderator import create
    with app.app_context():
        create("mod@x.ru", "ModPass123")
    login = app.test_client().post("/api/auth/login", json={"email": "mod@x.ru", "password": "ModPass123"})
    assert login.status_code == 200 and login.json["user"]["role"] == "moderator"
    H = {"Authorization": "Bearer " + login.json["token"]}
    c = app.test_client()
    assert cand.get("/api/moderator/queue").status_code == 403                               # кандидату кабинет модератора недоступен
    q = c.get("/api/moderator/queue", headers=H).json
    assert [i["id"] for i in q["items"]] == [aid]
    d = c.get(f"/api/moderator/attempts/{aid}", headers=H).json
    assert d["snapshots"] and any(e["kind"] == "paste" for e in d["events"])
    img = c.get(f"/api/moderator/snapshots/{d['snapshots'][0]['id']}", headers=H)
    assert img.status_code == 200 and img.mimetype == "image/jpeg" and img.data[:2] == b"\xff\xd8"
    res = c.post(f"/api/moderator/attempts/{aid}/decision", headers=H, json={"decision": "annul", "comment": "Подсказки в кадре"})
    assert res.status_code == 200 and res.json["state"] == "annulled"
    assert cand.get("/api/candidate/me").json["category"]["grade"] is None                   # категория, присвоенная этой попыткой, снята


def test_proctoring_terminates_attempt_without_changing_category(app, make):
    cand = make("p3@x.ru", "candidate")
    _survey(cand)
    aid = cand.post("/api/candidate/tests", {"spec": "backend", "grade": "junior", "consent_proctoring": True, "camera_ready": True}).json["id"]
    out = None
    for _ in range(10):
        out = cand.post(f"/api/candidate/tests/{aid}/proctor", {"cid": "tab-cccccc", "events": [{"kind": "devtools"}] * 3 + [{"kind": "fullscreen_exit"}] * 6 + [{"kind": "tab_hidden"}] * 8}).json
        if out["terminated"]:
            break
    assert out["terminated"] is True
    st = cand.get(f"/api/candidate/tests/{aid}").json
    assert st["state"] == "finished" and st["passed"] is False and st["outcome"]["terminated"] is True
    assert cand.get("/api/candidate/me").json["category"]["grade"] is None
    assert cand.post(f"/api/candidate/tests/{aid}/finish", {"answers": {}}).status_code == 409


def test_technology_catalog_and_footer_data(client):
    tax = client.get("/api/taxonomy").json
    assert 140 <= len(tax["tech"]) <= 260 and len({t["id"] for t in tax["tech"]}) == len(tax["tech"])
    assert {"python", "kubernetes", "react", "postgresql", "playwright", "pytorch"} <= {t["id"] for t in tax["tech"]}
    about = client.get("/api/about").json
    assert about["name"] == "Федерация спортивного программирования" and about["disciplines"]


# ------------------------------------------------------------------------------ резюме, тренировка, награды, кошелёк, вакансии
def test_resume_is_saved_and_masked_for_employer_until_reveal(app, make):
    star, plain, frontend, emp = _setup_market(app, make)
    resume = {"summary": "Backend-разработчик", "desired_position": "Backend", "experience": [{"company": "СекретКом", "position": "Dev", "start": "2022-01", "end": "", "description": "API"}],
              "projects": [{"name": "Proj", "role": "lead", "link": "https://secret.example/p", "description": "d", "stack": ["python"]}],
              "education": [{"institution": "МГТУ им. Секрета", "degree": "Бакалавр", "specialty": "ИТ", "year_from": "2018", "year_to": "2022"}],
              "certificates": [{"kind": "diploma", "name": "Диплом ФСП", "issuer": "ФСП", "year": "2024", "link": "https://secret.example/c"}]}
    r = plain.put("/api/candidate/resume", resume)
    assert r.status_code == 200 and r.json["progress"]["percent"] == 100
    assert plain.get("/api/candidate/resume").json["experience"][0]["company"] == "СекретКом"
    code = plain.get("/api/candidate/me").json["code"]
    card = emp.get(f"/api/employer/candidates/{code}").json
    blob = json.dumps(card["resume"], ensure_ascii=False)
    assert "СекретКом" not in blob and "МГТУ" not in blob and "secret.example" not in blob
    assert card["resume"]["experience"][0]["position"] == "Dev"
    assert plain.get("/api/candidate/profile.pdf").status_code == 200


def test_practice_and_rewards(app, make):
    cand = make("pr@x.ru", "candidate")
    item = cand.post("/api/candidate/practice/next", {"spec": "backend", "level": 3}).json
    assert "answer" not in json.dumps(item) and item["level"] == 3
    again = cand.post("/api/candidate/practice/next", {"spec": "backend", "level": 3}).json
    assert again["id"] == item["id"]                                   # неотвеченное возвращается повторно
    with app.app_context():
        q = json.loads(D.q1("SELECT question FROM practice_items WHERE id = ?", (item["id"],))["question"])
    res = cand.post(f"/api/candidate/practice/{item['id']}/answer", {"answer": q["answer"]})
    assert res.status_code == 200 and res.json["ok"] is True and res.json["stats"]["solved"] == 1
    assert cand.post(f"/api/candidate/practice/{item['id']}/answer", {"answer": q["answer"]}).status_code == 409
    rw = cand.get("/api/candidate/achievements").json
    assert any(b["code"] == "practice_1" and b["earned"] for b in rw["badges"]) and rw["points"] >= 5
    assert cand.get("/api/candidate/me").json["category"]["grade"] is None   # тренировка категорию не меняет


def test_wallet_shop_expert_test_and_boost(app, make):
    cand = make("w@x.ru", "candidate")
    assert cand.get("/api/wallet").json["balance"] == 0
    assert cand.post("/api/wallet/buy", {"service": "profile_boost"}).status_code == 402
    assert cand.post("/api/wallet/buy", {"service": "vacancy_boost"}).status_code == 404         # услуга чужой роли
    assert cand.post("/api/wallet/topup", {"amount": 5000}).json["balance"] == 5000
    assert cand.post("/api/wallet/buy", {"service": "profile_boost"}).status_code == 201
    st = cand.get("/api/candidate/me").json
    assert st["badges"]["boosted"] is True and st["balance"] == 5000 - 299
    # экспертный тест: нужна категория и покупка
    assert cand.post("/api/candidate/tests", {"spec": "backend", "grade": "junior", "expert": True, "consent_proctoring": True, "camera_ready": True}).status_code in (409,)
    onboard(app, cand, "backend", "junior")
    body = {"spec": "backend", "grade": "junior", "expert": True, "consent_proctoring": True, "camera_ready": True}
    assert cand.post("/api/candidate/tests", body).status_code == 402
    assert cand.post("/api/wallet/buy", {"service": "expert_test"}).status_code == 201
    r = cand.post("/api/candidate/tests", body)
    assert r.status_code == 201 and r.json["kind"] == "expert" and len(r.json["questions"]) == 20
    aid = r.json["id"]
    with app.app_context():
        qs = json.loads(D.q1("SELECT questions FROM test_attempts WHERE id = ?", (aid,))["questions"])
        assert all(q["level"] >= 3 for q in qs) and sum(q["level"] == 5 for q in qs) >= 12
        D.ex("UPDATE test_attempts SET started_at = ? WHERE id = ?", ((datetime.now(timezone.utc) - timedelta(minutes=40)).strftime("%Y-%m-%dT%H:%M:%SZ"), aid))
    fin = cand.post(f"/api/candidate/tests/{aid}/finish", {"answers": {q["id"]: q["answer"] for q in qs}})
    assert fin.json["passed"] and fin.json["outcome"]["expert_passed"] is True
    me = cand.get("/api/candidate/me").json
    assert me["badges"]["expert"] is True and me["category"]["grade"] == "junior"            # категория не изменилась
    assert cand.post("/api/candidate/tests", body).status_code == 402                          # покупка израсходована


def test_vacancy_management_detail_and_boost(app, make):
    emp = make("hr@acme.ru", "employer", company_name="Acme")
    cand = make("c@x.ru", "candidate", full_name="Иван")
    body = {"title": "Backend Python", "description": "Делаем платежи", "requirements": "Python 3 года", "conditions": "ДМС", "city": "Казань",
            "employment": "full", "spec": "backend", "grade": "middle", "salary_from": 200000, "salary_to": 300000, "stack": ["python"], "work_format": "hybrid"}
    v = emp.post("/api/employer/vacancies", body).json
    assert emp.put(f"/api/employer/vacancies/{v['id']}", {**body, "title": "Backend Python (обновлено)", "conditions": "ДМС, remote"}).json["title"].endswith("(обновлено)")
    full = cand.get(f"/api/candidate/vacancies/{v['id']}").json
    assert full["requirements"] == "Python 3 года" and full["conditions"] == "ДМС, remote" and full["city"] == "Казань" and full["company"]["name"] == "Acme"
    emp.post("/api/wallet/topup", {"amount": 1000})
    assert emp.post("/api/wallet/buy", {"service": "vacancy_boost"}).status_code == 422          # нужна вакансия
    assert emp.post("/api/wallet/buy", {"service": "vacancy_boost", "vacancy_id": v["id"]}).status_code == 201
    assert cand.get("/api/candidate/vacancies").json["items"][0]["boosted"] is True
    assert emp.get("/api/employer/candidates?expert_only=true").status_code == 402
    assert emp.delete(f"/api/employer/vacancies/{v['id']}").status_code == 200
    assert cand.get(f"/api/candidate/vacancies/{v['id']}").status_code == 404


def test_avatar_and_support(app, make):
    cand = make("av@x.ru", "candidate", full_name="Аня")
    img = JPEG
    assert cand.put("/api/account/avatar", {"image": img}).status_code == 200
    assert cand.get("/api/auth/me").json["avatar"] == img
    assert cand.put("/api/account/avatar", {"image": "http://evil/x.png"}).status_code == 422
    t = cand.post("/api/support", {"subject": "Вопрос по тесту", "message": "Не работает камера в браузере"})
    assert t.status_code == 201
    from scripts.create_moderator import create
    with app.app_context():
        create("mod2@x.ru", "ModPass123")
    H = {"Authorization": "Bearer " + app.test_client().post("/api/auth/login", json={"email": "mod2@x.ru", "password": "ModPass123"}).json["token"]}
    c = app.test_client()
    assert c.post(f"/api/moderator/support/{t.json['id']}/reply", headers=H, json={"reply": "Разрешите доступ к камере"}).status_code == 200
    assert cand.get("/api/support").json["items"][0]["reply"].startswith("Разрешите")


def test_applications_edit_withdraw_and_reapply(app, make):
    emp = make("hr@acme.ru", "employer", company_name="Acme")
    cand = make("c@x.ru", "candidate", full_name="Иван")
    v = emp.post("/api/employer/vacancies", {"title": "Dev vacancy", "spec": "backend", "grade": "junior", "salary_from": 100000, "salary_to": 150000}).json
    a = cand.post(f"/api/candidate/vacancies/{v['id']}/apply", {"message": "привет"}).json
    assert cand.patch(f"/api/candidate/applications/{a['id']}", {"message": "обновлено"}).json["message"] == "обновлено"
    assert cand.get(f"/api/candidate/vacancies/{v['id']}").json["my_application_id"] == a["id"]
    assert cand.delete(f"/api/candidate/applications/{a['id']}").json["status"] == "withdrawn"
    assert cand.patch(f"/api/candidate/applications/{a['id']}", {"message": "x"}).status_code == 409
    assert cand.post(f"/api/candidate/vacancies/{v['id']}/apply", {"message": "снова"}).status_code in (200, 201)
    assert cand.post(f"/api/candidate/vacancies/{v['id']}/apply", {"message": "ещё"}).status_code == 409


def test_invite_stages_visible_to_candidate(app, make):
    star, plain, frontend, emp = _setup_market(app, make)
    code = plain.get("/api/candidate/me").json["code"]
    inv = emp.post("/api/employer/invites", {"candidate_code": code, "title": "Backend", "description": "Описание предложения", "contact_method": "hr@x.ru",
                                              "salary_from": 123457, "salary_to": 234569}).json                     # произвольные числа, не кратные шагу
    assert inv["salary_from"] == 123457
    st = emp.post(f"/api/employer/invites/{inv['id']}/stage", {"stage": "interview", "note": "Созвон в четверг"}).json
    assert st["stage"] == "interview" and st["stage_log"][-1]["note"] == "Созвон в четверг"
    seen = plain.get("/api/candidate/invites").json["items"][0]
    assert seen["stage"] == "interview"
    assert emp.post(f"/api/employer/invites/{inv['id']}/stage", {"stage": "bogus"}).status_code == 422
    emp.delete(f"/api/employer/invites/{inv['id']}")
    assert emp.post(f"/api/employer/invites/{inv['id']}/stage", {"stage": "offer"}).status_code == 409


def test_resume_extended_personal_visibility_and_pdf(app, make):
    star, plain, frontend, emp = _setup_market(app, make)
    code = plain.get("/api/candidate/me").json["code"]
    body = {"summary": "Backend", "desired_position": "Backend", "salary_expectation": 250000, "languages": [{"name": "Английский", "level": "B2"}],
            "links": {"github": "https://github.com/secret"}, "personal": {"birth_year": 1998, "marital_status": "married", "citizenship": "РФ"},
            "education": [{"institution": "ВУЗ", "level": "bachelor", "degree": "Бакалавр", "specialty": "ИТ", "year_from": "2016", "year_to": "2020"}]}
    r = plain.put("/api/candidate/resume", body).json
    assert r["advice"] and r["languages"][0]["level"] == "B2"
    card = emp.get(f"/api/employer/candidates/{code}").json["resume"]
    assert card["personal"] is None and card["salary_expectation"] == 250000 and card["links"] == {}      # личное скрыто по умолчанию
    priv = plain.get("/api/candidate/me").json["settings"]["privacy"]
    assert plain.put("/api/candidate/settings", {"consent_publish": True, "privacy": {**priv, "show_personal": True}}).status_code == 200
    card = emp.get(f"/api/employer/candidates/{code}").json["resume"]
    assert card["personal"]["marital_status"] == "married" and card["personal"]["age"] >= 25 and "birth_year" not in card["personal"]
    pdf = emp.c.get(f"/api/employer/candidates/{code}/resume.pdf", headers={"Authorization": f"Bearer {emp.token}"})
    assert pdf.status_code == 200 and pdf.data[:4] == b"%PDF"


def test_new_specializations_and_showcase(app, make, client):
    tax = client.get("/api/taxonomy").json
    assert len(tax["specs"]) >= 12 and {"mobile", "security", "fullstack", "embedded"} <= set(tax["specs"])
    emp = make("hr@acme.ru", "employer", company_name="Acme")
    r = emp.post("/api/employer/vacancies", {"title": "Mobile dev", "spec": "mobile", "grade": "middle", "salary_from": 150000, "salary_to": 250000, "stack": ["kotlin"]})
    assert r.status_code == 201
    show = client.get("/api/public/showcase").json
    assert show["vacancies"][0]["title"] == "Mobile dev" and "candidates" in show
    assert client.get("/api/health").json["build"]


def test_need_edit_invite_restore_and_call_passed(app, make):
    star, plain, frontend, emp = _setup_market(app, make)
    code = plain.get("/api/candidate/me").json["code"]
    need = emp.post("/api/employer/needs", {"title": "Backend в платежи", "spec": "backend", "grade": "middle", "stack": ["python"]}).json
    upd = emp.put(f"/api/employer/needs/{need['id']}", {"title": "Backend в биллинг", "spec": "backend", "grade": "senior", "stack": ["python", "sql"], "team_desc": "Команда 5 человек"})
    assert upd.status_code == 200 and upd.json["title"] == "Backend в биллинг" and upd.json["grade"] == "senior"
    assert make("hr@other.ru", "employer", company_name="Other").put(f"/api/employer/needs/{need['id']}", {"title": "Чужая", "spec": "backend", "grade": "middle"}).status_code == 404
    vac = emp.post("/api/employer/vacancies", {"title": "Новая вакансия", "description": "Описание", "spec": "backend", "grade": "middle", "stack": ["python"], "salary_from": 150000, "salary_to": 250000}).json
    inv = emp.post("/api/employer/invites", {"candidate_code": code, "title": "Новая вакансия", "description": "Платёжный сервис, команда", "contact_method": "hr@acme.ru",
                                              "salary_from": 150000, "salary_to": 250000, "vacancy_id": vac["id"], "need_id": need["id"]}).json
    mine = emp.get("/api/employer/invites").json["items"][0]
    assert mine["vacancy_title"] == "Новая вакансия" and mine["need_title"] == "Backend в биллинг"
    assert emp.post(f"/api/employer/invites/{inv['id']}/restore").status_code == 409            # вернуть можно только отозванное
    emp.delete(f"/api/employer/invites/{inv['id']}")
    assert plain.get("/api/candidate/invites").json["items"] == []
    r = emp.post(f"/api/employer/invites/{inv['id']}/restore")
    assert r.status_code == 200 and r.json["status"] == "sent"
    assert len(plain.get("/api/candidate/invites").json["items"]) == 1
    # отклик: новый статус «успешно прошёл созвон»
    plain.post(f"/api/candidate/vacancies/{vac['id']}/apply", {"message": "Хочу к вам"})
    app_id = emp.get(f"/api/employer/vacancies/{vac['id']}/applications").json["items"][0]["id"]
    assert emp.post(f"/api/employer/applications/{app_id}/status", {"status": "call_passed"}).json["status"] == "call_passed"
    assert plain.get("/api/candidate/applications").json["items"][0]["status"] == "call_passed"


def test_microtask_sent_by_fsp_id(app, make):
    star, plain, frontend, emp = _setup_market(app, make)
    body = {"title": "Адресное задание", "body": "Опишите, как ускорить отчёт", "spec": "backend", "grade": "middle", "kind": "approach"}
    assert emp.post("/api/employer/microtasks", {**body, "fsp_ids": ["не id!"]}).status_code == 422
    r = emp.post("/api/employer/microtasks", {**body, "fsp_ids": "fsp-100001, FSP-424242"})
    assert r.status_code == 201 and r.json["delivered"] == ["FSP-100001"] and r.json["not_found"] == ["FSP-424242"]
    mine = star.get("/api/candidate/microtasks").json["items"]
    assert len(mine) == 1 and mine[0]["targeted"] is True and mine[0]["title"] == "Адресное задание"
    assert plain.get("/api/candidate/microtasks").json["items"] == []                         # остальным адресное задание не назначается
    assert emp.get("/api/employer/microtasks").json["items"][0]["fsp_ids"] == ["FSP-100001", "FSP-424242"]


def test_hired_invite_lands_in_vacancy_and_purge(app, make):
    star, plain, frontend, emp = _setup_market(app, make)
    code = plain.get("/api/candidate/me").json["code"]
    vac = emp.post("/api/employer/vacancies", {"title": "Backend", "description": "Описание", "spec": "backend", "grade": "middle", "stack": [], "salary_from": 150000, "salary_to": 250000}).json
    inv = emp.post("/api/employer/invites", {"candidate_code": code, "title": "Backend", "description": "Платёжный сервис, команда", "contact_method": "hr@acme.ru",
                                              "salary_from": 150000, "salary_to": 250000, "vacancy_id": vac["id"]}).json
    assert emp.get(f"/api/employer/vacancies/{vac['id']}/applications").json["items"] == []
    plain.post(f"/api/candidate/invites/{inv['id']}/decision", {"decision": "accept"})
    emp.post(f"/api/employer/invites/{inv['id']}/stage", {"stage": "hired"})
    items = emp.get(f"/api/employer/vacancies/{vac['id']}/applications").json["items"]
    assert len(items) == 1 and items[0]["status"] == "hired"
    assert plain.get("/api/candidate/applications").json["items"][0]["status"] == "hired"
    assert emp.delete(f"/api/employer/invites/{inv['id']}/permanent").json["deleted"] is True
    assert emp.get("/api/employer/invites").json["items"] == [] and plain.get("/api/candidate/invites").json["items"] == []
    assert emp.delete(f"/api/employer/invites/{inv['id']}/permanent").status_code == 404


def test_hired_without_vacancy_requires_choice(app, make):
    star, plain, frontend, emp = _setup_market(app, make)
    code = plain.get("/api/candidate/me").json["code"]
    inv = emp.post("/api/employer/invites", {"candidate_code": code, "title": "Что-то особенное", "description": "Описание предложения", "contact_method": "hr@x.ru",
                                              "salary_from": 100000, "salary_to": 200000}).json
    assert emp.post(f"/api/employer/invites/{inv['id']}/stage", {"stage": "hired"}).status_code == 422       # вакансии нет — нужно выбрать
    vac = emp.post("/api/employer/vacancies", {"title": "Backend", "description": "Описание", "spec": "backend", "grade": "middle", "stack": [], "salary_from": 150000, "salary_to": 250000}).json
    r = emp.post(f"/api/employer/invites/{inv['id']}/stage", {"stage": "hired", "vacancy_id": vac["id"]})
    assert r.status_code == 200 and r.json["placed_in_vacancy"] == "Backend" and r.json["stage"] == "hired"
    assert emp.get(f"/api/employer/vacancies/{vac['id']}/applications").json["items"][0]["status"] == "hired"


def test_employer_deletes_application(app, make):
    star, plain, frontend, emp = _setup_market(app, make)
    vac = emp.post("/api/employer/vacancies", {"title": "Backend", "description": "Описание", "spec": "backend", "grade": "middle", "stack": [], "salary_from": 150000, "salary_to": 250000}).json
    plain.post(f"/api/candidate/vacancies/{vac['id']}/apply", {"message": "Хочу к вам"})
    aid = emp.get(f"/api/employer/vacancies/{vac['id']}/applications").json["items"][0]["id"]
    assert make("hr@other.ru", "employer", company_name="Other").delete(f"/api/employer/applications/{aid}").status_code == 404
    assert emp.delete(f"/api/employer/applications/{aid}").json["deleted"] is True
    assert emp.get(f"/api/employer/vacancies/{vac['id']}/applications").json["items"] == []
    assert plain.get("/api/candidate/applications").json["items"] == []
    assert plain.post(f"/api/candidate/vacancies/{vac['id']}/apply", {"message": "Снова"}).status_code in (200, 201)
