"""
VoiceAttend AI - PostgreSQL Database Layer (FIXED)
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timezone

DB_CONFIG = {
    "dbname": "voiceattend",
    "user": "voiceuser",
    "password": "voicepass",
    "host": "localhost",
    "port": 5432,
}

def get_connection():
    return psycopg2.connect(**DB_CONFIG)


# ─────────────────────────────
# INIT DB
# ─────────────────────────────
def init_db():
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id SERIAL PRIMARY KEY,
                        name TEXT NOT NULL,
                        email TEXT UNIQUE NOT NULL,
                        password_hash TEXT NOT NULL,
                        role TEXT DEFAULT 'user'
                    );
                """)

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS voice_profiles (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                        embedding TEXT NOT NULL
                    );
                """)

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS attendance_logs (
                        id SERIAL PRIMARY KEY,
                        user_name TEXT NOT NULL,
                        timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    );
                """)

        print("[DB] Ready")
    finally:
        conn.close()


# ─────────────────────────────
# USERS
# ─────────────────────────────
def create_user(name, email, password_hash):
    conn = get_connection()
    try:
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    INSERT INTO users (name, email, password_hash)
                    VALUES (%s, %s, %s)
                    RETURNING id, name, email, role;
                """, (name, email, password_hash))
                return cur.fetchone()
    finally:
        conn.close()


def get_user_by_email(email):
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM users WHERE email=%s", (email,))
            return cur.fetchone()
    finally:
        conn.close()


def get_user_by_id(user_id):
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM users WHERE id=%s", (user_id,))
            return cur.fetchone()
    finally:
        conn.close()


# ─────────────────────────────
# ADMIN FUNCTIONS (FIXED MISSING IMPORTS)
# ─────────────────────────────
def list_all_users():
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT id, name, email, role FROM users ORDER BY id DESC")
            return cur.fetchall()
    finally:
        conn.close()


def delete_user(user_id: str):
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM users WHERE id=%s", (user_id,))
                return cur.rowcount > 0
    finally:
        conn.close()


# ─────────────────────────────
# VOICE PROFILES
# ─────────────────────────────
def save_voice_profile(user_id, embedding):
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO voice_profiles (user_id, embedding)
                    VALUES (%s, %s)
                """, (user_id, str(embedding)))
    finally:
        conn.close()


def get_all_voice_profiles():
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
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
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    INSERT INTO attendance_logs (user_name, timestamp)
                    VALUES (%s, %s)
                    RETURNING id, user_name, timestamp
                """, (user_name, datetime.now(timezone.utc)))
                return cur.fetchone()
    finally:
        conn.close()


def get_all_logs():
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM attendance_logs ORDER BY timestamp DESC")
            return cur.fetchall()
    finally:
        conn.close()


def get_logs_by_user(user_name: str):
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM attendance_logs
                WHERE user_name=%s
                ORDER BY timestamp DESC
            """, (user_name,))
            return cur.fetchall()
    finally:
        conn.close()