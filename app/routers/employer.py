"""Личный кабинет «Работодатель»: компания, потребность, подборка, банк кандидатов, приглашения, вакансии, задания."""
from collections import Counter
from datetime import datetime, timedelta, timezone

from flask import current_app

from .. import db as D
from ..apidoc import ApiError
from ..schemas import (ApplicationStatusIn, CompanyIn, InviteIn, MicrotaskIn, NeedIn, RateIn, SearchQuery, VacancyIn, VacancyStatusIn)
from ..services import domain, matching
from ..taxonomy import category_label

EMP = ("employer",)


def _need_dict(r) -> dict:
    return {"id": r["id"], "title": r["title"], "spec": r["spec"], "grade": r["grade"], "stack": D.jl(r["stack"], []),
            "team_desc": r["team_desc"], "work_format": r["work_format"], "created_at": r["created_at"],
            "category_label": category_label(r["spec"], r["grade"])}


def _vacancy_dict(r, **extra) -> dict:
    return {"id": r["id"], "title": r["title"], "description": r["description"], "spec": r["spec"], "grade": r["grade"],
            "category_label": category_label(r["spec"], r["grade"]), "stack": D.jl(r["stack"], []), "work_format": r["work_format"],
            "salary_from": r["salary_from"], "salary_to": r["salary_to"], "status": r["status"], "created_at": r["created_at"], **extra}


def _own(table: str, obj_id: int, employer_id: int):
    row = D.q1(f"SELECT * FROM {table} WHERE id = ? AND employer_id = ?", (obj_id, employer_id))
    if row is None:
        raise ApiError(404, "not_found", "Объект не найден")
    return row


def run_search(employer_id: int, need: dict | None, q: SearchQuery) -> dict:
    """Подборка/поиск. Ядро механики: выдача строится по категориям и подтверждённым данным."""
    rows = domain.visible_candidate_rows()
    integ, revealed = domain.integrity_map(), domain.revealed_ids(employer_id)
    cats = Counter((c["spec"], c["grade"]) for c in rows)
    stack_f = [s.strip().lower() for s in (q.stack or "").split(",") if s.strip()]
    grades_f = [g.strip() for g in (q.grade or "").split(",") if g.strip()]

    def relevant(c) -> bool:
        if need is None:
            return True
        return matching.category_factor(need["spec"], need["grade"], c["spec"], c["grade"])[0] > 0

    base = [c for c in rows if relevant(c)]       # подборка до фильтров — она не теряется при уточнении запроса

    def passes(c) -> bool:
        p = c["privacy"]
        if q.spec and c["spec"] != q.spec:
            return False
        if grades_f and c["grade"] not in grades_f:
            return False
        if stack_f and not (p["show_stack"] and set(stack_f) <= set(c["stack_confirmed"])):
            return False
        if q.has_fsp and not (p["show_fsp"] and domain.fsp_summary(c)):
            return False
        if q.min_score is not None and c["best_score"] * 100 < q.min_score:
            return False
        if q.city and not (p["show_city"] and q.city.strip().lower() in (c["city"] or "").lower()):
            return False  # по скрытому городу фильтровать нельзя — иначе он раскрывается
        return True

    found = [c for c in base if passes(c)]
    cards = []
    for c in found:
        ref_need = need or {"spec": c["spec"], "grade": c["grade"], "stack": stack_f}
        if need is None and stack_f:
            ref_need = {"spec": c["spec"], "grade": c["grade"], "stack": stack_f}
        cards.append(domain.employer_card(c, employer_id, ref_need, integ=integ, revealed=revealed))
    cards.sort(key=lambda x: (-x["match"]["score"], -x["test_score"], x["code"]))
    return {
        "need": need, "filters": {k: v for k, v in q.model_dump().items() if v not in (None, "") and k not in ("limit", "offset", "need_id")},
        "base_total": len(base), "total": len(cards),
        "items": cards[q.offset:q.offset + q.limit],
        "recommended_categories": matching.recommend_categories(need, cats) if need else [
            {"spec": s, "grade": g, "label": category_label(s, g), "count": n} for (s, g), n in sorted(cats.items(), key=lambda kv: -kv[1])],
    }


def register(api):
    # ------------------------------------------------------------------ компания
    @api.route("/api/employer/company", ("GET",), tag="Работодатель", summary="Профиль компании", auth=EMP)
    def company(ctx):
        r = D.q1("SELECT * FROM employers WHERE user_id = ?", (ctx.user["id"],))
        return {**{k: r[k] for k in ("company_name", "industry", "description", "website", "contact_name", "contact_method")}, "email": ctx.user["email"]}

    @api.route("/api/employer/company", ("PUT",), tag="Работодатель", summary="Сохранить профиль компании", auth=EMP, body=CompanyIn)
    def save_company(ctx):
        b = ctx.body
        D.ex("""UPDATE employers SET company_name=?, industry=?, description=?, website=?, contact_name=?, contact_method=? WHERE user_id=?""",
             (b.company_name, b.industry, b.description, b.website, b.contact_name, b.contact_method, ctx.user["id"]))
        return b.model_dump()

    @api.route("/api/employer/summary", ("GET",), tag="Работодатель", summary="Сводка по кабинету", auth=EMP)
    def summary(ctx):
        uid = ctx.user["id"]
        inv = {r["status"]: r["n"] for r in D.qa("SELECT status, COUNT(*) AS n FROM invites WHERE employer_id = ? GROUP BY status", (uid,))}
        return {"needs": D.q1("SELECT COUNT(*) AS n FROM needs WHERE employer_id = ?", (uid,))["n"],
                "vacancies": D.q1("SELECT COUNT(*) AS n FROM vacancies WHERE employer_id = ? AND status = 'published'", (uid,))["n"],
                "applications_new": D.q1("""SELECT COUNT(*) AS n FROM applications a JOIN vacancies v ON v.id = a.vacancy_id
                                            WHERE v.employer_id = ? AND a.status = 'sent'""", (uid,))["n"],
                "invites": inv, "invites_total": sum(inv.values()),
                "candidates_in_bank": len(domain.visible_candidate_rows()),
                "invites_left_today": max(0, current_app.config["INVITES_PER_DAY"] - _invites_today(uid))}

    # ------------------------------------------------------------------ потребность и подборка
    @api.route("/api/employer/needs", ("POST",), tag="Подбор", summary="Описать потребность", auth=EMP, body=NeedIn, status=201,
               description="Какие специалисты нужны: специализация, грейд, стек, чем занимается команда. На её основе формируется подборка.")
    def create_need(ctx):
        b = ctx.body
        nid = D.ex("""INSERT INTO needs(employer_id, title, spec, grade, stack, team_desc, work_format, created_at) VALUES (?,?,?,?,?,?,?,?)""",
                   (ctx.user["id"], b.title, b.spec, b.grade, D.js(b.stack), b.team_desc, b.work_format, D.now()))
        return _need_dict(D.q1("SELECT * FROM needs WHERE id = ?", (nid,)))

    @api.route("/api/employer/needs", ("GET",), tag="Подбор", summary="Мои потребности", auth=EMP)
    def list_needs(ctx):
        return {"items": [_need_dict(r) for r in D.qa("SELECT * FROM needs WHERE employer_id = ? ORDER BY id DESC", (ctx.user["id"],))]}

    @api.route("/api/employer/needs/<int:need_id>", ("DELETE",), tag="Подбор", summary="Удалить потребность", auth=EMP)
    def delete_need(ctx, need_id):
        _own("needs", need_id, ctx.user["id"])
        D.ex("DELETE FROM needs WHERE id = ?", (need_id,))
        return {"deleted": True}

    @api.route("/api/employer/needs/<int:need_id>/matches", ("GET",), tag="Подбор", summary="Подборка кандидатов под потребность", auth=EMP, query=SearchQuery,
               description="Рекомендованные категории + кандидаты, ранжированные по силе подтверждённого профиля, с объяснением (`match.reasons`). "
                           "Фильтры уточняют выдачу; `base_total` — размер исходной подборки до фильтров (она не теряется).")
    def matches(ctx, need_id):
        need = _need_dict(_own("needs", need_id, ctx.user["id"]))
        return run_search(ctx.user["id"], need, ctx.query)

    # ------------------------------------------------------------------ банк кандидатов
    @api.route("/api/employer/candidates", ("GET",), tag="Банк кандидатов", summary="Поиск по банку кандидатов", auth=EMP, query=SearchQuery,
               description="Фильтры: специализация, грейд, стек (подтверждённый тестом), наличие достижений ФСП, минимальный результат теста. "
                           "Имя и контакты скрыты до принятия приглашения/отклика. Кандидаты с `consent_publish=false` не видны.")
    def search(ctx):
        need = None
        if ctx.query.need_id:
            need = _need_dict(_own("needs", ctx.query.need_id, ctx.user["id"]))
        return run_search(ctx.user["id"], need, ctx.query)

    @api.route("/api/employer/candidates/<code>", ("GET",), tag="Банк кандидатов", summary="Карточка кандидата", auth=EMP,
               description="Подробная карточка. Если кандидат принял приглашение или откликнулся — добавляются контакты (`contacts`).")
    def candidate_card(ctx, code):
        c = domain.visible_by_code(code)
        return domain.employer_card(c, ctx.user["id"], {"spec": c["spec"], "grade": c["grade"], "stack": []}, detailed=True)

    # ------------------------------------------------------------------ приглашения
    def _invites_today(uid: int) -> int:
        since = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
        return D.q1("SELECT COUNT(*) AS n FROM invites WHERE employer_id = ? AND created_at >= ?", (uid, since))["n"]

    @api.route("/api/employer/invites", ("POST",), tag="Выход на контакт", summary="Направить приглашение кандидату", auth=EMP, body=InviteIn, status=201,
               description="Инициатива у работодателя. Приглашение содержит описание предложения, зарплатную вилку (₽, обязательно), название компании и способ связи; "
                           "привязка к вакансии не требуется. Контакты кандидата раскрываются только после принятия.")
    def create_invite(ctx):
        b, uid = ctx.body, ctx.user["id"]
        cand = domain.visible_by_code(b.candidate_code)
        if D.q1("SELECT 1 FROM invites WHERE employer_id = ? AND candidate_id = ? AND status IN ('sent','viewed')", (uid, cand["user_id"])):
            raise ApiError(409, "invite_active", "Этому кандидату уже отправлено приглашение, ответа пока нет")
        if _invites_today(uid) >= current_app.config["INVITES_PER_DAY"]:
            raise ApiError(429, "invite_limit", "Достигнут суточный лимит приглашений")
        if b.vacancy_id is not None:
            _own("vacancies", b.vacancy_id, uid)
        snapshot = {}
        if b.need_id is not None:
            need = _need_dict(_own("needs", b.need_id, uid))
            snapshot = matching.score_candidate(need, domain.internal_view(cand))
            snapshot["need_title"] = need["title"]
        iid = D.ex("""INSERT INTO invites(employer_id, candidate_id, vacancy_id, title, description, salary_from, salary_to, contact_method,
                      status, match_snapshot, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                   (uid, cand["user_id"], b.vacancy_id, b.title, b.description, b.salary_from, b.salary_to, b.contact_method, "sent", D.js(snapshot), D.now()))
        return _invite_view(D.q1("SELECT * FROM invites WHERE id = ?", (iid,)), uid)

    def _invite_view(r, employer_id: int) -> dict:
        c = domain.candidate_by_user_id(r["candidate_id"])
        card = domain.employer_card(c, employer_id, None) if c["grade"] else {"code": c["pseudo_code"], "revealed": False}
        return {"id": r["id"], "title": r["title"], "description": r["description"], "salary_from": r["salary_from"], "salary_to": r["salary_to"],
                "contact_method": r["contact_method"], "status": r["status"], "created_at": r["created_at"], "viewed_at": r["viewed_at"],
                "decided_at": r["decided_at"], "vacancy_id": r["vacancy_id"], "candidate": card, "match": D.jl(r["match_snapshot"], {})}

    @api.route("/api/employer/invites", ("GET",), tag="Выход на контакт", summary="Мои приглашения и их статусы", auth=EMP,
               description="Статусы: sent (отправлено) → viewed (просмотрено) → accepted (принято) / declined (отклонено); withdrawn — отозвано.")
    def list_invites(ctx):
        rows = D.qa("SELECT * FROM invites WHERE employer_id = ? ORDER BY id DESC", (ctx.user["id"],))
        return {"items": [_invite_view(r, ctx.user["id"]) for r in rows]}

    @api.route("/api/employer/invites/<int:invite_id>", ("DELETE",), tag="Выход на контакт", summary="Отозвать приглашение", auth=EMP,
               description="Можно отозвать, пока кандидат не принял решение.")
    def withdraw(ctx, invite_id):
        r = _own("invites", invite_id, ctx.user["id"])
        if r["status"] not in ("sent", "viewed"):
            raise ApiError(409, "not_withdrawable", "По приглашению уже принято решение")
        D.ex("UPDATE invites SET status = 'withdrawn', decided_at = ? WHERE id = ?", (D.now(), invite_id))
        return {"status": "withdrawn"}

    # ------------------------------------------------------------------ вакансии (дополнительный сценарий)
    @api.route("/api/employer/vacancies", ("POST",), tag="Вакансии", summary="Опубликовать вакансию", auth=EMP, body=VacancyIn, status=201,
               description="Зарплатная вилка (₽, «от–до») обязательна.")
    def create_vacancy(ctx):
        b = ctx.body
        vid = D.ex("""INSERT INTO vacancies(employer_id, title, description, spec, grade, stack, work_format, salary_from, salary_to, status, created_at)
                      VALUES (?,?,?,?,?,?,?,?,?,?,?)""", (ctx.user["id"], b.title, b.description, b.spec, b.grade, D.js(b.stack), b.work_format,
                                                           b.salary_from, b.salary_to, "published", D.now()))
        return _vacancy_dict(D.q1("SELECT * FROM vacancies WHERE id = ?", (vid,)))

    @api.route("/api/employer/vacancies", ("GET",), tag="Вакансии", summary="Мои вакансии", auth=EMP)
    def list_vacancies(ctx):
        rows = D.qa("""SELECT v.*, (SELECT COUNT(*) FROM applications a WHERE a.vacancy_id = v.id) AS apps,
                              (SELECT COUNT(*) FROM applications a WHERE a.vacancy_id = v.id AND a.status = 'sent') AS apps_new
                       FROM vacancies v WHERE v.employer_id = ? ORDER BY v.id DESC""", (ctx.user["id"],))
        return {"items": [_vacancy_dict(r, applications=r["apps"], applications_new=r["apps_new"]) for r in rows]}

    @api.route("/api/employer/vacancies/<int:vacancy_id>", ("PUT",), tag="Вакансии", summary="Редактировать вакансию", auth=EMP, body=VacancyIn)
    def edit_vacancy(ctx, vacancy_id):
        _own("vacancies", vacancy_id, ctx.user["id"])
        b = ctx.body
        D.ex("""UPDATE vacancies SET title=?, description=?, spec=?, grade=?, stack=?, work_format=?, salary_from=?, salary_to=? WHERE id=?""",
             (b.title, b.description, b.spec, b.grade, D.js(b.stack), b.work_format, b.salary_from, b.salary_to, vacancy_id))
        return _vacancy_dict(D.q1("SELECT * FROM vacancies WHERE id = ?", (vacancy_id,)))

    @api.route("/api/employer/vacancies/<int:vacancy_id>/status", ("PATCH",), tag="Вакансии", summary="Опубликовать / закрыть вакансию", auth=EMP, body=VacancyStatusIn)
    def vacancy_status(ctx, vacancy_id):
        _own("vacancies", vacancy_id, ctx.user["id"])
        D.ex("UPDATE vacancies SET status = ? WHERE id = ?", (ctx.body.status, vacancy_id))
        return {"status": ctx.body.status}

    @api.route("/api/employer/vacancies/<int:vacancy_id>/applications", ("GET",), tag="Вакансии", summary="Отклики на вакансию", auth=EMP,
               description="Откликнувшийся кандидат раскрывает контакты — они приходят в `candidate.contacts`.")
    def vacancy_applications(ctx, vacancy_id):
        v = _own("vacancies", vacancy_id, ctx.user["id"])
        need = {"spec": v["spec"], "grade": v["grade"], "stack": D.jl(v["stack"], [])}
        integ, revealed = domain.integrity_map(), domain.revealed_ids(ctx.user["id"])
        items = []
        for a in D.qa("SELECT * FROM applications WHERE vacancy_id = ? ORDER BY id DESC", (vacancy_id,)):
            c = domain.candidate_by_user_id(a["candidate_id"])
            card = domain.employer_card(c, ctx.user["id"], need if c["grade"] else None, detailed=True, integ=integ, revealed=revealed) if c["grade"] else \
                {"code": c["pseudo_code"], "revealed": True, "contacts": {"full_name": c["full_name"], "email": c["email"], "phone": c["phone"]}}
            items.append({"id": a["id"], "status": a["status"], "message": a["message"], "created_at": a["created_at"], "candidate": card})
        return {"vacancy": _vacancy_dict(v), "items": items}

    @api.route("/api/employer/applications/<int:application_id>/status", ("POST",), tag="Вакансии", summary="Сменить статус отклика", auth=EMP, body=ApplicationStatusIn)
    def application_status(ctx, application_id):
        a = D.q1("""SELECT a.* FROM applications a JOIN vacancies v ON v.id = a.vacancy_id WHERE a.id = ? AND v.employer_id = ?""", (application_id, ctx.user["id"]))
        if a is None:
            raise ApiError(404, "not_found", "Отклик не найден")
        D.ex("UPDATE applications SET status = ?, updated_at = ? WHERE id = ?", (ctx.body.status, D.now(), application_id))
        return {"status": ctx.body.status}

    # ------------------------------------------------------------------ регулярные задания
    @api.route("/api/employer/microtasks", ("POST",), tag="Регулярные задания", summary="Создать короткое задание для кандидатов", auth=EMP, body=MicrotaskIn, status=201,
               description="Система периодически назначает задание кандидатам подходящей категории; ответ поддерживает их профиль в актуальном состоянии.")
    def create_microtask(ctx):
        b = ctx.body
        mid = D.ex("INSERT INTO microtasks(employer_id, title, body, spec, grade, kind, active, created_at) VALUES (?,?,?,?,?,?,?,?)",
                   (ctx.user["id"], b.title, b.body, b.spec, b.grade, b.kind, 1, D.now()))
        return {"id": mid, **b.model_dump()}

    @api.route("/api/employer/microtasks", ("GET",), tag="Регулярные задания", summary="Мои задания и ответы кандидатов", auth=EMP)
    def list_microtasks(ctx):
        rows = D.qa("""SELECT m.*, (SELECT COUNT(*) FROM microtask_assignments a WHERE a.task_id = m.id) AS assigned,
                              (SELECT COUNT(*) FROM microtask_assignments a WHERE a.task_id = m.id AND a.status != 'assigned') AS answered
                       FROM microtasks m WHERE m.employer_id = ? ORDER BY m.id DESC""", (ctx.user["id"],))
        return {"items": [{"id": r["id"], "title": r["title"], "body": r["body"], "spec": r["spec"], "grade": r["grade"], "kind": r["kind"],
                           "assigned": r["assigned"], "answered": r["answered"]} for r in rows]}

    @api.route("/api/employer/microtasks/<int:task_id>/submissions", ("GET",), tag="Регулярные задания", summary="Ответы кандидатов на задание", auth=EMP)
    def submissions(ctx, task_id):
        _own("microtasks", task_id, ctx.user["id"])
        integ, revealed = domain.integrity_map(), domain.revealed_ids(ctx.user["id"])
        items = []
        for a in D.qa("SELECT * FROM microtask_assignments WHERE task_id = ? AND status != 'assigned' ORDER BY id DESC", (task_id,)):
            c = domain.candidate_by_user_id(a["candidate_id"])
            items.append({"assignment_id": a["id"], "status": a["status"], "answer": a["answer"], "rating": a["rating"], "feedback": a["feedback"],
                          "submitted_at": a["submitted_at"],
                          "candidate": domain.employer_card(c, ctx.user["id"], None, integ=integ, revealed=revealed) if c["grade"] else {"code": c["pseudo_code"]}})
        return {"items": items}

    @api.route("/api/employer/assignments/<int:assignment_id>/rate", ("POST",), tag="Регулярные задания", summary="Оценить ответ кандидата", auth=EMP, body=RateIn,
               description="Оценка ≥ 4 дополнительно повышает актуальность профиля кандидата.")
    def rate(ctx, assignment_id):
        a = D.q1("""SELECT a.* FROM microtask_assignments a JOIN microtasks m ON m.id = a.task_id WHERE a.id = ? AND m.employer_id = ?""", (assignment_id, ctx.user["id"]))
        if a is None:
            raise ApiError(404, "not_found", "Ответ не найден")
        if a["status"] == "assigned":
            raise ApiError(409, "not_submitted", "Кандидат ещё не ответил")
        D.ex("UPDATE microtask_assignments SET status='rated', rating=?, feedback=?, rated_at=? WHERE id=?", (ctx.body.rating, ctx.body.feedback, D.now(), assignment_id))
        if ctx.body.rating >= 4 and a["status"] == "submitted":
            D.ex("UPDATE candidates SET micro_bonus = MIN(1.0, micro_bonus + 0.2) WHERE user_id = ?", (a["candidate_id"],))
        return {"status": "rated"}
