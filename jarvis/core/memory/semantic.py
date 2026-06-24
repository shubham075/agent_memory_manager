"""
Tier 1 — Semantic Memory (Persistent SQLite Fact Store)
-------------------------------------------------------
Stores permanent user facts (name, preferences, projects, etc.)
that survive all sessions. This is JARVIS's long-term knowledge of you.

Schema:
    user_facts(key TEXT PK, value TEXT, category TEXT, updated_at TEXT)

Categories:
    identity    — name, age, location
    work        — job, projects, skills
    preferences — likes, dislikes, habits
    system      — internal JARVIS config facts
"""
import sqlite3
from datetime import datetime, timezone
from core.config import SQLITE_DB_PATH


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_semantic_db() -> None:
    """Auto-create table on first run. Safe to call repeatedly."""
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_facts (
                key        TEXT PRIMARY KEY,
                value      TEXT NOT NULL,
                category   TEXT NOT NULL DEFAULT 'general',
                updated_at TEXT NOT NULL
            )
        """)
        conn.commit()


def write_fact(key: str, value: str, category: str = "general") -> None:
    """Insert or update a fact. Thread-safe via SQLite WAL mode."""
    with _connect() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            INSERT INTO user_facts (key, value, category, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value      = excluded.value,
                category   = excluded.category,
                updated_at = excluded.updated_at
            """,
            (key, str(value), category, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()


def read_facts(category: str | None = None) -> dict[str, str]:
    """Return all facts as {key: value}. Optionally filter by category."""
    with _connect() as conn:
        if category:
            rows = conn.execute(
                "SELECT key, value FROM user_facts WHERE category = ?", (category,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT key, value FROM user_facts").fetchall()
    return {row["key"]: row["value"] for row in rows}


def delete_fact(key: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM user_facts WHERE key = ?", (key,))
        conn.commit()


def facts_as_text() -> str:
    """Render all facts as a compact bulleted string for injection into system prompt."""
    facts = read_facts()
    if not facts:
        return "No user profile data stored yet."
    return "\n".join(f"  • {k}: {v}" for k, v in sorted(facts.items()))


def bulk_write_facts(facts: dict[str, tuple[str, str]]) -> None:
    """Write many facts at once. facts = {key: (value, category)}"""
    with _connect() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        now = datetime.now(timezone.utc).isoformat()
        conn.executemany(
            """
            INSERT INTO user_facts (key, value, category, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value=excluded.value, category=excluded.category, updated_at=excluded.updated_at
            """,
            [(k, v, cat, now) for k, (v, cat) in facts.items()],
        )
        conn.commit()
