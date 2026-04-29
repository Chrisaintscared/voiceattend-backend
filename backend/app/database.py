"""
VoiceAttend AI - PostgreSQL Database Layer
Render + Supabase Production Ready

Changes from v1:
  - voice_profiles.embedding column migrated TEXT → JSONB
  - save_voice_profile() accepts List[float] directly (no json.dumps in caller)
  - get_voice_profile() returns embedding as List[float], never a raw string
  - get_user_embedding() helper for one-shot embedding retrieval
  - Backward-compat: TEXT embeddings stored before the migration are
    auto-converted via json.loads() on read
  - Embedding validation (shape, dtype) on both write and read paths
  - Additional performance indexes
  - All connections closed via try/finally (no connection leaks)
"""

import json
import logging
import os

import psycopg2
from psycopg2.extras import Json, RealDictCursor

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")

# Minimum sensible embedding dimension.
# ECAPA-TDNN produces 192-dim vectors; we accept anything ≥ 64 to allow
# other models without forcing a code change.
MIN_EMBEDDING_DIM = 64


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

def get_connection():
    """
    Open and return a psycopg2 connection.

    SSL is enforced for Supabase / Render Postgres.
    Every caller is responsible for closing the connection (try/finally).
    """
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL environment variable is not set. "
            "Add it to your Render environment or .env file."
        )

    url = DATABASE_URL
    if "sslmode" not in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}sslmode=require"

    try:
        return psycopg2.connect(url)
    except Exception as exc:
        logger.error("DB connection failed: %s", exc)
        raise


# ---------------------------------------------------------------------------
# Schema init
# ---------------------------------------------------------------------------

def init_db() -> None:
    """
    Create all tables, indexes, and run safe ALTER migrations.
    Idempotent — safe to call on every startup.
    """
    logger.info("Initializing database schema …")
    conn = None
    try:
        conn = get_connection()
        cur  = conn.cursor()

        # ── users ────────────────────────────────────────────────────────────
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id            SERIAL PRIMARY KEY,
                name          TEXT    NOT NULL,
                email         TEXT    UNIQUE NOT NULL,
                password_hash TEXT    NOT NULL,
                role          TEXT    DEFAULT 'user'
            );
        """)

        # ── voice_profiles (JSONB embedding) ─────────────────────────────────
        # New deployments: embedding is JSONB from the start.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS voice_profiles (
                id        SERIAL  PRIMARY KEY,
                user_id   INTEGER UNIQUE REFERENCES users(id) ON DELETE CASCADE,
                embedding JSONB   NOT NULL
            );
        """)

        # Migration guard: if the column was created as TEXT in a previous
        # deployment, convert it to JSONB in-place.  The USING cast works
        # because every TEXT value is already valid JSON (we stored it with
        # json.dumps).  If the column is already JSONB this is a no-op.
        cur.execute("""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM   information_schema.columns
                    WHERE  table_name  = 'voice_profiles'
                    AND    column_name = 'embedding'
                    AND    data_type   = 'text'
                ) THEN
                    ALTER TABLE voice_profiles
                        ALTER COLUMN embedding
                        TYPE JSONB
                        USING embedding::jsonb;
                    RAISE NOTICE 'Migrated voice_profiles.embedding TEXT → JSONB';
                END IF;
            END
            $$;
        """)

        # ── attendance_logs ───────────────────────────────────────────────────
        cur.execute("""
            CREATE TABLE IF NOT EXISTS attendance_logs (
                id        SERIAL       PRIMARY KEY,
                user_name TEXT         NOT NULL,
                timestamp TIMESTAMPTZ  DEFAULT NOW()
            );
        """)

        cur.execute("""
            ALTER TABLE attendance_logs
            ADD COLUMN IF NOT EXISTS class_id INTEGER REFERENCES classes(id)
            ON DELETE SET NULL;
        """)  # safe no-op if column already exists

        # ── classes ───────────────────────────────────────────────────────────
        cur.execute("""
            CREATE TABLE IF NOT EXISTS classes (
                id         SERIAL       PRIMARY KEY,
                name       TEXT         NOT NULL,
                code       TEXT         UNIQUE NOT NULL,
                teacher_id INTEGER      REFERENCES users(id) ON DELETE CASCADE,
                created_at TIMESTAMPTZ  DEFAULT NOW()
            );
        """)

        # ── class_members ─────────────────────────────────────────────────────
        cur.execute("""
            CREATE TABLE IF NOT EXISTS class_members (
                id         SERIAL       PRIMARY KEY,
                class_id   INTEGER      REFERENCES classes(id)  ON DELETE CASCADE,
                student_id INTEGER      REFERENCES users(id)    ON DELETE CASCADE,
                joined_at  TIMESTAMPTZ  DEFAULT NOW(),
                UNIQUE (class_id, student_id)
            );
        """)

        # ── indexes ───────────────────────────────────────────────────────────
        for ddl in [
            # attendance
            "CREATE INDEX IF NOT EXISTS idx_attendance_timestamp ON attendance_logs(timestamp);",
            "CREATE INDEX IF NOT EXISTS idx_attendance_class     ON attendance_logs(class_id);",
            "CREATE INDEX IF NOT EXISTS idx_attendance_user      ON attendance_logs(user_name);",
            # voice profiles — primary lookup path
            "CREATE INDEX IF NOT EXISTS idx_voice_user_id        ON voice_profiles(user_id);",
            # class members
            "CREATE INDEX IF NOT EXISTS idx_class_members_class  ON class_members(class_id);",
        ]:
            cur.execute(ddl)

        conn.commit()
        logger.info("✅ DB initialized")
        print("✅ DB initialized")

    except Exception as exc:
        logger.error("❌ DATABASE INIT ERROR: %s", exc)
        print(f"❌ DATABASE INIT ERROR: {exc}")
        raise
    finally:
        if conn:
            conn.close()


# ---------------------------------------------------------------------------
# Embedding helpers (private)
# ---------------------------------------------------------------------------

def _validate_embedding(embedding: list, *, context: str = "") -> None:
    """
    Raise ValueError if the embedding is not a non-empty list of floats
    with at least MIN_EMBEDDING_DIM dimensions.

    Parameters
    ----------
    embedding : list
        The embedding to validate.
    context : str
        Optional label used in error messages (e.g. "user_id=42").
    """
    tag = f" [{context}]" if context else ""

    if not isinstance(embedding, list):
        raise ValueError(f"Embedding{tag} must be a list, got {type(embedding).__name__}.")

    if len(embedding) < MIN_EMBEDDING_DIM:
        raise ValueError(
            f"Embedding{tag} has only {len(embedding)} dimensions "
            f"(minimum {MIN_EMBEDDING_DIM}). The data may be corrupt."
        )

    if not all(isinstance(v, (int, float)) for v in embedding):
        raise ValueError(f"Embedding{tag} contains non-numeric values.")


def _parse_embedding(raw) -> list[float]:
    """
    Return a List[float] from whatever the DB column returns.

    Handles two cases:
      1. JSONB column  → psycopg2 already deserialised it to a Python list.
      2. Legacy TEXT   → still a string; we json.loads() it ourselves.

    Raises ValueError if the result is not a valid embedding.
    """
    if isinstance(raw, str):
        # Backward-compat: pre-migration TEXT value
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Stored embedding is not valid JSON: {exc}") from exc

    if not isinstance(raw, list):
        raise ValueError(f"Parsed embedding is not a list (got {type(raw).__name__}).")

    return [float(v) for v in raw]


# ---------------------------------------------------------------------------
# User functions
# ---------------------------------------------------------------------------

def get_user_by_email(email: str):
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            "SELECT id, name, email, password_hash, role FROM users WHERE email = %s",
            (email,),
        )
        return cur.fetchone()
    finally:
        conn.close()


def create_user(name: str, email: str, password_hash: str, role: str = "user"):
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            """
            INSERT INTO users (name, email, password_hash, role)
            VALUES (%s, %s, %s, %s)
            RETURNING id, name, email, role;
            """,
            (name, email, password_hash, role),
        )
        conn.commit()
        return cur.fetchone()
    finally:
        conn.close()


def get_user_by_id(user_id: int):
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            "SELECT id, name, email, role FROM users WHERE id = %s",
            (user_id,),
        )
        return cur.fetchone()
    finally:
        conn.close()


def get_user_by_id_internal(user_id: int):
    """Returns full row including password_hash — for auth use only."""
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            "SELECT id, name, email, password_hash, role FROM users WHERE id = %s",
            (user_id,),
        )
        return cur.fetchone()
    finally:
        conn.close()


def list_all_users():
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT id, name, email, role FROM users ORDER BY id DESC")
        return cur.fetchall()
    finally:
        conn.close()


def delete_user(user_id: int):
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            "DELETE FROM users WHERE id = %s RETURNING id, name, email, role;",
            (user_id,),
        )
        conn.commit()
        return cur.fetchone()
    finally:
        conn.close()


def update_user_password(user_id: int, new_hash: str):
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            """
            UPDATE users SET password_hash = %s
            WHERE id = %s
            RETURNING id, name, email, role;
            """,
            (new_hash, user_id),
        )
        conn.commit()
        return cur.fetchone()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Voice profile functions
# ---------------------------------------------------------------------------

def save_voice_profile(user_id: int, embedding: list[float]):
    """
    Persist a speaker embedding for *user_id*.

    Parameters
    ----------
    user_id : int
    embedding : List[float]
        L2-normalised embedding from voice_service.extract_voice_embedding().
        Callers must NOT call json.dumps() — this function handles
        serialisation via psycopg2.extras.Json.

    Returns
    -------
    dict  Row from voice_profiles (id, user_id, embedding as list).

    Raises
    ------
    ValueError  If the embedding fails shape / dtype validation.
    """
    _validate_embedding(embedding, context=f"user_id={user_id}")

    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            """
            INSERT INTO voice_profiles (user_id, embedding)
            VALUES (%s, %s)
            ON CONFLICT (user_id)
            DO UPDATE SET embedding = EXCLUDED.embedding
            RETURNING id, user_id, embedding;
            """,
            (user_id, Json(embedding)),   # Json() → proper JSONB binding
        )
        conn.commit()
        row = cur.fetchone()

        # Return embedding as list, not the raw DB value
        if row:
            row = dict(row)
            row["embedding"] = _parse_embedding(row["embedding"])
        return row
    finally:
        conn.close()


def get_voice_profile(user_id: int) -> dict | None:
    """
    Retrieve the voice profile for *user_id*.

    Returns
    -------
    dict | None
        ``{"id": …, "user_id": …, "embedding": List[float]}``
        or ``None`` if no profile exists.

    Notes
    -----
    The ``embedding`` field is always returned as ``List[float]``.
    Legacy TEXT-encoded embeddings are transparently converted.
    """
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            "SELECT id, user_id, embedding FROM voice_profiles WHERE user_id = %s",
            (user_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None

        row = dict(row)
        try:
            embedding = _parse_embedding(row["embedding"])
            _validate_embedding(embedding, context=f"user_id={user_id}")
            row["embedding"] = embedding
        except ValueError as exc:
            logger.error(
                "Corrupt embedding in DB for user_id=%s: %s", user_id, exc
            )
            # Surface as None so the caller sees "not enrolled" and prompts
            # the user to re-enroll rather than crashing the request.
            return None

        return row
    finally:
        conn.close()


def get_user_embedding(user_id: int) -> list[float] | None:
    """
    Convenience wrapper — returns only the embedding list (or None).

    Preferred over get_voice_profile() when the caller just needs the
    vector for cosine similarity, e.g. in attendance.py:

        stored_emb = get_user_embedding(user["id"])
        if stored_emb is None:
            raise HTTPException(400, "Voice not enrolled")
    """
    profile = get_voice_profile(user_id)
    if profile is None:
        return None
    return profile["embedding"]


def get_all_voice_profiles() -> list[dict]:
    """Return all profiles with embeddings parsed to List[float]."""
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT id, user_id, embedding FROM voice_profiles")
        rows = cur.fetchall()

        result = []
        for row in rows:
            row = dict(row)
            try:
                embedding = _parse_embedding(row["embedding"])
                _validate_embedding(embedding, context=f"user_id={row['user_id']}")
                row["embedding"] = embedding
                result.append(row)
            except ValueError as exc:
                logger.warning(
                    "Skipping corrupt profile user_id=%s: %s", row["user_id"], exc
                )
        return result
    finally:
        conn.close()


def delete_voice_profile(user_id: int) -> dict | None:
    """Delete a user's voice profile (e.g. admin re-enrollment reset)."""
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            "DELETE FROM voice_profiles WHERE user_id = %s RETURNING id, user_id;",
            (user_id,),
        )
        conn.commit()
        return cur.fetchone()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Attendance
# ---------------------------------------------------------------------------

def save_attendance(user_name: str, class_id: int | None = None) -> dict:
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            """
            INSERT INTO attendance_logs (user_name, class_id)
            VALUES (%s, %s)
            RETURNING *;
            """,
            (user_name, class_id),
        )
        conn.commit()
        return cur.fetchone()
    finally:
        conn.close()


# Alias kept for backward compatibility
log_attendance = save_attendance


def get_all_logs(limit: int = 1000) -> list[dict]:
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            "SELECT * FROM attendance_logs ORDER BY timestamp DESC LIMIT %s",
            (limit,),
        )
        return cur.fetchall()
    finally:
        conn.close()


def get_logs_by_user(user_name: str) -> list[dict]:
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            "SELECT * FROM attendance_logs WHERE user_name = %s ORDER BY timestamp DESC",
            (user_name,),
        )
        return cur.fetchall()
    finally:
        conn.close()


def get_logs_by_class(class_id: int, limit: int = 1000) -> list[dict]:
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            """
            SELECT * FROM attendance_logs
            WHERE class_id = %s
            ORDER BY timestamp DESC
            LIMIT %s
            """,
            (class_id, limit),
        )
        return cur.fetchall()
    finally:
        conn.close()


def get_logs_by_user_and_class(user_name: str, class_id: int) -> list[dict]:
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            """
            SELECT * FROM attendance_logs
            WHERE user_name = %s AND class_id = %s
            ORDER BY timestamp DESC
            """,
            (user_name, class_id),
        )
        return cur.fetchall()
    finally:
        conn.close()
