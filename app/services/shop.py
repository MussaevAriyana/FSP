"""Кошелёк и платные услуги (монетизация).

Деньги — целые рубли. Баланс = сумма проводок `wallet_tx`. Покупка атомарна: проверка баланса → проводка → запись в `purchases` → эффект.
Пополнение в этой версии — ДЕМО (`PAYMENTS_MODE=demo`): средства зачисляются без платёжного провайдера. Для боевого режима
`topup` нужно заменить на создание платежа в провайдере (ЮKassa / CloudPayments) и зачисление по вебхуку — см. документацию §11.

Принцип: платные услуги дают **видимость и дополнительную проверку**, но не подменяют результат теста: категория по-прежнему
присваивается только тестом, а любое платное преимущество в подборе помечается в «почему» и ограничено небольшим бонусом.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from flask import current_app

from .. import db as D
from ..apidoc import ApiError

BOOST_BONUS = 0.04    # добавка к итоговому баллу продвигаемого профиля (из 1.0)
EXPERT_BONUS = 0.05   # добавка к силе профиля за пройденный Expert-тест

CATALOG = {
    "profile_boost": {"role": "candidate", "title": "Поднять профиль в банке", "price": 299, "days": 7,
                      "desc": "7 дней профиль получает небольшой бонус к баллу в подборках и пометку «Продвигается». Категорию и результат теста не заменяет."},
    "expert_test": {"role": "candidate", "title": "Экспертный тест", "price": 990, "uses": 1,
                    "desc": "Одна попытка усложнённого теста (задания уровня 5 по вашей специализации, под прокторингом). Пройдёте — получите значок Expert и бонус к силе профиля."},
    "pro_badge": {"role": "candidate", "title": "Значок Pro", "price": 199, "days": 30,
                  "desc": "30 дней значок Pro в вашей карточке: работодатель видит, что вы активно ищете работу."},
    "vacancy_boost": {"role": "employer", "title": "Продвинуть вакансию", "price": 490, "days": 7, "needs_vacancy": True,
                      "desc": "7 дней вакансия показывается выше остальных в своей категории с пометкой «Продвигается»."},
    "invites_pack": {"role": "employer", "title": "Пакет приглашений +50 в сутки", "price": 1490, "days": 30,
                     "desc": "30 дней лимит приглашений — на 50 больше в сутки (антиспам-лимит остаётся для остальных)."},
    "expert_filter": {"role": "employer", "title": "Поиск среди Expert-кандидатов", "price": 1990, "days": 30,
                      "desc": "30 дней фильтр «только прошедшие Expert-тест» в банке кандидатов."},
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ts(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def balance(uid: int) -> int:
    return int(D.q1("SELECT COALESCE(SUM(amount), 0) AS b FROM wallet_tx WHERE user_id = ?", (uid,))["b"])


def active(uid: int, service: str) -> Optional[dict]:
    """Действующая покупка: срок не истёк / остались использования."""
    row = D.q1("""SELECT * FROM purchases WHERE user_id = ? AND service = ?
                  AND (expires_at IS NULL OR expires_at > ?) AND (uses_left IS NULL OR uses_left > 0) ORDER BY id DESC LIMIT 1""", (uid, service, _ts(_now())))
    return dict(row) if row else None


def is_active(uid: int, service: str) -> bool:
    return active(uid, service) is not None


def topup(uid: int, amount: int) -> dict:
    if current_app.config["PAYMENTS_MODE"] != "demo":
        raise ApiError(501, "payments_not_configured", "Платёжный провайдер не подключён. Обратитесь в поддержку.")
    D.ex("INSERT INTO wallet_tx(user_id, amount, kind, title, at) VALUES (?,?,?,?,?)", (uid, amount, "topup", "Пополнение (демо-режим)", D.now()))
    return {"balance": balance(uid)}


def buy(user: dict, service: str, vacancy_id: Optional[int] = None) -> dict:
    spec = CATALOG.get(service)
    if spec is None or spec["role"] != user["role"]:
        raise ApiError(404, "service_not_found", "Такой услуги нет")
    uid = user["id"]
    if spec.get("needs_vacancy"):
        v = D.q1("SELECT * FROM vacancies WHERE id = ? AND employer_id = ? AND status = 'published'", (vacancy_id or 0, uid))
        if v is None:
            raise ApiError(422, "vacancy_required", "Выберите свою опубликованную вакансию")
    if balance(uid) < spec["price"]:
        raise ApiError(402, "insufficient_funds", f"Недостаточно средств: нужно {spec['price']} ₽, на счёте {balance(uid)} ₽", {"price": spec["price"], "balance": balance(uid)})
    now = _now()
    base = now
    prev = active(uid, service) if spec.get("days") and not spec.get("needs_vacancy") else None
    if prev and prev["expires_at"]:
        base = datetime.strptime(prev["expires_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)   # продление, а не перезапись
    expires = _ts(base + timedelta(days=spec["days"])) if spec.get("days") else None
    title = spec["title"] + (f" · «{v['title']}»" if spec.get("needs_vacancy") else "")
    D.ex("INSERT INTO wallet_tx(user_id, amount, kind, title, at) VALUES (?,?,?,?,?)", (uid, -spec["price"], "purchase", title, D.now()))
    pid = D.ex("INSERT INTO purchases(user_id, service, title, price, params, created_at, expires_at, uses_left) VALUES (?,?,?,?,?,?,?,?)",
               (uid, service, title, spec["price"], D.js({"vacancy_id": vacancy_id} if vacancy_id else {}), D.now(), expires, spec.get("uses")))
    if service == "profile_boost":
        D.ex("UPDATE candidates SET boost_until = ? WHERE user_id = ?", (expires, uid))
    elif service == "vacancy_boost":
        cur = D.q1("SELECT boost_until FROM vacancies WHERE id = ?", (vacancy_id,))["boost_until"]
        start = max(now, datetime.strptime(cur, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)) if cur and cur > _ts(now) else now
        D.ex("UPDATE vacancies SET boost_until = ? WHERE id = ?", (_ts(start + timedelta(days=spec["days"])), vacancy_id))
    return {"purchase_id": pid, "title": title, "price": spec["price"], "expires_at": expires, "balance": balance(uid)}


def consume(uid: int, service: str) -> bool:
    """Списывает одно использование (экспертный тест). False, если нет оплаченных."""
    row = active(uid, service)
    if not row or row["uses_left"] is None:
        return False
    D.ex("UPDATE purchases SET uses_left = uses_left - 1 WHERE id = ?", (row["id"],))
    return True


def is_boosted(until: Optional[str]) -> bool:
    return bool(until and until > _ts(_now()))


def overview(user: dict) -> dict:
    uid = user["id"]
    items = []
    for key, s in CATALOG.items():
        if s["role"] != user["role"]:
            continue
        act = active(uid, key)
        items.append({"service": key, "title": s["title"], "price": s["price"], "description": s["desc"], "needs_vacancy": bool(s.get("needs_vacancy")),
                      "days": s.get("days"), "uses": s.get("uses"),
                      "active": bool(act) and not s.get("needs_vacancy"), "expires_at": act["expires_at"] if act else None,
                      "uses_left": act["uses_left"] if act else None})
    tx = [dict(r) for r in D.qa("SELECT id, amount, kind, title, at FROM wallet_tx WHERE user_id = ? ORDER BY id DESC LIMIT 30", (uid,))]
    return {"balance": balance(uid), "services": items, "transactions": tx, "demo": current_app.config["PAYMENTS_MODE"] == "demo"}
