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
    role TEXT NOT NULL CHECK (role IN ('candidate','employer')),
    email_confirmed INTEGER NOT NULL DEFAULT 0,
    confirm_token TEXT,
    consent_pd_at TEXT NOT NULL,
    created_at TEXT NOT NULL
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
    last_activity_at TEXT
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
    outcome TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS ix_attempts_user ON test_attempts(user_id, started_at);

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
    created_at TEXT NOT NULL
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
    created_at TEXT NOT NULL, viewed_at TEXT, decided_at TEXT
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


def init_db(path: str) -> None:
    conn = connect(path)
    conn.executescript(SCHEMA)
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
