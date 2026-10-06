"""Конфигурация приложения. Все параметры переопределяются переменными окружения."""
import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


class Config:
    # --- общие ---
    DB_PATH = os.environ.get("DB_PATH", str(BASE_DIR / "data" / "app.db"))
    # В production обязательно задайте SECRET_KEY. Без него ключ случайный на каждый запуск
    # (все выданные токены перестанут действовать после перезапуска).
    SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    TOKEN_TTL_HOURS = _env_int("TOKEN_TTL_HOURS", 12)
    PUBLIC_URL = os.environ.get("PUBLIC_URL", "http://localhost:8000")

    # --- e-mail ---
    # DEV_MODE=1: письмо не отправляется, ссылка подтверждения возвращается в ответе API
    # и пишется в лог. Для боевого режима задайте SMTP_* и DEV_MODE=0.
    DEV_MODE = os.environ.get("DEV_MODE", "1") == "1"
    SMTP_HOST = os.environ.get("SMTP_HOST", "")
    SMTP_PORT = _env_int("SMTP_PORT", 587)
    SMTP_USER = os.environ.get("SMTP_USER", "")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
    SMTP_FROM = os.environ.get("SMTP_FROM", "no-reply@fsp-talent.local")

    # --- тестирование ---
    GRADE_COOLDOWN_DAYS = _env_int("GRADE_COOLDOWN_DAYS", 90)   # смена грейда не чаще 1 раза в N дней
    TEST_ATTEMPTS_PER_DAY = _env_int("TEST_ATTEMPTS_PER_DAY", 5)
    TEST_TIME_LIMIT_MIN = _env_int("TEST_TIME_LIMIT_MIN", 40)
    PASS_THRESHOLD = float(os.environ.get("PASS_THRESHOLD", "0.65"))

    # --- антиспам ---
    INVITES_PER_DAY = _env_int("INVITES_PER_DAY", 25)
    MICROTASKS_PER_WEEK = _env_int("MICROTASKS_PER_WEEK", 2)

    # --- ФСП ---
    FSP_REGISTRY_FILE = os.environ.get("FSP_REGISTRY_FILE", str(BASE_DIR / "data" / "fsp_registry.json"))
