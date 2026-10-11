"""Создаёт (или обновляет пароль) учётную запись модератора прокторинга.

    python scripts/create_moderator.py moderator@example.ru 'ПарольНеКороче8'
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import create_app  # noqa: E402
from app import db as D  # noqa: E402
from app.security import hash_password  # noqa: E402


def create(email: str, password: str) -> str:
    if len(password) < 8:
        raise SystemExit("Пароль — не короче 8 символов")
    email = email.strip().lower()
    row = D.q1("SELECT id, role FROM users WHERE email = ?", (email,))
    if row and row["role"] != "moderator":
        raise SystemExit("Этот e-mail уже занят учётной записью другой роли")
    if row:
        D.ex("UPDATE users SET pw_hash = ? WHERE id = ?", (hash_password(password), row["id"]))
        return "updated"
    D.ex("""INSERT INTO users(email, pw_hash, role, email_confirmed, consent_pd_at, created_at) VALUES (?,?,?,?,?,?)""",
         (email, hash_password(password), "moderator", 1, D.now(), D.now()))
    return "created"


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    app = create_app()
    with app.app_context():
        print(create(sys.argv[1], sys.argv[2]))
