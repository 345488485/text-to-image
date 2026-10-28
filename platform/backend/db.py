from contextlib import contextmanager
from pathlib import Path
import sqlite3

SCHEMA = '''
CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE, password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','user')), is_active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), csrf_token TEXT NOT NULL, expires_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id), prompt TEXT NOT NULL, negative_prompt TEXT NOT NULL DEFAULT '', steps INTEGER NOT NULL, seed INTEGER NOT NULL, status TEXT NOT NULL CHECK(status IN ('queued','running','succeeded','failed','cancelled')), created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT, error TEXT, prompt_id TEXT, image_path TEXT, image_sha256 TEXT, elapsed_seconds REAL);
CREATE INDEX IF NOT EXISTS jobs_owner_created ON jobs(owner_id,created_at DESC);
CREATE INDEX IF NOT EXISTS jobs_status_created ON jobs(status,created_at);
CREATE INDEX IF NOT EXISTS sessions_user ON sessions(user_id);
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
'''

class ManagedConnection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


class Database:
    def __init__(self,path):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as c:
            c.executescript(SCHEMA)
            columns = {row[1] for row in c.execute('PRAGMA table_info(users)')}
            if 'must_change_password' not in columns:
                c.execute('ALTER TABLE users ADD COLUMN must_change_password INTEGER NOT NULL DEFAULT 0')
            job_columns = {row[1] for row in c.execute('PRAGMA table_info(jobs)')}
            for side in ('width', 'height'):
                if side not in job_columns:
                    c.execute(f'ALTER TABLE jobs ADD COLUMN {side} INTEGER NOT NULL DEFAULT 512')
            c.execute('PRAGMA journal_mode=WAL')

    def connect(self):
        c=sqlite3.connect(self.path,timeout=15,factory=ManagedConnection)
        c.row_factory=sqlite3.Row
        c.execute('PRAGMA foreign_keys=ON')
        c.execute('PRAGMA busy_timeout=15000')
        return c

    @contextmanager
    def transaction(self):
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            yield c

    def one(self,sql,params=()):
        with self.connect() as c:
            row=c.execute(sql,params).fetchone()
            return dict(row) if row else None

    def all(self,sql,params=()):
        with self.connect() as c:
            return [dict(row) for row in c.execute(sql,params).fetchall()]

    def execute(self,sql,params=()):
        with self.connect() as c:
            return c.execute(sql,params).rowcount
