"""Личный кабинет «Кандидат»."""
from datetime import datetime, timedelta, timezone

from flask import Response, current_app, request

from .. import db as D
from ..apidoc import ApiError
from ..schemas import (ApplyIn, DecisionIn, FspLinkIn, MicrotaskAnswerIn, ProfileIn, SettingsIn, SurveyIn, TestFinishIn,
                       TestStartIn, VacancyListQuery)
from ..services import domain, fsp as fsp_mod, matching, resume
from ..taxonomy import GRADES, SPECS, category_label

CAND = ("candidate",)


def _cand(ctx) -> dict:
    return domain.get_candidate(ctx.user["id"])


def _invite_dict(r) -> dict:
    return {"id": r["id"], "title": r["title"], "description": r["description"], "salary_from": r["salary_from"],
            "salary_to": r["salary_to"], "contact_method": r["contact_method"], "status": r["status"],
            "created_at": r["created_at"], "viewed_at": r["viewed_at"], "decided_at": r["decided_at"],
            "vacancy_id": r["vacancy_id"],
            "company": {"name": r["company_name"], "industry": r["industry"], "description": r["emp_description"], "website": r["website"]}}


_INVITE_SQL = """SELECT i.*, e.company_name, e.industry, e.description AS emp_description, e.website
                 FROM invites i JOIN employers e ON e.user_id = i.employer_id WHERE i.candidate_id = ?"""


def register(api):
    # ------------------------------------------------------------------ профиль
    @api.route("/api/candidate/me", ("GET",), tag="Кандидат", summary="Состояние кабинета: профиль, категория, шаги, ФСП", auth=CAND)
    def me(ctx):
        return domain.candidate_state(_cand(ctx))

    @api.route("/api/candidate/profile", ("PUT",), tag="Кандидат", summary="Сохранить профиль и резюме (вручную)", auth=CAND, body=ProfileIn,
               description="Самоописанные данные. Они отображаются в профиле, но НЕ влияют на категорию и ранжирование.")
    def save_profile(ctx):
        b = ctx.body
        D.ex("""UPDATE candidates SET full_name=?, phone=?, city=?, headline=?, about=?, experience_years=?, roles=?, soft_skills=?,
                stack_declared=?, last_activity_at=? WHERE user_id=?""",
             (b.full_name, b.phone, b.city, b.headline, b.about, b.experience_years, D.js(b.roles), D.js(b.soft_skills),
              D.js(b.stack_declared), D.now(), ctx.user["id"]))
        return domain.candidate_state(_cand(ctx))

    @api.route("/api/candidate/resume/parse", ("POST",), tag="Кандидат", summary="Распознать резюме из PDF", auth=CAND, upload=True,
               description="Возвращает предзаполнение формы профиля (ФИО, контакты, стек, стаж, роли, софт-скиллы). Ничего не сохраняет — "
                           "кандидат проверяет данные и сохраняет их через PUT /api/candidate/profile.")
    def parse_resume(ctx):
        f = request.files.get("file")
        if f is None:
            raise ApiError(400, "no_file", "Прикрепите PDF-файл в поле file")
        data = f.read()
        if not data.startswith(b"%PDF"):
            raise ApiError(400, "not_pdf", "Файл не похож на PDF")
        try:
            return resume.parse_resume(data)
        except ValueError as e:
            raise ApiError(422, "unreadable_pdf", str(e))
        except Exception:
            raise ApiError(422, "unreadable_pdf", "Не удалось прочитать PDF. Заполните профиль вручную.")

    @api.route("/api/candidate/profile.pdf", ("GET",), tag="Кандидат", summary="Скачать стандартизированный PDF-профиль", auth=CAND,
               description="PDF с блоком «Подтверждено платформой» (категория, результат теста, подтверждённый стек, опыт ФСП).")
    def profile_pdf(ctx):
        c = _cand(ctx)
        try:
            pdf = resume.build_profile_pdf(c, domain.fsp_summary(c), c["email"])
        except RuntimeError as e:
            raise ApiError(500, "pdf_font_missing", str(e))
        return Response(pdf, mimetype="application/pdf", headers={"Content-Disposition": f'attachment; filename="profile-{c["pseudo_code"]}.pdf"'})

    @api.route("/api/candidate/survey", ("POST",), tag="Кандидат", summary="Опрос по отрасли и специализации (шаг 1 обязательного пути)",
               auth=CAND, body=SurveyIn, description="Фиксирует отрасль, специализацию, заявленный грейд и формат работы. Категория при этом НЕ присваивается — только по итогам теста.")
    def survey(ctx):
        b = ctx.body
        c = _cand(ctx)
        stack_declared = c["stack_declared"] or b.stack
        D.ex("UPDATE candidates SET survey=?, stack_declared=?, last_activity_at=? WHERE user_id=?",
             (D.js(b.model_dump()), D.js(stack_declared), D.now(), ctx.user["id"]))
        return domain.candidate_state(_cand(ctx))

    @api.route("/api/candidate/settings", ("PUT",), tag="Кандидат", summary="Приватность и согласие на публикацию профиля", auth=CAND, body=SettingsIn,
               description="Без согласия `consent_publish` профиль не попадает в банк кандидатов и не виден работодателям (152-ФЗ).")
    def settings(ctx):
        b = ctx.body
        D.ex("UPDATE candidates SET consent_publish=?, privacy=? WHERE user_id=?",
             (int(b.consent_publish), D.js(b.privacy.model_dump()), ctx.user["id"]))
        return domain.candidate_state(_cand(ctx))

    # ------------------------------------------------------------------ ФСП
    @api.route("/api/candidate/fsp", ("POST",), tag="ФСП", summary="Привязать ФСП ID", auth=CAND, body=FspLinkIn,
               description="MVP: привязка допускается, если e-mail аккаунта совпадает с e-mail участника в реестре ФСП. "
                           "В продакшене заменяется входом через ФСП ID (Keycloak/OIDC).")
    def link_fsp(ctx):
        rec = fsp_mod.verify_link(domain.registry(), ctx.body.fsp_id, ctx.user["email"])
        if rec is None:
            if domain.registry().get(ctx.body.fsp_id):
                raise ApiError(403, "fsp_email_mismatch", "E-mail аккаунта не совпадает с e-mail участника ФСП с этим ID")
            raise ApiError(404, "fsp_not_found", "Участник ФСП с таким ID не найден")
        taken = D.q1("SELECT 1 FROM candidates WHERE fsp_id = ? AND user_id != ?", (rec["fsp_id"], ctx.user["id"]))
        if taken:
            raise ApiError(409, "fsp_taken", "Этот ФСП ID уже привязан к другому аккаунту")
        D.ex("UPDATE candidates SET fsp_id=?, fsp_linked_at=?, last_activity_at=? WHERE user_id=?", (rec["fsp_id"], D.now(), D.now(), ctx.user["id"]))
        return domain.candidate_state(_cand(ctx))

    @api.route("/api/candidate/fsp", ("DELETE",), tag="ФСП", summary="Отвязать ФСП ID", auth=CAND)
    def unlink_fsp(ctx):
        D.ex("UPDATE candidates SET fsp_id=NULL, fsp_linked_at=NULL WHERE user_id=?", (ctx.user["id"],))
        return domain.candidate_state(_cand(ctx))

    # ------------------------------------------------------------------ тестирование
    @api.route("/api/candidate/tests", ("POST",), tag="Тестирование", summary="Начать тест на грейд", auth=CAND, body=TestStartIn, status=201,
               description="Генерирует уникальный набор заданий (сид попытки). Ограничения: смена грейда/специализации — не чаще "
                           "GRADE_COOLDOWN_DAYS; не более TEST_ATTEMPTS_PER_DAY попыток в сутки; одна активная попытка.")
    def start_test(ctx):
        att = domain.start_attempt(ctx.user["id"], ctx.body.spec, ctx.body.grade)
        return domain.attempt_public(att)

    @api.route("/api/candidate/tests", ("GET",), tag="Тестирование", summary="История попыток", auth=CAND)
    def tests_history(ctx):
        rows = D.qa("SELECT * FROM test_attempts WHERE user_id = ? ORDER BY id DESC LIMIT 50", (ctx.user["id"],))
        return {"items": [{"id": r["id"], "spec": r["spec"], "grade": r["target_grade"], "status": r["status"], "started_at": r["started_at"],
                           "score_pct": round((r["ratio"] or 0) * 100) if r["ratio"] is not None else None,
                           "passed": None if r["passed"] is None else bool(r["passed"])} for r in rows],
                "grade_history": [dict(r) for r in D.qa("SELECT spec, old_grade, new_grade, reason, at FROM grade_history WHERE user_id = ? ORDER BY id DESC", (ctx.user["id"],))]}

    @api.route("/api/candidate/tests/<int:attempt_id>", ("GET",), tag="Тестирование", summary="Задания активной попытки или результат завершённой", auth=CAND)
    def get_test(ctx, attempt_id):
        att = D.q1("SELECT * FROM test_attempts WHERE id = ? AND user_id = ?", (attempt_id, ctx.user["id"]))
        if att is None:
            raise ApiError(404, "not_found", "Попытка не найдена")
        if att["status"] == "active":
            return {"state": "active", **domain.attempt_public(dict(att))}
        return {"state": "finished", **domain.result_view(att)}

    @api.route("/api/candidate/tests/<int:attempt_id>/finish", ("POST",), tag="Тестирование", summary="Отправить ответы и получить результат",
               auth=CAND, body=TestFinishIn,
               description="Результат определяет категорию: при зачёте присваивается/подтверждается категория (специализация × грейд). "
                           "Грейд не понижается принудительно; при уверенном результате предлагается следующий грейд.")
    def finish_test(ctx, attempt_id):
        return domain.finish_attempt(ctx.user["id"], attempt_id, ctx.body.answers, ctx.body.blur_count)

    # ------------------------------------------------------------------ приглашения
    @api.route("/api/candidate/invites", ("GET",), tag="Приглашения", summary="Входящие приглашения от работодателей", auth=CAND,
               description="Условия (в т.ч. зарплатная вилка) видны до начала общения.")
    def invites(ctx):
        rows = D.qa(_INVITE_SQL + " AND i.status != 'withdrawn' ORDER BY i.id DESC", (ctx.user["id"],))
        return {"items": [_invite_dict(r) for r in rows]}

    @api.route("/api/candidate/invites/<int:invite_id>", ("GET",), tag="Приглашения", summary="Открыть приглашение (статус «просмотрено»)", auth=CAND)
    def invite_open(ctx, invite_id):
        r = D.q1(_INVITE_SQL + " AND i.id = ? AND i.status != 'withdrawn'", (ctx.user["id"], invite_id))
        if r is None:
            raise ApiError(404, "not_found", "Приглашение не найдено")
        if r["status"] == "sent":
            D.ex("UPDATE invites SET status = 'viewed', viewed_at = ? WHERE id = ?", (D.now(), invite_id))
            r = D.q1(_INVITE_SQL + " AND i.id = ?", (ctx.user["id"], invite_id))
        return _invite_dict(r)

    @api.route("/api/candidate/invites/<int:invite_id>/decision", ("POST",), tag="Приглашения", summary="Принять или отклонить приглашение",
               auth=CAND, body=DecisionIn,
               description="При принятии работодатель получает ваши контактные данные (ФИО, e-mail, телефон).")
    def invite_decide(ctx, invite_id):
        r = D.q1("SELECT * FROM invites WHERE id = ? AND candidate_id = ?", (invite_id, ctx.user["id"]))
        if r is None or r["status"] == "withdrawn":
            raise ApiError(404, "not_found", "Приглашение не найдено")
        if r["status"] in ("accepted", "declined"):
            raise ApiError(409, "already_decided", "По этому приглашению решение уже принято")
        status = "accepted" if ctx.body.decision == "accept" else "declined"
        D.ex("UPDATE invites SET status = ?, decided_at = ?, viewed_at = COALESCE(viewed_at, ?) WHERE id = ?", (status, D.now(), D.now(), invite_id))
        domain.touch(ctx.user["id"])
        return _invite_dict(D.q1(_INVITE_SQL + " AND i.id = ?", (ctx.user["id"], invite_id)))

    # ------------------------------------------------------------------ вакансии и отклики (дополнительный сценарий)
    @api.route("/api/candidate/vacancies", ("GET",), tag="Вакансии и отклики", summary="Опубликованные вакансии", auth=CAND, query=VacancyListQuery,
               description="Дополнительный сценарий: кандидат может откликнуться сам. Зарплатная вилка указана обязательно.")
    def vacancies(ctx):
        q, c = ctx.query, _cand(ctx)
        sql = """SELECT v.*, e.company_name, e.industry,
                        (SELECT status FROM applications a WHERE a.vacancy_id = v.id AND a.candidate_id = ?) AS my_status
                 FROM vacancies v JOIN employers e ON e.user_id = v.employer_id WHERE v.status = 'published'"""
        args = [ctx.user["id"]]
        if q.spec:
            sql += " AND v.spec = ?"; args.append(q.spec)
        if q.grade:
            sql += " AND v.grade = ?"; args.append(q.grade)
        rows = D.qa(sql + " ORDER BY v.id DESC", args)
        items = []
        for r in rows:
            fit, why = matching.category_factor(r["spec"], r["grade"], c["spec"], c["grade"])
            items.append({"id": r["id"], "title": r["title"], "description": r["description"], "spec": r["spec"], "grade": r["grade"],
                          "category_label": category_label(r["spec"], r["grade"]), "stack": D.jl(r["stack"], []), "work_format": r["work_format"],
                          "salary_from": r["salary_from"], "salary_to": r["salary_to"], "company": {"name": r["company_name"], "industry": r["industry"]},
                          "created_at": r["created_at"], "my_application": r["my_status"], "fit": round(fit, 2), "fit_text": why})
        items.sort(key=lambda x: (-x["fit"], -x["id"]))
        return {"total": len(items), "items": items[q.offset:q.offset + q.limit]}

    @api.route("/api/candidate/vacancies/<int:vacancy_id>/apply", ("POST",), tag="Вакансии и отклики", summary="Откликнуться на вакансию", auth=CAND,
               body=ApplyIn, status=201, description="Отклик раскрывает ваши контакты работодателю этой вакансии.")
    def apply(ctx, vacancy_id):
        c = _cand(ctx)
        v = D.q1("SELECT * FROM vacancies WHERE id = ? AND status = 'published'", (vacancy_id,))
        if v is None:
            raise ApiError(404, "not_found", "Вакансия не найдена или закрыта")
        if not c["full_name"]:
            raise ApiError(409, "profile_incomplete", "Укажите ФИО в профиле — работодатель получит его вместе с откликом")
        if D.q1("SELECT 1 FROM applications WHERE vacancy_id = ? AND candidate_id = ?", (vacancy_id, ctx.user["id"])):
            raise ApiError(409, "already_applied", "Вы уже откликались на эту вакансию")
        aid = D.ex("INSERT INTO applications(vacancy_id, candidate_id, message, status, created_at, updated_at) VALUES (?,?,?,?,?,?)",
                   (vacancy_id, ctx.user["id"], ctx.body.message, "sent", D.now(), D.now()))
        domain.touch(ctx.user["id"])
        return {"id": aid, "status": "sent"}

    @api.route("/api/candidate/applications", ("GET",), tag="Вакансии и отклики", summary="Мои отклики и их статусы", auth=CAND)
    def applications(ctx):
        rows = D.qa("""SELECT a.*, v.title, v.salary_from, v.salary_to, e.company_name FROM applications a
                       JOIN vacancies v ON v.id = a.vacancy_id JOIN employers e ON e.user_id = v.employer_id
                       WHERE a.candidate_id = ? ORDER BY a.id DESC""", (ctx.user["id"],))
        return {"items": [{"id": r["id"], "vacancy_id": r["vacancy_id"], "title": r["title"], "company": r["company_name"], "status": r["status"],
                           "salary_from": r["salary_from"], "salary_to": r["salary_to"], "created_at": r["created_at"], "updated_at": r["updated_at"]} for r in rows]}

    # ------------------------------------------------------------------ регулярные задания
    def _ensure_assignments(c: dict) -> None:
        if not c["grade"]:
            return
        week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
        recent = D.q1("SELECT COUNT(*) AS n FROM microtask_assignments WHERE candidate_id = ? AND assigned_at >= ?", (c["user_id"], week_ago))["n"]
        slots = current_app.config["MICROTASKS_PER_WEEK"] - recent
        if slots <= 0:
            return
        gi = list(GRADES).index(c["grade"])
        grades = [g for i, g in enumerate(GRADES) if i in (gi, gi - 1) and i >= 0]
        marks = ",".join("?" * len(grades))
        tasks = D.qa(f"""SELECT id FROM microtasks WHERE active = 1 AND spec = ? AND grade IN ({marks})
                         AND id NOT IN (SELECT task_id FROM microtask_assignments WHERE candidate_id = ?) ORDER BY id DESC LIMIT ?""",
                     (c["spec"], *grades, c["user_id"], slots))
        for t in tasks:
            D.ex("INSERT OR IGNORE INTO microtask_assignments(task_id, candidate_id, status, assigned_at) VALUES (?,?,?,?)", (t["id"], c["user_id"], "assigned", D.now()))

    @api.route("/api/candidate/microtasks", ("GET",), tag="Регулярные задания", summary="Короткие задания от работодателей", auth=CAND,
               description="Система периодически назначает кандидату задачу от работодателя (не более MICROTASKS_PER_WEEK в неделю): решить её или предложить подход. "
                           "Ответ повышает актуальность профиля.")
    def microtasks(ctx):
        c = _cand(ctx)
        _ensure_assignments(c)
        rows = D.qa("""SELECT m.*, a.id AS aid, a.status AS astatus, a.answer, a.rating, a.feedback, a.assigned_at, e.company_name
                       FROM microtask_assignments a JOIN microtasks m ON m.id = a.task_id JOIN employers e ON e.user_id = m.employer_id
                       WHERE a.candidate_id = ? ORDER BY a.id DESC""", (ctx.user["id"],))
        return {"items": [{"task_id": r["id"], "title": r["title"], "body": r["body"], "kind": r["kind"], "company": r["company_name"],
                           "status": r["astatus"], "answer": r["answer"], "rating": r["rating"], "feedback": r["feedback"], "assigned_at": r["assigned_at"]} for r in rows]}

    @api.route("/api/candidate/microtasks/<int:task_id>/answer", ("POST",), tag="Регулярные задания", summary="Отправить решение или подход", auth=CAND,
               body=MicrotaskAnswerIn)
    def microtask_answer(ctx, task_id):
        a = D.q1("SELECT * FROM microtask_assignments WHERE task_id = ? AND candidate_id = ?", (task_id, ctx.user["id"]))
        if a is None:
            raise ApiError(404, "not_found", "Задание вам не назначено")
        if a["status"] != "assigned":
            raise ApiError(409, "already_submitted", "Ответ уже отправлен")
        D.ex("UPDATE microtask_assignments SET status='submitted', answer=?, submitted_at=? WHERE id=?", (ctx.body.answer, D.now(), a["id"]))
        D.ex("UPDATE candidates SET micro_bonus = MIN(1.0, micro_bonus + 0.15), last_activity_at = ? WHERE user_id = ?", (D.now(), ctx.user["id"]))
        return {"status": "submitted"}

    # ------------------------------------------------------------------ данные субъекта
    @api.route("/api/candidate/export", ("GET",), tag="Кандидат", summary="Выгрузить все мои данные (JSON)", auth=CAND,
               description="Право субъекта на доступ к своим персональным данным (152-ФЗ).")
    def export(ctx):
        c = _cand(ctx)
        uid = ctx.user["id"]
        return {"account": {"email": c["email"], "consent_pd_at": ctx.user["consent_pd_at"], "created_at": ctx.user["created_at"]},
                "profile": domain.candidate_state(c), "tests": [dict(r) for r in D.qa(
                    "SELECT id, spec, target_grade, status, started_at, finished_at, ratio, passed FROM test_attempts WHERE user_id = ?", (uid,))],
                "invites": [dict(r) for r in D.qa("SELECT id, title, salary_from, salary_to, status, created_at FROM invites WHERE candidate_id = ?", (uid,))],
                "applications": [dict(r) for r in D.qa("SELECT id, vacancy_id, status, created_at FROM applications WHERE candidate_id = ?", (uid,))]}
