"""Пароли и токены.

Пароли: scrypt (стандартная библиотека) + индивидуальная соль, сравнение за постоянное время.
Токены: JWT HS256 (PyJWT). Точка расширения для ФСП ID/Keycloak описана в docs/DOCUMENTATION.md:
вместо `decode_token` подставляется проверка access-токена Keycloak по JWKS.
"""
import hashlib
import hmac
import os
import time
from typing import Optional

import jwt
from flask import current_app

_N, _R, _P = 2 ** 14, 8, 1


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt_hex, dk_hex = stored.split("$")
        dk = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex),
                            n=int(n), r=int(r), p=int(p), dklen=len(dk_hex) // 2)
        return hmac.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False


def make_token(user_id: int, role: str) -> str:
    ttl = current_app.config["TOKEN_TTL_HOURS"] * 3600
    payload = {"sub": str(user_id), "role": role, "iat": int(time.time()), "exp": int(time.time()) + ttl}
    return jwt.encode(payload, current_app.config["SECRET_KEY"], algorithm="HS256")


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, current_app.config["SECRET_KEY"], algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
