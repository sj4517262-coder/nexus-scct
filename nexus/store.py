"""SQLite transactions shared by REST, event replay and operational workflows."""
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


def uid(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class Store:
    def __init__(self, path):
        self.path = str(path).removeprefix("sqlite:///")

    @contextmanager
    def transaction(self):
        if self.path.startswith("postgresql"):
            import psycopg2
            from psycopg2.extras import DictCursor
            connection = psycopg2.connect(self.path.replace("postgresql+psycopg2", "postgresql"), cursor_factory=DictCursor)
            try:
                adapter = PostgresConnection(connection)
                # Preserve the local store's serialized mutation semantics across workers.
                adapter.execute("SELECT pg_advisory_xact_lock(72819402)")
                yield adapter
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.close()
            return
        con = sqlite3.connect(self.path, timeout=15)
        con.row_factory = sqlite3.Row
        try:
            con.execute("PRAGMA foreign_keys=ON")
            con.execute("BEGIN IMMEDIATE")
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def initialize(self):
        if not self.path.startswith("postgresql"):
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.transaction() as con:
            con.execute("CREATE TABLE IF NOT EXISTS records (kind TEXT, id TEXT, data TEXT NOT NULL, PRIMARY KEY(kind,id))")
            con.execute("CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT NOT NULL)")
            con.execute("CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, email TEXT UNIQUE, password TEXT NOT NULL, role TEXT NOT NULL)")
            con.execute("CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, user_id TEXT REFERENCES users(id), expires REAL NOT NULL)")
            con.execute("CREATE TABLE IF NOT EXISTS login_attempts (key TEXT PRIMARY KEY, attempts INTEGER NOT NULL, reset_at REAL NOT NULL)")
            con.execute("CREATE TABLE IF NOT EXISTS outbox (id TEXT PRIMARY KEY, topic TEXT NOT NULL, payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'PENDING', attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT, created_at TEXT NOT NULL)")
            con.execute("CREATE TABLE IF NOT EXISTS inbox (id TEXT PRIMARY KEY, processed_at TEXT NOT NULL)")
            con.execute("CREATE TABLE IF NOT EXISTS dead_letters (id TEXT PRIMARY KEY, payload TEXT NOT NULL, error TEXT NOT NULL, created_at TEXT NOT NULL)")
            if not self.get(con, "meta", "initialized"):
                from nexus.seed import seed
                seed(self, con)
                self.put(con, "meta", {"id": "initialized", "created_at": now()})

    @staticmethod
    def all(con, kind):
        return [json.loads(row[0]) for row in con.execute("SELECT data FROM records WHERE kind=? ORDER BY rowid", (kind,))]

    @staticmethod
    def get(con, kind, identifier):
        row = con.execute("SELECT data FROM records WHERE kind=? AND id=?", (kind, identifier)).fetchone()
        return json.loads(row[0]) if row else None

    @staticmethod
    def put(con, kind, record):
        con.execute("INSERT INTO records(kind,id,data) VALUES(?,?,?) ON CONFLICT(kind,id) DO UPDATE SET data=excluded.data", (kind, record["id"], json.dumps(record)))
        return record

    @staticmethod
    def event(con, kind, message, actor="system", entity_id=None, severity="LOW", details=None):
        event = dict(type=kind, message=message, actor=actor, entity_id=entity_id, severity=severity, timestamp=now(), details=details or {})
        cursor = con.execute("INSERT INTO events(data) VALUES(?)", (json.dumps(event),))
        return {**event, "seq": cursor.lastrowid}

    @staticmethod
    def enqueue(con, topic, payload, identifier=None):
        identifier = identifier or uid("EVT")
        payload = {**payload, "event_id": identifier, "created_at": now(), "schema_version": 1}
        con.execute("INSERT INTO outbox(id,topic,payload,status,attempts,created_at) VALUES(?,?,?,'PENDING',0,?) ON CONFLICT(id) DO NOTHING", (identifier,topic,json.dumps(payload),now()))
        return payload

    @staticmethod
    def events(con, after=0, limit=100):
        rows = con.execute("SELECT seq,data FROM events WHERE seq>? ORDER BY seq DESC LIMIT ?", (after, limit)).fetchall()
        return [{**json.loads(row["data"]), "seq": row["seq"]} for row in rows]


class PostgresConnection:
    """Small DB-API adapter; parameters remain bound, never interpolated."""
    def __init__(self, connection):
        self.connection = connection

    def execute(self, sql, parameters=()):
        sql = sql.replace("?", "%s").replace("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY").replace("ORDER BY rowid", "ORDER BY id").replace("expires REAL", "expires DOUBLE PRECISION").replace("reset_at REAL", "reset_at DOUBLE PRECISION")
        cursor = self.connection.cursor()
        event_insert = sql.startswith("INSERT INTO events(")
        if event_insert:
            sql += " RETURNING seq"
        cursor.execute(sql, parameters)
        return CursorResult(cursor, cursor.fetchone()[0] if event_insert else None)


class CursorResult:
    def __init__(self, cursor, lastrowid=None):
        self.cursor, self.lastrowid = cursor, lastrowid
        self.rowcount = cursor.rowcount

    def fetchone(self):
        return self.cursor.fetchone()

    def fetchall(self):
        return self.cursor.fetchall()

    def __iter__(self):
        return iter(self.cursor)
