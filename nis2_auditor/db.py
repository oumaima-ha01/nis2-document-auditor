from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4

from .config import DB


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def uid() -> str:
    return uuid4().hex


@contextmanager
def connect():
    conn = sqlite3.connect(DB, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS audits (
          id TEXT PRIMARY KEY, name TEXT NOT NULL, profile_json TEXT NOT NULL,
          status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS documents (
          id TEXT PRIMARY KEY, audit_id TEXT NOT NULL REFERENCES audits(id) ON DELETE CASCADE,
          name TEXT NOT NULL, ext TEXT NOT NULL, sha256 TEXT NOT NULL,
          status TEXT NOT NULL, error TEXT, page_count INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_documents_audit ON documents(audit_id);
        CREATE TABLE IF NOT EXISTS elements (
          id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
          kind TEXT NOT NULL, locator TEXT NOT NULL, text TEXT NOT NULL,
          metadata_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS idx_elements_document ON elements(document_id);
        CREATE TABLE IF NOT EXISTS assessments (
          id TEXT PRIMARY KEY, audit_id TEXT NOT NULL REFERENCES audits(id) ON DELETE CASCADE,
          requirement_id TEXT NOT NULL, applicability TEXT NOT NULL,
          status TEXT NOT NULL, rationale TEXT NOT NULL,
          source TEXT NOT NULL, reviewed INTEGER NOT NULL DEFAULT 0,
          reviewer_note TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL,
          UNIQUE(audit_id, requirement_id)
        );
        CREATE TABLE IF NOT EXISTS evidence (
          id TEXT PRIMARY KEY, assessment_id TEXT NOT NULL REFERENCES assessments(id) ON DELETE CASCADE,
          element_id TEXT NOT NULL REFERENCES elements(id) ON DELETE CASCADE,
          quote TEXT NOT NULL, explanation TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_evidence_assessment ON evidence(assessment_id);
        """)


def rowdict(row):
    return dict(row) if row is not None else None

