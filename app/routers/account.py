"""Общие для кандидата и работодателя: фото/логотип, кошелёк и платные услуги, поддержка."""
from .. import db as D
from ..schemas import AvatarIn, BuyIn, SupportIn, TopupIn
from ..services import shop

BOTH = ("candidate", "employer")


def register(api):
    @api.route("/api/account/avatar", ("PUT",), tag="Аккаунт", summary="Загрузить фото профиля или логотип компании", auth=BOTH, body=AvatarIn,
               description="Показывается в меню аккаунта; у работодателя — как логотип в вакансиях. Фотографию кандидата работодатели не видят (псевдонимность).")
    def set_avatar(ctx):
        D.ex("UPDATE users SET avatar = ? WHERE id = ?", (ctx.body.image, ctx.user["id"]))
        return {"avatar": ctx.body.image}

    @api.route("/api/account/avatar", ("DELETE",), tag="Аккаунт", summary="Удалить фото", auth=BOTH)
    def del_avatar(ctx):
        D.ex("UPDATE users SET avatar = NULL WHERE id = ?", (ctx.user["id"],))
        return {"avatar": None}

    @api.route("/api/wallet", ("GET",), tag="Кошелёк и услуги", summary="Баланс, каталог услуг своей роли, история операций", auth=BOTH)
    def wallet(ctx):
        return shop.overview(ctx.user)

    @api.route("/api/wallet/topup", ("POST",), tag="Кошелёк и услуги", summary="Пополнить кошелёк", auth=BOTH, body=TopupIn,
               description="В демо-режиме (`PAYMENTS_MODE=demo`) зачисляется сразу; иначе 501 — платёжный провайдер не подключён.")
    def topup(ctx):
        return shop.topup(ctx.user["id"], ctx.body.amount)

    @api.route("/api/wallet/buy", ("POST",), tag="Кошелёк и услуги", summary="Купить услугу", auth=BOTH, body=BuyIn, status=201,
               description="402 `insufficient_funds`, если на счёте не хватает средств. Повторная покупка срочной услуги продлевает срок.")
    def buy(ctx):
        return shop.buy(ctx.user, ctx.body.service, ctx.body.vacancy_id)

    @api.route("/api/support", ("POST",), tag="Поддержка", summary="Написать в поддержку", auth=BOTH, body=SupportIn, status=201)
    def support_new(ctx):
        tid = D.ex("INSERT INTO support_tickets(user_id, subject, message, created_at) VALUES (?,?,?,?)",
                   (ctx.user["id"], ctx.body.subject, ctx.body.message, D.now()))
        return {"id": tid, "status": "open"}

    @api.route("/api/support", ("GET",), tag="Поддержка", summary="Мои обращения и ответы", auth=BOTH)
    def support_list(ctx):
        rows = D.qa("SELECT id, subject, message, status, reply, created_at, answered_at FROM support_tickets WHERE user_id = ? ORDER BY id DESC LIMIT 50",
                    (ctx.user["id"],))
        return {"items": [dict(r) for r in rows]}
