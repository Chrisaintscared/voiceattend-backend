"""
VoiceAttend AI — app/database.py
==================================
All database helpers. Column name for the hashed password is `password_hash`
throughout to match what auth.py expects.
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")


# ─────────────────────────────────────────────────────────────────────────────
# Connection
# ─────────────────────────────────────────────────────────────────────────────

def get_connection():
    return psycopg2.connect(DATABASE_URL)


# ─────────────────────────────────────────────────────────────────────────────
# Schema
# ─────────────────────────────────────────────────────────────────────────────

def init_db():
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id            SERIAL PRIMARY KEY,
                name          TEXT NOT NULL,
                email         TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role          TEXT DEFAULT 'student'
            );

            CREATE TABLE IF NOT EXISTS classes (
                id         SERIAL PRIMARY KEY,
                name       TEXT NOT NULL,
                code       TEXT UNIQUE NOT NULL,
                teacher_id INTEGER REFERENCES users(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS class_members (
                id         SERIAL PRIMARY KEY,
                class_id   INTEGER REFERENCES classes(id),
                student_id INTEGER REFERENCES users(id),
                joined_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (class_id, student_id)
            );

            CREATE TABLE IF NOT EXISTS voice_profiles (
                user_id   INTEGER PRIMARY KEY REFERENCES users(id),
                embedding FLOAT8[] NOT NULL
            );

            CREATE TABLE IF NOT EXISTS attendance_logs (
                id        SERIAL PRIMARY KEY,
                user_id   INTEGER REFERENCES users(id),
                user_name TEXT NOT NULL,
                class_id  INTEGER REFERENCES classes(id),
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Users
# ─────────────────────────────────────────────────────────────────────────────

def create_user(name: str, email: str, password_hash: str, role: str = "student"):
    """Insert a new user and return the full row (including password_hash)."""
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            """INSERT INTO users (name, email, password_hash, role)
               VALUES (%s, %s, %s, %s)
               RETURNING id, name, email, password_hash, role""",
            (name, email, password_hash, role),
        )
        user = cur.fetchone()
        conn.commit()
        return user
    finally:
        conn.close()


def get_user_by_email(email: str):
    """Return the full user row (including password_hash) or None."""
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM users WHERE email = %s", (email,))
        return cur.fetchone()
    finally:
        conn.close()


def get_user_by_id(user_id: int):
    """Return the full user row (including password_hash) or None."""
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        return cur.fetchone()
    finally:
        conn.close()


# Alias — auth.py imports both names
get_user_by_id_internal = get_user_by_id


def update_user_password(user_id: int, new_password_hash: str):
    """Overwrite the stored password hash for a user."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE users SET password_hash = %s WHERE id = %s",
            (new_password_hash, user_id),
        )
        conn.commit()
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Voice profiles
# ─────────────────────────────────────────────────────────────────────────────

def get_all_voice_profiles():
    """Return every (user_id, embedding) row — used by voice-login."""
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT user_id, embedding FROM voice_profiles")
        return cur.fetchall()
    finally:
        conn.close()


def get_voice_profile(user_id: int):
    """Return the embedding for one user, or None."""
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            "SELECT embedding FROM voice_profiles WHERE user_id = %s", (user_id,)
        )
        return cur.fetchone()
    finally:
        conn.close()


def save_voice_profile(user_id: int, embedding):
    """Upsert a voice embedding for a user."""
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            """INSERT INTO voice_profiles (user_id, embedding)
               VALUES (%s, %s)
               ON CONFLICT (user_id)
               DO UPDATE SET embedding = EXCLUDED.embedding
               RETURNING user_id""",
            (user_id, embedding),
        )
        result = cur.fetchone()
        conn.commit()
        return result
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Enrollment
# ─────────────────────────────────────────────────────────────────────────────

def is_enrolled(class_id: int, student_id: int) -> bool:
    """Return True if the student belongs to the class."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM class_members WHERE class_id = %s AND student_id = %s",
            (class_id, student_id),
        )
        return cur.fetchone() is not None
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Attendance
# ─────────────────────────────────────────────────────────────────────────────

def has_attendance_today(class_id: int, user_id: int) -> bool:
    """Return True if the user already checked in for this class today."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT id FROM attendance_logs
               WHERE class_id = %s
                 AND user_id   = %s
                 AND timestamp::date = CURRENT_DATE""",
            (class_id, user_id),
        )
        return cur.fetchone() is not None
    finally:
        conn.close()


def save_attendance(user_id: int, user_name: str, class_id: int):
    """Insert an attendance log row and return it."""
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            """INSERT INTO attendance_logs (user_id, user_name, class_id)
               VALUES (%s, %s, %s)
               RETURNING *""",
            (user_id, user_name, class_id),
        )
        conn.commit()
        return cur.fetchone()
    finally:
        conn.close()


def get_attendance_logs(user_id=None, class_id=None):
    """Fetch logs filtered by user and/or class, newest first."""
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        query = "SELECT * FROM attendance_logs WHERE 1=1"
        params = []
        if user_id is not None:
            query += " AND user_id = %s"
            params.append(user_id)
        if class_id is not None:
            query += " AND class_id = %s"
            params.append(class_id)
        query += " ORDER BY timestamp DESC"
        cur.execute(query, params)
        return cur.fetchall()
    finally:
        conn.close()
