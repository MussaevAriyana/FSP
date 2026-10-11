"""Кабинет модератора: проверка попыток, помеченных прокторингом."""
from flask import Response

from .. import db as D
from ..apidoc import ApiError
from ..schemas import ModerationIn, SupportReplyIn
from ..services import proctor

MOD = ("moderator",)


def register(api):
    @api.route("/api/moderator/queue", ("GET",), tag="Модерация", summary="Очередь попыток на проверку", auth=MOD,
               description="state=flagged — ожидают решения (по умолчанию); decided — уже разобранные; all — все с ненулевым риском.")
    def queue(ctx):
        from flask import request
        state = request.args.get("state", "flagged")
        if state not in ("flagged", "decided", "all"):
            raise ApiError(422, "validation_error", "state: flagged | decided | all")
        return {"items": proctor.queue(state), "flag_at": proctor.FLAG_AT, "terminate_at": proctor.TERMINATE_AT}

    @api.route("/api/moderator/attempts/<int:attempt_id>", ("GET",), tag="Модерация", summary="Журнал прокторинга попытки", auth=MOD)
    def detail(ctx, attempt_id):
        return proctor.detail(attempt_id)

    @api.route("/api/moderator/snapshots/<int:snap_id>", ("GET",), tag="Модерация", summary="Снимок с камеры (JPEG)", auth=MOD)
    def snapshot(ctx, snap_id):
        r = D.q1("SELECT image FROM proctor_snapshots WHERE id = ?", (snap_id,))
        if r is None:
            raise ApiError(404, "not_found", "Снимок не найден (возможно, истёк срок хранения)")
        resp = Response(proctor.jpeg_bytes(r["image"]), mimetype="image/jpeg")
        resp.headers["Cache-Control"] = "private, no-store"
        return resp

    @api.route("/api/moderator/attempts/<int:attempt_id>/decision", ("POST",), tag="Модерация", summary="Снять отметку или аннулировать попытку",
               auth=MOD, body=ModerationIn,
               description="clear — результат остаётся, вес профиля восстанавливается. annul — попытка аннулируется; если категория была "
                           "присвоена этой попыткой, она снимается, и кандидату нужно пройти тест заново.")
    def decision(ctx, attempt_id):
        return proctor.decide(attempt_id, ctx.user["id"], ctx.body.decision, ctx.body.comment)

    @api.route("/api/moderator/support", ("GET",), tag="Модерация", summary="Обращения в поддержку", auth=MOD)
    def support_queue(ctx):
        rows = D.qa("""SELECT t.id, t.subject, t.message, t.status, t.reply, t.created_at, u.email, u.role FROM support_tickets t
                       JOIN users u ON u.id = t.user_id ORDER BY (t.status = 'open') DESC, t.id DESC LIMIT 100""")
        return {"items": [dict(r) for r in rows]}

    @api.route("/api/moderator/support/<int:ticket_id>/reply", ("POST",), tag="Модерация", summary="Ответить на обращение", auth=MOD, body=SupportReplyIn)
    def support_reply(ctx, ticket_id):
        if D.q1("SELECT 1 FROM support_tickets WHERE id = ?", (ticket_id,)) is None:
            raise ApiError(404, "not_found", "Обращение не найдено")
        D.ex("UPDATE support_tickets SET reply = ?, status = 'answered', answered_at = ? WHERE id = ?", (ctx.body.reply, D.now(), ticket_id))
        return {"status": "answered"}
