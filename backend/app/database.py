"""
VoiceAttend AI - PostgreSQL Database Layer (Render + Supabase Production Ready)
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.getenv("DATABASE_URL")


# ─────────────────────────────
# CONNECTION
# ─────────────────────────────
def get_connection():
    if not DATABASE_URL:
        raise Exception("❌ DATABASE_URL not set")

    try:
        url = DATABASE_URL
        if "sslmode" not in url:
            separator = "&" if "?" in url else "?"
            url = url + separator + "sslmode=require"

        return psycopg2.connect(url)
    except Exception as e:
        print("❌ Connection failed:", e)
        raise


# ─────────────────────────────
# INIT DB
# ─────────────────────────────
def init_db():
    print("🚀 Initializing database...")

    conn = None

    try:
        conn = get_connection()
        cur = conn.cursor()

        # USERS TABLE
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'user'
            );
        """)

        # VOICE PROFILES
        cur.execute("""
            CREATE TABLE IF NOT EXISTS voice_profiles (
                id SERIAL PRIMARY KEY,
                user_id INTEGER UNIQUE REFERENCES users(id) ON DELETE CASCADE,
                embedding TEXT NOT NULL
            );
        """)

        # ATTENDANCE LOGS
        cur.execute("""
            CREATE TABLE IF NOT EXISTS attendance_logs (
                id SERIAL PRIMARY KEY,
                user_name TEXT NOT NULL,
                timestamp TIMESTAMPTZ DEFAULT NOW()
            );
        """)

        # INDEX for performance
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_attendance_timestamp
            ON attendance_logs(timestamp);
        """)

        conn.commit()
        print("✅ Database ready")

    except Exception as e:
        print("❌ DATABASE INIT ERROR:", e)
        raise

    finally:
        if conn:
            conn.close()


# ─────────────────────────────
# USER FUNCTIONS
# ─────────────────────────────

def get_user_by_email(email: str):
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT id, name, email, password_hash, role
            FROM users
            WHERE email = %s
        """, (email,))
        return cur.fetchone()
    finally:
        conn.close()


def create_user(name: str, email: str, password_hash: str, role: str = "user"):
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            INSERT INTO users (name, email, password_hash, role)
            VALUES (%s, %s, %s, %s)
            RETURNING id, name, email, role;
        """, (name, email, password_hash, role))
        conn.commit()
        return cur.fetchone()
    finally:
        conn.close()


def get_user_by_id(user_id: int):
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT id, name, email, role
            FROM users
            WHERE id = %s
        """, (user_id,))
        return cur.fetchone()
    finally:
        conn.close()


def list_all_users():
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT id, name, email, role
            FROM users
            ORDER BY id DESC
        """)
        return cur.fetchall()
    finally:
        conn.close()


def delete_user(user_id: int):
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            DELETE FROM users WHERE id = %s
            RETURNING id, name, email, role;
        """, (user_id,))
        conn.commit()
        return cur.fetchone()
    finally:
        conn.close()


# ─────────────────────────────
# VOICE PROFILE FUNCTIONS
# ─────────────────────────────

def save_voice_profile(user_id: int, embedding: str):
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            INSERT INTO voice_profiles (user_id, embedding)
            VALUES (%s, %s)
            ON CONFLICT (user_id)
            DO UPDATE SET embedding = EXCLUDED.embedding
            RETURNING *;
        """, (user_id, embedding))
        conn.commit()
        return cur.fetchone()
    finally:
        conn.close()


def get_voice_profile(user_id: int):
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT * FROM voice_profiles
            WHERE user_id = %s
        """, (user_id,))
        return cur.fetchone()
    finally:
        conn.close()


def get_all_voice_profiles():
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM voice_profiles")
        return cur.fetchall()
    finally:
        conn.close()


# ─────────────────────────────
# ATTENDANCE
# ─────────────────────────────

def save_attendance(user_name: str):
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            INSERT INTO attendance_logs (user_name)
            VALUES (%s)
            RETURNING *;
        """, (user_name,))
        conn.commit()
        return cur.fetchone()
    finally:
        conn.close()


# log_attendance is an alias kept for backwards compatibility
log_attendance = save_attendance


def get_all_logs(limit: int = 1000):
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT * FROM attendance_logs
            ORDER BY timestamp DESC
            LIMIT %s
        """, (limit,))
        return cur.fetchall()
    finally:
        conn.close()


def get_logs_by_user(user_name: str):
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT * FROM attendance_logs
            WHERE user_name = %s
            ORDER BY timestamp DESC
        """, (user_name,))
        return cur.fetchall()
    finally:
        conn.close()
