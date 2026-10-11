"""Слой хранения: SQLite (стандартная библиотека), тонкая обёртка вокруг sqlite3.

Схема простая и переносима на PostgreSQL (типы TEXT/INTEGER/REAL, JSON хранится как TEXT).
"""
import json
import sqlite3
from datetime import datetime, timezone

from flask import g, current_app

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    pw_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('candidate','employer','moderator')),
    email_confirmed INTEGER NOT NULL DEFAULT 0,
    confirm_token TEXT,
    consent_pd_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    avatar TEXT
);

CREATE TABLE IF NOT EXISTS candidates (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    pseudo_code TEXT NOT NULL UNIQUE,
    full_name TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    city TEXT NOT NULL DEFAULT '',
    headline TEXT NOT NULL DEFAULT '',
    about TEXT NOT NULL DEFAULT '',
    experience_years REAL NOT NULL DEFAULT 0,
    roles TEXT NOT NULL DEFAULT '[]',
    soft_skills TEXT NOT NULL DEFAULT '[]',
    stack_declared TEXT NOT NULL DEFAULT '[]',
    stack_confirmed TEXT NOT NULL DEFAULT '[]',
    spec TEXT,
    grade TEXT,
    best_score REAL NOT NULL DEFAULT 0,
    category_assigned_at TEXT,
    last_grade_change_at TEXT,
    survey TEXT NOT NULL DEFAULT '{}',
    fsp_id TEXT,
    fsp_linked_at TEXT,
    consent_publish INTEGER NOT NULL DEFAULT 0,
    privacy TEXT NOT NULL DEFAULT '{}',
    micro_bonus REAL NOT NULL DEFAULT 0,
    last_activity_at TEXT,
    category_attempt_id INTEGER,
    resume TEXT NOT NULL DEFAULT '{}',
    expert INTEGER NOT NULL DEFAULT 0,
    boost_until TEXT
);

CREATE TABLE IF NOT EXISTS employers (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    company_name TEXT NOT NULL DEFAULT '',
    industry TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    website TEXT NOT NULL DEFAULT '',
    contact_name TEXT NOT NULL DEFAULT '',
    contact_method TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS test_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    spec TEXT NOT NULL,
    target_grade TEXT NOT NULL,
    seed TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    started_at TEXT NOT NULL,
    deadline_at TEXT NOT NULL,
    finished_at TEXT,
    questions TEXT NOT NULL,      -- полные задания вместе с ответами (только на сервере!)
    answers TEXT NOT NULL DEFAULT '{}',
    score REAL, max_score REAL, ratio REAL,
    passed INTEGER,
    topic_stats TEXT NOT NULL DEFAULT '{}',
    flags TEXT NOT NULL DEFAULT '{}',
    outcome TEXT NOT NULL DEFAULT '{}',
    review_state TEXT NOT NULL DEFAULT 'clean',   -- clean | flagged | cleared | annulled
    risk REAL NOT NULL DEFAULT 0,
    proctor TEXT NOT NULL DEFAULT '{}',
    times TEXT NOT NULL DEFAULT '{}',
    kind TEXT NOT NULL DEFAULT 'regular'          -- regular | expert (платный усложнённый тест)
);
CREATE INDEX IF NOT EXISTS ix_attempts_user ON test_attempts(user_id, started_at);

CREATE TABLE IF NOT EXISTS proctor_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    attempt_id INTEGER NOT NULL REFERENCES test_attempts(id) ON DELETE CASCADE,
    at TEXT NOT NULL,
    kind TEXT NOT NULL,
    weight REAL NOT NULL DEFAULT 0,
    meta TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS ix_pe_attempt ON proctor_events(attempt_id, id);

CREATE TABLE IF NOT EXISTS proctor_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    attempt_id INTEGER NOT NULL REFERENCES test_attempts(id) ON DELETE CASCADE,
    at TEXT NOT NULL,
    image TEXT NOT NULL,          -- data:image/jpeg;base64,… (хранится ограниченное время, см. PROCTOR_RETENTION_DAYS)
    note TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_ps_attempt ON proctor_snapshots(attempt_id, id);

CREATE TABLE IF NOT EXISTS moderation_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    attempt_id INTEGER NOT NULL REFERENCES test_attempts(id) ON DELETE CASCADE,
    moderator_id INTEGER NOT NULL,
    decision TEXT NOT NULL,
    comment TEXT NOT NULL DEFAULT '',
    at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS wallet_tx (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    amount INTEGER NOT NULL,          -- копейки не используем: целые рубли; + пополнение, − покупка
    kind TEXT NOT NULL,               -- topup | purchase
    title TEXT NOT NULL,
    at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_tx_user ON wallet_tx(user_id, id);

CREATE TABLE IF NOT EXISTS purchases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    service TEXT NOT NULL,
    title TEXT NOT NULL,
    price INTEGER NOT NULL,
    params TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    expires_at TEXT,
    uses_left INTEGER
);
CREATE INDEX IF NOT EXISTS ix_pur_user ON purchases(user_id, service);

CREATE TABLE IF NOT EXISTS support_tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    subject TEXT NOT NULL,
    message TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',      -- open | answered
    reply TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    answered_at TEXT
);

CREATE TABLE IF NOT EXISTS achievements (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    code TEXT NOT NULL,
    at TEXT NOT NULL,
    seen INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, code)
);

CREATE TABLE IF NOT EXISTS practice_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    spec TEXT NOT NULL,
    level INTEGER NOT NULL,
    topic TEXT NOT NULL,
    question TEXT NOT NULL,           -- с ответом; клиенту уходит без него
    created_at TEXT NOT NULL,
    solved INTEGER,                   -- NULL — не отвечено, 1 — верно, 0 — неверно
    answered_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_pi_user ON practice_items(user_id, solved);

CREATE TABLE IF NOT EXISTS grade_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    spec TEXT, old_grade TEXT, new_grade TEXT, reason TEXT, at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS needs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employer_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    spec TEXT NOT NULL,
    grade TEXT NOT NULL,
    stack TEXT NOT NULL DEFAULT '[]',
    team_desc TEXT NOT NULL DEFAULT '',
    work_format TEXT NOT NULL DEFAULT '',
    salary_from INTEGER, salary_to INTEGER,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS vacancies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employer_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    spec TEXT NOT NULL,
    grade TEXT NOT NULL,
    stack TEXT NOT NULL DEFAULT '[]',
    work_format TEXT NOT NULL DEFAULT '',
    salary_from INTEGER NOT NULL,
    salary_to INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'published',
    created_at TEXT NOT NULL,
    city TEXT NOT NULL DEFAULT '',
    employment TEXT NOT NULL DEFAULT '',
    requirements TEXT NOT NULL DEFAULT '',
    conditions TEXT NOT NULL DEFAULT '',
    boost_until TEXT
);

CREATE TABLE IF NOT EXISTS invites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employer_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    candidate_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    vacancy_id INTEGER REFERENCES vacancies(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    salary_from INTEGER NOT NULL,
    salary_to INTEGER NOT NULL,
    contact_method TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'sent',
    match_snapshot TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL, viewed_at TEXT, decided_at TEXT,
    stage TEXT NOT NULL DEFAULT '', stage_at TEXT, stage_log TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS ix_invites_cand ON invites(candidate_id, created_at);

CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vacancy_id INTEGER NOT NULL REFERENCES vacancies(id) ON DELETE CASCADE,
    candidate_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    message TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'sent',
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    UNIQUE (vacancy_id, candidate_id)
);

CREATE TABLE IF NOT EXISTS microtasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employer_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    spec TEXT NOT NULL,
    grade TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'approach',
    target_fsp_ids TEXT NOT NULL DEFAULT '[]',
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS microtask_assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES microtasks(id) ON DELETE CASCADE,
    candidate_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'assigned',
    answer TEXT, rating INTEGER, feedback TEXT,
    assigned_at TEXT NOT NULL, submitted_at TEXT, rated_at TEXT,
    UNIQUE (task_id, candidate_id)
);
"""


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_ts(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _columns(conn, table: str) -> set:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def _migrate(conn) -> None:
    """Мягкая миграция баз, созданных прежними версиями приложения."""
    adds = {"test_attempts": [("review_state", "TEXT NOT NULL DEFAULT 'clean'"), ("risk", "REAL NOT NULL DEFAULT 0"),
                              ("proctor", "TEXT NOT NULL DEFAULT '{}'"), ("times", "TEXT NOT NULL DEFAULT '{}'")],
            "candidates": [("category_attempt_id", "INTEGER"), ("resume", "TEXT NOT NULL DEFAULT '{}'"), ("expert", "INTEGER NOT NULL DEFAULT 0"), ("boost_until", "TEXT")],
            "vacancies": [("city", "TEXT NOT NULL DEFAULT ''"), ("employment", "TEXT NOT NULL DEFAULT ''"), ("requirements", "TEXT NOT NULL DEFAULT ''"),
                          ("conditions", "TEXT NOT NULL DEFAULT ''"), ("boost_until", "TEXT")]}
    adds["test_attempts"].append(("kind", "TEXT NOT NULL DEFAULT 'regular'"))
    adds["microtasks"] = [("target_fsp_ids", "TEXT NOT NULL DEFAULT '[]'")]
    adds["invites"] = [("stage", "TEXT NOT NULL DEFAULT ''"), ("stage_at", "TEXT"), ("stage_log", "TEXT NOT NULL DEFAULT '[]'")]
    for table, cols in adds.items():
        have = _columns(conn, table)
        for name, ddl in cols:
            if name not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
    sql = conn.execute("SELECT sql FROM sqlite_master WHERE name = 'users'").fetchone()
    if sql and "moderator" not in sql[0]:  # расширяем CHECK по роли
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("ALTER TABLE users RENAME TO users_old")
        conn.executescript(SCHEMA.split("CREATE TABLE IF NOT EXISTS candidates")[0])
        conn.execute("INSERT INTO users SELECT * FROM users_old")
        conn.execute("DROP TABLE users_old")
        conn.execute("PRAGMA foreign_keys = ON")
    if "avatar" not in _columns(conn, "users"):
        conn.execute("ALTER TABLE users ADD COLUMN avatar TEXT")


def init_db(path: str) -> None:
    conn = connect(path)
    conn.executescript(SCHEMA)
    _migrate(conn)
    conn.commit()
    conn.close()


def db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = connect(current_app.config["DB_PATH"])
    return g.db


def close_db(_exc=None) -> None:
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def q1(sql: str, args=()):
    return db().execute(sql, args).fetchone()


def qa(sql: str, args=()):
    return db().execute(sql, args).fetchall()


def ex(sql: str, args=()) -> int:
    cur = db().execute(sql, args)
    db().commit()
    return cur.lastrowid


def jl(s, default=None):
    """json.loads, терпимый к пустым значениям."""
    if s is None or s == "":
        return default
    return json.loads(s)


def js(v) -> str:
    return json.dumps(v, ensure_ascii=False)
