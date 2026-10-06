"""Публичные справочники и сведения о платформе."""
from .. import db as D
from ..taxonomy import taxonomy_payload


def register(api):
    @api.route("/api/health", ("GET",), tag="Служебные", summary="Проверка работоспособности", auth=None)
    def health(ctx):
        D.q1("SELECT 1")
        return {"status": "ok"}

    @api.route("/api/taxonomy", ("GET",), tag="Справочники", summary="Специализации, грейды, стек, вопросы опроса", auth=None)
    def taxonomy(ctx):
        return taxonomy_payload()

    @api.route("/api/stats", ("GET",), tag="Справочники", summary="Агрегированная статистика платформы (для главной страницы)", auth=None,
               description="Только обезличенные числа: без персональных данных.")
    def stats(ctx):
        cats = D.qa("""SELECT spec, grade, COUNT(*) AS n FROM candidates WHERE grade IS NOT NULL AND consent_publish = 1 GROUP BY spec, grade""")
        return {"candidates_categorized": sum(r["n"] for r in cats),
                "employers": D.q1("SELECT COUNT(*) AS n FROM employers")["n"],
                "vacancies_open": D.q1("SELECT COUNT(*) AS n FROM vacancies WHERE status = 'published'")["n"],
                "invites_sent": D.q1("SELECT COUNT(*) AS n FROM invites")["n"],
                "categories": [{"spec": r["spec"], "grade": r["grade"], "count": r["n"]} for r in cats]}
