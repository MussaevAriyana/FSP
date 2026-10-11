"""Демо-данные: синтетический реестр ФСП, кандидаты, работодатели, вакансии, приглашения.

Всё создаётся через настоящий конвейер приложения (регистрация → опрос → генерация теста →
проверка → категория), а не прямой записью категорий в БД. Ответы моделируются по scripts/simulate.py.

    python scripts/seed.py            # 70 кандидатов (SEED_CANDIDATES=N — другое число)
Демо-входы (пароль у всех Demo12345):
    модератор:    moderator@fsp-demo.ru
    кандидат:     demo.candidate@fsp-demo.ru   (e-mail есть в реестре ФСП — можно привязать FSP-100001)
    работодатель: demo.employer@fsp-demo.ru
"""
import json
import os
import random
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from app import create_app  # noqa: E402
from app import db as D  # noqa: E402
from simulate import draw_theta, simulate_answers  # noqa: E402

PWD = "Demo12345"
FIRST = ["Алексей", "Мария", "Дмитрий", "Анна", "Иван", "Екатерина", "Сергей", "Ольга", "Артём", "Наталья", "Павел", "Елена", "Михаил", "Татьяна", "Никита", "Виктория"]
LAST = ["Иванов", "Смирнова", "Кузнецов", "Попова", "Соколов", "Лебедева", "Козлов", "Новикова", "Морозов", "Петрова", "Волков", "Соловьёва", "Васильев", "Зайцева", "Орлов", "Белова"]
CITIES = ["Москва", "Санкт-Петербург", "Казань", "Новосибирск", "Екатеринбург", "Нижний Новгород", "Самара", "Пермь"]
INDUSTRIES = ["Финтех и банки", "Электронная коммерция", "Телеком", "Государственные сервисы (GovTech)", "Игры и медиа", "Образование (EdTech)"]
GRADES = ["trainee", "junior", "middle", "senior"]
SPEC_W = {"backend": 0.32, "frontend": 0.24, "data": 0.16, "devops": 0.14, "qa": 0.14}
GRADE_W = [0.15, 0.35, 0.33, 0.17]
STACK_BY_SPEC = {"backend": ["python", "java", "go", "sql", "postgresql", "redis", "docker"], "frontend": ["javascript", "typescript", "react", "vue", "css", "html"],
                 "data": ["python", "pandas", "sql", "ml", "statistics"], "devops": ["linux", "docker", "kubernetes", "ci_cd", "terraform", "bash"],
                 "qa": ["manual", "pytest", "selenium", "api_testing", "sql"]}
EVENTS = ["Открытый кубок ФСП", "Хакатон ФСП", "Лига ФСП: весна", "Лига ФСП: осень", "Школа ФСП", "Московская командная олимпиада", "Чемпионат ФСП по алгоритмам"]


class Client:
    def __init__(self, app, email, role, **extra):
        self.c, self.app, self.email = app.test_client(), app, email
        r = self.c.post("/api/auth/register", json={"email": email, "password": PWD, "role": role, "consent_pd": True, **extra})
        assert r.status_code == 201, r.json
        r = self.c.post("/api/auth/confirm", json={"token": r.json["dev_token"]})
        self.token, self.uid = r.json["token"], r.json["user"]["id"]

    def req(self, method, url, body=None):
        return getattr(self.c, method)(url, headers={"Authorization": f"Bearer {self.token}"}, json=body)

    def get(self, u): return self.req("get", u)
    def post(self, u, b=None): return self.req("post", u, b)
    def put(self, u, b=None): return self.req("put", u, b)


def build_registry(rng: random.Random, n: int, today: date) -> list[dict]:
    """Синтетический реестр ФСП: участники cand00..cand{n-1}@fsp-demo.ru (кроме части без истории)."""
    reg = []
    for i in range(n):
        events = []
        for k in range(rng.randint(1, 6)):
            parts = rng.choice([40, 60, 120, 200, 350])
            quality = rng.random() ** 1.7                      # ближе к 0 — лучше результат
            events.append({"id": i * 10 + k, "title": rng.choice(EVENTS), "type": rng.choice(["contest", "contest", "hackathon", "training"]),
                           "date": (today - timedelta(days=rng.randint(10, 900))).isoformat(), "place": max(1, int(quality * parts)),
                           "participants": parts, "points": rng.randint(10, 100)})
        reg.append({"fsp_id": f"FSP-{100000 + i}", "email": f"cand{i:02d}@fsp-demo.ru", "full_name": f"{rng.choice(FIRST)} {rng.choice(LAST)}", "events": events})
    reg[0]["email"] = "demo.candidate@fsp-demo.ru"
    return reg


JPEG = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDABQODxIPDRQSEBIXFRQYHjIhHhwcHj0sLiQySUBMS0dARkVQWnNiUFVtVkVGZIhlbXd7gYKBTmCNl4x9lnN+gXz/2wBDARUXFx4aHjshITt8U0ZTfHx8fHx8fHx8fHx8fHx8fHx8fHx8fHx8fHx8fHx8fHx8fHx8fHx8fHx8fHx8fHx8fHz/wAARCAAwAEADASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDLooortLCiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooA//Z"


def run_test(app, cli: Client, spec: str, grade: str, theta: float, rng: random.Random, fast: bool = False) -> dict:
    r = cli.post("/api/candidate/tests", {"spec": spec, "grade": grade, "consent_proctoring": True, "camera_ready": True})
    if r.status_code != 201:
        return {"error": r.json}
    aid = r.json["id"]
    with app.app_context():
        qs = json.loads(D.q1("SELECT questions FROM test_attempts WHERE id = ?", (aid,))["questions"])
        minutes = 1 if fast else rng.randint(11, 32)
        D.ex("UPDATE test_attempts SET started_at = ? WHERE id = ?",
             ((datetime.now(timezone.utc) - timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ"), aid))
    # прокторинг: снимки раз в ~2 минуты; «быстрые» прохождения получают нарушения
    cid = f"seed-{aid:06d}"
    for k in range(minutes // 2 + 1):
        evs = []
        if fast and k == 0:
            evs = [{"kind": "paste", "meta": {}}] * 3 + [{"kind": "tab_hidden", "meta": {}}] * 3 + [{"kind": "fullscreen_exit", "meta": {}}]
        elif rng.random() < 0.04:
            evs = [{"kind": "window_blur", "meta": {}}]
        cli.post(f"/api/candidate/tests/{aid}/proctor", {"cid": cid, "events": evs, "snapshot": JPEG, "camera": True})
    times = {q["id"]: rng.uniform(40, 240) for q in qs}
    return cli.post(f"/api/candidate/tests/{aid}/finish", {"answers": simulate_answers(qs, theta, rng), "blur_count": rng.choice([0, 0, 0, 1, 2]), "times": times}).json


def main():
    n = int(os.environ.get("SEED_CANDIDATES", "70"))
    rng = random.Random(2026)
    db_path = os.environ.get("DB_PATH", str(ROOT / "data" / "app.db"))
    if os.path.exists(db_path):
        os.remove(db_path)
    reg_path = Path(os.environ.get("FSP_REGISTRY_FILE", ROOT / "data" / "fsp_registry.json"))
    reg = build_registry(rng, n + 1, date.today())
    reg_path.parent.mkdir(parents=True, exist_ok=True)
    reg_path.write_text(json.dumps(reg, ensure_ascii=False, indent=1), encoding="utf-8")
    app = create_app({"DB_PATH": db_path, "FSP_REGISTRY_FILE": str(reg_path), "DEV_MODE": True, "SECRET_KEY": "seed-secret-seed-secret-seed-secret"})

    with app.app_context():
        from create_moderator import create as _mk_mod
        _mk_mod("moderator@fsp-demo.ru", PWD)

    cands = []
    for i in range(n):
        spec = rng.choices(list(SPEC_W), list(SPEC_W.values()))[0]
        gi = rng.choices(range(4), GRADE_W)[0]
        theta = draw_theta(gi, rng)
        email = "demo.candidate@fsp-demo.ru" if i == 0 else f"cand{i:02d}@fsp-demo.ru"
        name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        cli = Client(app, email, "candidate", full_name=name)
        cli.put("/api/candidate/profile", {"full_name": name, "phone": f"+7 9{rng.randint(10, 99)} {rng.randint(100, 999)}-{rng.randint(10, 99)}-{rng.randint(10, 99)}",
                                           "city": rng.choice(CITIES), "headline": f"{spec.capitalize()}-специалист", "experience_years": [0, 0.5, 2, 5][gi] + rng.choice([0, 0.5, 1]),
                                           "about": "Увлекаюсь спортивным программированием и разбором олимпиадных задач.",
                                           "roles": [f"{spec} в компании {rng.choice(['Альфа', 'Бета', 'Гамма'])}"], "stack_declared": rng.sample(STACK_BY_SPEC[spec], 3),
                                           "soft_skills": rng.sample(["Коммуникация", "Работа в команде", "Ответственность", "Самообучаемость"], 2)})
        claim = min(3, gi + (1 if rng.random() < 0.25 else 0))
        cli.post("/api/candidate/survey", {"industry": rng.choice(INDUSTRIES), "spec": spec, "grade": GRADES[claim], "stack": rng.sample(STACK_BY_SPEC[spec], 3), "format": rng.choice(["remote", "hybrid", "office"])})
        fast = rng.random() < 0.05
        g = claim
        while g >= 0:
            res = run_test(app, cli, spec, GRADES[g], theta, rng, fast)
            if res.get("passed"):
                break
            g -= 1                                               # «не прошёл — тест на уровень ниже», как в ТЗ
        if rng.random() < 0.45 and i < len(reg):
            cli.post("/api/candidate/fsp", {"fsp_id": f"FSP-{100000 + i}"})
        cli.put("/api/candidate/settings", {"consent_publish": rng.random() < 0.92, "privacy": {"show_city": rng.random() < 0.5}})
        cands.append((cli, spec, gi))
    print(f"кандидатов создано: {len(cands)}")

    emps = []
    for name, mail in [("Платёжный дом «Ключ»", "klyuch"), ("Маркетплейс «Ярмарка»", "yarmarka"), ("Телеком-Софт", "telecom-soft"), ("ГосТех-Лаб", "gostech")]:
        e = Client(app, f"hr@{mail}-demo.ru", "employer", company_name=name)
        emps.append(e)
    demo = Client(app, "demo.employer@fsp-demo.ru", "employer", company_name="Демо-компания «Орбита»")
    emps.insert(0, demo)
    for e, (name, ind) in zip(emps, [("Демо-компания «Орбита»", "Разработка ПО"), ("Платёжный дом «Ключ»", "Финтех"), ("Маркетплейс «Ярмарка»", "Электронная коммерция"), ("Телеком-Софт", "Телеком"), ("ГосТех-Лаб", "GovTech")]):
        e.put("/api/employer/company", {"company_name": name, "industry": ind, "description": f"{name}: продуктовая ИТ-команда, работаем над сервисами для миллионов пользователей.",
                                       "website": "https://example.org", "contact_name": "Анна из HR", "contact_method": f"hr@{e.email.split('@')[1]}, Telegram @hr_team"})
    needs = {}
    for e, (spec, grade, stack) in zip(emps, [("backend", "middle", ["python", "sql", "docker"]), ("backend", "senior", ["go", "postgresql"]), ("frontend", "middle", ["javascript", "react"]),
                                              ("devops", "middle", ["linux", "docker", "kubernetes"]), ("data", "junior", ["python", "pandas", "sql"])]):
        needs[e.uid] = e.post("/api/employer/needs", {"title": f"{spec.capitalize()}-разработчик ({grade})", "spec": spec, "grade": grade, "stack": stack,
                                                      "team_desc": "Команда из 7 человек, двухнедельные спринты, код-ревью, CI/CD."}).json
        e.post("/api/employer/vacancies", {"title": f"{spec.capitalize()} {grade}", "description": "Продуктовая разработка, удалённо или гибрид.", "spec": spec, "grade": grade, "stack": stack,
                                           "salary_from": {"junior": 90000, "middle": 180000, "senior": 300000}.get(grade, 60000), "salary_to": {"junior": 150000, "middle": 280000, "senior": 450000}.get(grade, 90000)})
        e.post("/api/employer/microtasks", {"title": "Как бы вы ускорили медленный отчёт?", "body": "Отчёт по заказам строится 40 секунд. Опишите, как найдёте причину и что предложите.", "spec": spec, "grade": grade, "kind": "approach"})

    # приглашений в демо-данных нет: работодатели отправляют их сами
    # демо-данные новых разделов: резюме кандидата и стартовый баланс
    dc = cands[0][0]
    dc.put("/api/candidate/resume", {"desired_position": "Frontend-разработчик", "summary": "Делаю интерфейсы для продуктовых команд, люблю читаемый код и тесты.",
        "experience": [{"company": "Студия «Пиксель»", "position": "Frontend-разработчик", "start": "2022-03", "end": "", "description": "Личные кабинеты, дашборды, оптимизация загрузки."}],
        "projects": [{"name": "Трекер привычек", "role": "автор", "link": "https://example.org/habits", "description": "PWA с офлайн-режимом.", "stack": ["javascript", "react"]}],
        "education": [{"institution": "НИУ «Высшая школа информатики»", "degree": "Бакалавр", "specialty": "Прикладная информатика", "year_from": "2018", "year_to": "2022"}],
        "certificates": [{"kind": "certificate", "name": "Продвинутый JavaScript", "issuer": "Онлайн-школа", "year": "2023", "link": ""}]})
    dc.put("/api/candidate/resume", {**dc.get("/api/candidate/resume").json, "salary_expectation": 220000, "employment_types": ["full"], "schedules": ["remote", "hybrid"], "relocation": "maybe",
        "languages": [{"name": "Английский", "level": "B2"}], "links": {"github": "https://github.com/demo-candidate", "telegram": "@demo_candidate", "linkedin": "", "site": ""},
        "personal": {"birth_year": 1999, "citizenship": "РФ", "marital_status": "single", "children": "none", "military": "", "driving": "B"}})
    dc.post("/api/wallet/topup", {"amount": 1500})
    emps[0].post("/api/wallet/topup", {"amount": 3000})

    with app.app_context():
        rows = D.qa("SELECT spec, grade, COUNT(*) AS n FROM candidates WHERE grade IS NOT NULL GROUP BY spec, grade ORDER BY spec, grade")
        total = sum(r["n"] for r in rows)
        print(f"с категорией: {total} из {n}")
    print("Демо-входы: demo.candidate@fsp-demo.ru / demo.employer@fsp-demo.ru, пароль", PWD)


if __name__ == "__main__":
    main()
