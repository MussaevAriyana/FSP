"""Кабинет кандидата: резюме, тренировка, награды."""
from .. import db as D
from ..schemas import PracticeAnswerIn, PracticeNextIn, ResumeIn
from ..services import domain, practice, resume as resume_mod, rewards

CAND = ("candidate",)


def register(api):
    @api.route("/api/candidate/resume", ("GET",), tag="Резюме", summary="Моё резюме в сервисе", auth=CAND,
               description="Опыт работы, проекты, образование, дипломы и сертификаты. Работодатель видит резюме только в разделах, разрешённых настройкой приватности "
                           "«стаж, роли и о себе»; названия компаний, вузов и ссылки скрыты до принятия приглашения.")
    def get_resume(ctx):
        c = domain.get_candidate(ctx.user["id"])
        full = {**ResumeIn().model_dump(), **c["resume"]}
        return {**full, "progress": rewards.resume_progress(full), "advice": resume_mod.resume_advice(full, c)}

    @api.route("/api/candidate/resume", ("PUT",), tag="Резюме", summary="Сохранить резюме", auth=CAND, body=ResumeIn)
    def put_resume(ctx):
        data = ctx.body.model_dump()
        # пустые записи не храним
        data["experience"] = [e for e in data["experience"] if e["company"] or e["position"]]
        data["projects"] = [p for p in data["projects"] if p["name"]]
        data["education"] = [e for e in data["education"] if e["institution"]]
        data["certificates"] = [x for x in data["certificates"] if x["name"]]
        data["languages"] = [x for x in data["languages"] if x["name"]]
        D.ex("UPDATE candidates SET resume = ? WHERE user_id = ?", (D.js(data), ctx.user["id"]))
        domain.touch(ctx.user["id"])
        return {**data, "progress": rewards.resume_progress(data), "advice": resume_mod.resume_advice(data, domain.get_candidate(ctx.user["id"])),
                "rewards": rewards.sync(ctx.user["id"])["new"]}

    @api.route("/api/candidate/practice/next", ("POST",), tag="Тренировка", summary="Следующее задание для тренировки", auth=CAND, body=PracticeNextIn,
               description="Задание порождается заново; неотвеченное задание того же уровня возвращается повторно. Категорию и подбор тренировка не затрагивает.")
    def practice_next(ctx):
        return practice.next_item(ctx.user["id"], ctx.body.spec, ctx.body.level)

    @api.route("/api/candidate/practice/<int:item_id>/answer", ("POST",), tag="Тренировка", summary="Ответить и получить разбор", auth=CAND, body=PracticeAnswerIn)
    def practice_answer(ctx, item_id):
        res = practice.answer(ctx.user["id"], item_id, ctx.body.answer)
        res["rewards"] = rewards.sync(ctx.user["id"])["new"]
        return res

    @api.route("/api/candidate/practice/<int:item_id>/skip", ("POST",), tag="Тренировка", summary="Пропустить задание", auth=CAND)
    def practice_skip(ctx, item_id):
        practice.skip(ctx.user["id"], item_id)
        return {"skipped": True}

    @api.route("/api/candidate/practice/stats", ("GET",), tag="Тренировка", summary="Моя статистика тренировки", auth=CAND)
    def practice_stats(ctx):
        return practice.stats(ctx.user["id"])

    @api.route("/api/candidate/achievements", ("GET",), tag="Награды", summary="Награды, очки и уровень", auth=CAND,
               description="Значки за профиль, резюме, тесты, тренировку и отклики. Поле `new` — полученные только что.")
    def achievements(ctx):
        return rewards.sync(ctx.user["id"])
