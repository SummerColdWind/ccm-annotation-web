import hashlib
import hmac
import os
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE, display_name TEXT NOT NULL,
 password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','annotator')),
 enabled INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS sessions (
 token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), csrf TEXT NOT NULL, expires REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS login_attempts (bucket TEXT PRIMARY KEY, attempts INTEGER NOT NULL, expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS datasets (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, root TEXT NOT NULL UNIQUE, mode TEXT NOT NULL CHECK(mode IN ('independent','shared')),
 active INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS images (
 id INTEGER PRIMARY KEY, dataset_id INTEGER NOT NULL REFERENCES datasets(id), relpath TEXT NOT NULL,
 sha256 TEXT NOT NULL, width INTEGER NOT NULL, height INTEGER NOT NULL, UNIQUE(dataset_id,relpath)
);
CREATE TABLE IF NOT EXISTS assignments (
 id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), image_id INTEGER NOT NULL REFERENCES images(id),
 position INTEGER NOT NULL, draft TEXT, revision INTEGER NOT NULL DEFAULT 0,
 UNIQUE(user_id,image_id)
);
CREATE INDEX IF NOT EXISTS assignments_user ON assignments(user_id,position);
CREATE INDEX IF NOT EXISTS assignments_image ON assignments(image_id);
CREATE TABLE IF NOT EXISTS annotations (
 assignment_id INTEGER PRIMARY KEY REFERENCES assignments(id), labels TEXT NOT NULL, manual_version TEXT NOT NULL,
 submitted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS annotation_audit (
 id INTEGER PRIMARY KEY, assignment_id INTEGER NOT NULL REFERENCES assignments(id), labels TEXT NOT NULL,
 manual_version TEXT NOT NULL, revision INTEGER NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


@contextmanager
def connect(path):
    db = sqlite3.connect(path, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    try:
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def initialize(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript(SCHEMA)


def password_hash(password):
    if not isinstance(password, str) or not 10 <= len(password) <= 128:
        raise ValueError("密码长度须为 10–128 个字符")
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 600_000).hex()
    return f"pbkdf2_sha256$600000${salt}${digest}"


def verify_password(password, stored):
    if not isinstance(password, str) or len(password) > 128:
        return False
    _, rounds, salt, expected = stored.split("$")
    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(rounds)).hex()
    return hmac.compare_digest(actual, expected)


def default_db():
    return os.getenv("CCM_DB", str(Path(__file__).resolve().parents[1] / "data" / "ccm.sqlite3"))
