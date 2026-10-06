"""Регистрация (e-mail + подтверждение), вход, профиль аккаунта, удаление аккаунта (право на удаление, 152-ФЗ)."""
import logging
import secrets
import smtplib
import time
from collections import defaultdict
from email.message import EmailMessage

from flask import current_app

from .. import db as D
from ..apidoc import ApiError
from ..schemas import ConfirmIn, DeleteAccountIn, LoginIn, RegisterIn, ResendIn
from ..security import hash_password, make_token, verify_password
from ..services import domain

log = logging.getLogger("fsp.auth")
_fails: dict = defaultdict(list)  # email -> метки времени неудачных входов
MAX_FAILS, WINDOW = 5, 15 * 60


def _send_confirmation(email: str, token: str) -> str:
    url = f"{current_app.config['PUBLIC_URL']}/#/confirm/{token}"
    if current_app.config["DEV_MODE"] or not current_app.config["SMTP_HOST"]:
        log.warning("DEV: ссылка подтверждения для %s: %s", email, url)
        return url
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = "Подтвердите адрес электронной почты — ФСП Карьера", current_app.config["SMTP_FROM"], email
    msg.set_content(f"Здравствуйте!\n\nДля завершения регистрации перейдите по ссылке:\n{url}\n\nЕсли вы не регистрировались — просто проигнорируйте письмо.")
    with smtplib.SMTP(current_app.config["SMTP_HOST"], current_app.config["SMTP_PORT"], timeout=10) as s:
        s.starttls()
        if current_app.config["SMTP_USER"]:
            s.login(current_app.config["SMTP_USER"], current_app.config["SMTP_PASSWORD"])
        s.send_message(msg)
    return ""


def register(api):
    @api.route("/api/auth/register", ("POST",), tag="Авторизация", summary="Регистрация по e-mail", auth=None, body=RegisterIn, status=201,
               ok="Аккаунт создан, на почту отправлена ссылка подтверждения",
               description="Требуется согласие на обработку персональных данных (152-ФЗ). В DEV_MODE ссылка подтверждения возвращается в ответе (`dev_confirm_url`).")
    def register_user(ctx):
        b = ctx.body
        if D.q1("SELECT 1 FROM users WHERE email = ?", (b.email,)):
            raise ApiError(409, "email_taken", "Пользователь с таким e-mail уже зарегистрирован")
        token = secrets.token_urlsafe(24)
        uid = D.ex("""INSERT INTO users(email, pw_hash, role, email_confirmed, confirm_token, consent_pd_at, created_at)
                      VALUES (?,?,?,?,?,?,?)""", (b.email, hash_password(b.password), b.role, 0, token, D.now(), D.now()))
        if b.role == "candidate":
            D.ex("INSERT INTO candidates(user_id, pseudo_code, full_name, privacy) VALUES (?,?,?,?)",
                 (uid, domain.new_pseudo_code(), b.full_name, D.js(domain.DEFAULT_PRIVACY)))
        else:
            D.ex("INSERT INTO employers(user_id, company_name, contact_name) VALUES (?,?,?)", (uid, b.company_name, b.full_name))
        url = _send_confirmation(b.email, token)
        resp = {"message": "Мы отправили письмо со ссылкой подтверждения на вашу почту."}
        if current_app.config["DEV_MODE"]:
            resp["dev_confirm_url"] = url
            resp["dev_token"] = token
        return resp

    @api.route("/api/auth/confirm", ("POST",), tag="Авторизация", summary="Подтверждение e-mail", auth=None, body=ConfirmIn,
               ok="E-mail подтверждён; в ответе — токен доступа")
    def confirm(ctx):
        row = D.q1("SELECT * FROM users WHERE confirm_token = ?", (ctx.body.token,))
        if row is None:
            raise ApiError(400, "bad_token", "Ссылка недействительна или уже использована")
        D.ex("UPDATE users SET email_confirmed = 1, confirm_token = NULL WHERE id = ?", (row["id"],))
        return {"token": make_token(row["id"], row["role"]), "user": {"id": row["id"], "email": row["email"], "role": row["role"]}}

    @api.route("/api/auth/resend", ("POST",), tag="Авторизация", summary="Повторная отправка письма подтверждения", auth=None, body=ResendIn)
    def resend(ctx):
        row = D.q1("SELECT * FROM users WHERE email = ? AND email_confirmed = 0", (ctx.body.email,))
        resp = {"message": "Если адрес зарегистрирован и не подтверждён, мы отправили письмо повторно."}
        if row:
            token = secrets.token_urlsafe(24)
            D.ex("UPDATE users SET confirm_token = ? WHERE id = ?", (token, row["id"]))
            url = _send_confirmation(row["email"], token)
            if current_app.config["DEV_MODE"]:
                resp["dev_confirm_url"], resp["dev_token"] = url, token
        return resp

    @api.route("/api/auth/login", ("POST",), tag="Авторизация", summary="Вход", auth=None, body=LoginIn, ok="Токен доступа (JWT)")
    def login(ctx):
        email = ctx.body.email
        now = time.time()
        _fails[email] = [t for t in _fails[email] if now - t < WINDOW]
        if len(_fails[email]) >= MAX_FAILS:
            raise ApiError(429, "too_many_attempts", "Слишком много неудачных попыток. Повторите через 15 минут")
        row = D.q1("SELECT * FROM users WHERE email = ?", (email,))
        ok = verify_password(ctx.body.password, row["pw_hash"] if row else "scrypt$16384$8$1$00$00")
        if not (row and ok):
            _fails[email].append(now)
            raise ApiError(401, "bad_credentials", "Неверный e-mail или пароль")
        if not row["email_confirmed"]:
            raise ApiError(403, "email_not_confirmed", "Подтвердите адрес электронной почты по ссылке из письма")
        _fails.pop(email, None)
        return {"token": make_token(row["id"], row["role"]), "user": {"id": row["id"], "email": row["email"], "role": row["role"]}}

    @api.route("/api/auth/me", ("GET",), tag="Авторизация", summary="Текущий пользователь", allow_unconfirmed=True)
    def me(ctx):
        u = ctx.user
        return {"id": u["id"], "email": u["email"], "role": u["role"], "email_confirmed": bool(u["email_confirmed"])}

    @api.route("/api/auth/account", ("DELETE",), tag="Авторизация", summary="Удалить аккаунт и все данные", body=DeleteAccountIn,
               description="Право субъекта на удаление персональных данных (152-ФЗ): аккаунт и связанные данные удаляются безвозвратно.")
    def delete_account(ctx):
        if not verify_password(ctx.body.password, ctx.user["pw_hash"]):
            raise ApiError(403, "bad_credentials", "Неверный пароль")
        D.ex("DELETE FROM users WHERE id = ?", (ctx.user["id"],))
        return {"deleted": True}
