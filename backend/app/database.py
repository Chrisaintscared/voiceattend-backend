"""
VoiceAttend AI - PostgreSQL Database Layer (FIXED FULL VERSION)
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
        raise Exception("DATABASE_URL not set")

    return psycopg2.connect(DATABASE_URL)


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
                        timestamp TIMESTAMPTZ DEFAULT NOW()
                    );
                """)

        print("[DB] Connected successfully")

    finally:
        conn.close()


# ─────────────────────────────
# USER FUNCTIONS
# ─────────────────────────────

def get_user_by_email(email: str):
    conn = get_connection()
    try:
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM users WHERE email = %s",
                    (email,)
                )
                return cur.fetchone()
    finally:
        conn.close()


def create_user(name: str, email: str, password_hash: str, role: str = "user"):
    conn = get_connection()
    try:
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    INSERT INTO users (name, email, password_hash, role)
                    VALUES (%s, %s, %s, %s)
                    RETURNING *;
                """, (name, email, password_hash, role))

                return cur.fetchone()
    finally:
        conn.close()


def get_user_by_id(user_id: int):
    conn = get_connection()
    try:
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM users WHERE id = %s",
                    (user_id,)
                )
                return cur.fetchone()
    finally:
        conn.close()


# ─────────────────────────────
# VOICE PROFILE FUNCTIONS (FIX ADDED)
# ─────────────────────────────

def save_voice_profile(user_id: int, embedding: str):
    """
    Saves face/voice embedding for a user
    """
    conn = get_connection()
    try:
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    INSERT INTO voice_profiles (user_id, embedding)
                    VALUES (%s, %s)
                    RETURNING *;
                """, (user_id, embedding))

                return cur.fetchone()
    finally:
        conn.close()


def get_voice_profile(user_id: int):
    conn = get_connection()
    try:
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM voice_profiles
                    WHERE user_id = %s
                """, (user_id,))
                return cur.fetchone()
    finally:
        conn.close()


# ─────────────────────────────
# ATTENDANCE
# ─────────────────────────────

def log_attendance(user_name: str):
    conn = get_connection()
    try:
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    INSERT INTO attendance_logs (user_name)
                    VALUES (%s)
                    RETURNING *;
                """, (user_name,))

                return cur.fetchone()
    finally:
        conn.close()
