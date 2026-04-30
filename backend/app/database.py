"""
VoiceAttend AI — app/database.py
==================================
All database helpers for the VoiceAttend backend. 
Ensures synchronization between Auth, Admin, and Attendance routes.
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
    """Establishes a connection to the PostgreSQL database."""
    return psycopg2.connect(DATABASE_URL)

# ─────────────────────────────────────────────────────────────────────────────
# Schema Initialization
# ─────────────────────────────────────────────────────────────────────────────

def init_db():
    """Initializes the database tables if they do not exist."""
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
                id          SERIAL PRIMARY KEY,
                class_id    INTEGER REFERENCES classes(id),
                student_id  INTEGER REFERENCES users(id),
                joined_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
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
# User Management
# ─────────────────────────────────────────────────────────────────────────────

def create_user(name: str, email: str, password_hash: str, role: str = "student"):
    """Inserts a new user and returns the full row."""
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
    """Returns the user row by email or None."""
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM users WHERE email = %s", (email,))
        return cur.fetchone()
    finally:
        conn.close()

def get_user_by_id(user_id: int):
    """Returns the user row by ID or None."""
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        return cur.fetchone()
    finally:
        conn.close()

# Alias for auth.py compatibility
get_user_by_id_internal = get_user_by_id

def update_user_password(user_id: int, new_password_hash: str):
    """Updates the password hash for a specific user."""
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
# Voice Biometrics
# ─────────────────────────────────────────────────────────────────────────────

def get_all_voice_profiles():
    """Returns all enrolled voice embeddings for comparison."""
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT user_id, embedding FROM voice_profiles")
        return cur.fetchall()
    finally:
        conn.close()

def save_voice_profile(user_id: int, embedding: list[float]):
    """Upserts a voice fingerprint for a user."""
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
# Attendance & Enrollment
# ─────────────────────────────────────────────────────────────────────────────

def is_enrolled(class_id: int, student_id: int) -> bool:
    """Checks if a student is registered in a class."""
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

def save_attendance(user_id: int, user_name: str, class_id: int):
    """Records a successful voice check-in."""
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

def has_attendance_today(class_id: int, user_id: int) -> bool:
    """Prevents duplicate attendance on the same day."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT id FROM attendance_logs
               WHERE class_id = %s AND user_id = %s
               AND timestamp::date = CURRENT_DATE""",
            (class_id, user_id),
        )
        return cur.fetchone() is not None
    finally:
        conn.close()

# ─────────────────────────────────────────────────────────────────────────────
# Admin & Management
# ─────────────────────────────────────────────────────────────────────────────

def list_all_users():
    """Returns user list for Admin Panel (omits sensitive data)."""
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT id, name, email, role FROM users ORDER BY id DESC")
        return cur.fetchall()
    finally:
        conn.close()

def delete_user(user_id: int) -> bool:
    """Deletes a user account and returns success status."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
        success = cur.rowcount > 0
        conn.commit()
        return success
    finally:
        conn.close()

def get_all_logs():
    """Returns a joined view of all logs for the Admin view."""
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT l.id, l.user_name, l.timestamp, c.name AS class_name
            FROM attendance_logs l
            JOIN classes c ON l.class_id = c.id
            ORDER BY l.timestamp DESC
        """)
        return cur.fetchall()
    finally:
        conn.close()
