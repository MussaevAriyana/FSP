"""Публичные справочники и сведения о платформе."""
import json

from flask import current_app

from .. import db as D
from ..taxonomy import taxonomy_payload


def register(api):
    @api.route("/api/health", ("GET",), tag="Служебные", summary="Проверка работоспособности", auth=None)
    def health(ctx):
        D.q1("SELECT 1")
        from .. import BUILD
        return {"status": "ok", "build": BUILD}

    @api.route("/api/taxonomy", ("GET",), tag="Справочники", summary="Специализации, грейды, стек, вопросы опроса", auth=None)
    def taxonomy(ctx):
        return taxonomy_payload()

    @api.route("/api/about", ("GET",), tag="Справочники", summary="Сведения о Федерации спортивного программирования (подвал сайта)", auth=None,
               description="Читается из файла FSP_ABOUT_FILE (data/fsp_about.json). Пустые реквизиты в интерфейсе не показываются.")
    def about(ctx):
        try:
            with open(current_app.config["FSP_ABOUT_FILE"], encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = {"name": "Федерация спортивного программирования", "short": "ФСП"}
        data.pop("note", None)
        return data

    @api.route("/api/stats", ("GET",), tag="Справочники", summary="Агрегированная статистика платформы (для главной страницы)", auth=None,
               description="Только обезличенные числа: без персональных данных.")
    def stats(ctx):
        cats = D.qa("""SELECT spec, grade, COUNT(*) AS n FROM candidates WHERE grade IS NOT NULL AND consent_publish = 1 GROUP BY spec, grade""")
        return {"candidates_categorized": sum(r["n"] for r in cats),
                "employers": D.q1("SELECT COUNT(*) AS n FROM employers")["n"],
                "vacancies_open": D.q1("SELECT COUNT(*) AS n FROM vacancies WHERE status = 'published'")["n"],
                "invites_sent": D.q1("SELECT COUNT(*) AS n FROM invites")["n"],
                "categories": [{"spec": r["spec"], "grade": r["grade"], "count": r["n"]} for r in cats]}

    @api.route("/api/public/showcase", ("GET",), tag="Справочники", summary="Витрина главной страницы: обезличенные кандидаты и открытые вакансии", auth=None,
               description="Без имён и контактов: код-псевдоним, категория, результат теста и подтверждённый стек — только у тех, кто разрешил публикацию профиля.")
    def showcase(ctx):
        from ..services import domain, shop
        from ..taxonomy import category_label
        rows = sorted(domain.visible_candidate_rows(), key=lambda c: (-c["best_score"], c["pseudo_code"]))[:6]
        cands = [{"code": c["pseudo_code"], "category": category_label(c["spec"], c["grade"]), "spec": c["spec"], "grade": c["grade"], "score": round(c["best_score"] * 100),
                  "stack": (c["stack_confirmed"] or [])[:5], "fsp": bool(c["fsp_id"]), "expert": bool(c.get("expert"))} for c in rows
                 if c["privacy"].get("visible_in_bank", True)]
        vs = D.qa("""SELECT v.id, v.title, v.spec, v.grade, v.salary_from, v.salary_to, v.work_format, v.city, v.stack, v.boost_until, e.company_name
                     FROM vacancies v JOIN employers e ON e.user_id = v.employer_id WHERE v.status = 'published' ORDER BY v.id DESC LIMIT 30""")
        vs = sorted(vs, key=lambda r: (not shop.is_boosted(r["boost_until"]), -r["id"]))[:6]
        vac = [{"id": r["id"], "title": r["title"], "company": r["company_name"], "category": category_label(r["spec"], r["grade"]), "salary_from": r["salary_from"],
                "salary_to": r["salary_to"], "work_format": r["work_format"], "city": r["city"], "stack": D.jl(r["stack"], [])[:4]} for r in vs]
        return {"candidates": cands, "vacancies": vac}
