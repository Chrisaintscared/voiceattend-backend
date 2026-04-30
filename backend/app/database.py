from __future__ import annotations

import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")


def get_connection():
    return psycopg2.connect(DATABASE_URL)


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


# ── User helpers ──────────────────────────────────────────────────────────────

def create_user(name: str, email: str, password_hash: str, role: str = "student"):
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            "INSERT INTO users (name, email, password_hash, role) VALUES (%s, %s, %s, %s) RETURNING *",
            (name, email, password_hash, role),
        )
        user = cur.fetchone()
        conn.commit()
        return user
    finally:
        conn.close()


def get_user_by_email(email: str):
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM users WHERE email = %s", (email,))
        return cur.fetchone()
    finally:
        conn.close()


def get_user_by_id(user_id: int):
    """Returns user without password_hash (safe for API responses)."""
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            "SELECT id, name, email, role FROM users WHERE id = %s", (user_id,)
        )
        return cur.fetchone()
    finally:
        conn.close()


def get_user_by_id_internal(user_id: int):
    """Returns full user row including password_hash (for internal auth checks)."""
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        return cur.fetchone()
    finally:
        conn.close()


def update_user_password(user_id: int, password_hash: str):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE users SET password_hash = %s WHERE id = %s",
            (password_hash, user_id),
        )
        conn.commit()
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


def delete_user(user_id: int) -> bool:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
        success = cur.rowcount > 0
        conn.commit()
        return success
    finally:
        conn.close()


# ── Voice profile helpers ─────────────────────────────────────────────────────

def get_all_voice_profiles():
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT user_id, embedding FROM voice_profiles")
        return cur.fetchall()
    finally:
        conn.close()


def get_voice_profile(user_id: int):
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM voice_profiles WHERE user_id = %s", (user_id,))
        return cur.fetchone()
    finally:
        conn.close()


def save_voice_profile(user_id: int, embedding: list[float]):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO voice_profiles (user_id, embedding)
            VALUES (%s, %s)
            ON CONFLICT (user_id) DO UPDATE SET embedding = EXCLUDED.embedding
            """,
            (user_id, embedding),
        )
        conn.commit()
    finally:
        conn.close()


# ── Class helpers ─────────────────────────────────────────────────────────────

def create_class(name: str, code: str, teacher_id: int):
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            "INSERT INTO classes (name, code, teacher_id) VALUES (%s, %s, %s) RETURNING *",
            (name, code, teacher_id),
        )
        row = cur.fetchone()
        conn.commit()
        return row
    finally:
        conn.close()


def get_class_by_code(code: str):
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM classes WHERE code = %s", (code,))
        return cur.fetchone()
    finally:
        conn.close()


def get_class_by_id(class_id: int):
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM classes WHERE id = %s", (class_id,))
        return cur.fetchone()
    finally:
        conn.close()


def get_classes_for_teacher(teacher_id: int):
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            "SELECT * FROM classes WHERE teacher_id = %s ORDER BY created_at DESC",
            (teacher_id,),
        )
        return cur.fetchall()
    finally:
        conn.close()


def get_classes_for_student(student_id: int):
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            """
            SELECT c.* FROM classes c
            JOIN class_members cm ON c.id = cm.class_id
            WHERE cm.student_id = %s
            ORDER BY c.created_at DESC
            """,
            (student_id,),
        )
        return cur.fetchall()
    finally:
        conn.close()


def delete_class(class_id: int) -> bool:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM classes WHERE id = %s", (class_id,))
        success = cur.rowcount > 0
        conn.commit()
        return success
    finally:
        conn.close()


# ── Enrollment helpers ────────────────────────────────────────────────────────

def enroll_student(class_id: int, student_id: int):
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            """
            INSERT INTO class_members (class_id, student_id)
            VALUES (%s, %s)
            ON CONFLICT DO NOTHING
            RETURNING *
            """,
            (class_id, student_id),
        )
        row = cur.fetchone()
        conn.commit()
        return row
    finally:
        conn.close()


def is_enrolled(class_id: int, user_id: int) -> bool:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM class_members WHERE class_id = %s AND student_id = %s",
            (class_id, user_id),
        )
        return cur.fetchone() is not None
    finally:
        conn.close()


def get_enrolled_students(class_id: int):
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            """
            SELECT u.id, u.name, u.email FROM users u
            JOIN class_members cm ON u.id = cm.student_id
            WHERE cm.class_id = %s
            ORDER BY u.name
            """,
            (class_id,),
        )
        return cur.fetchall()
    finally:
        conn.close()


# ── Attendance helpers ────────────────────────────────────────────────────────

def save_attendance(user_id: int, user_name: str, class_id: int):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO attendance_logs (user_id, user_name, class_id) VALUES (%s, %s, %s)",
            (user_id, user_name, class_id),
        )
        conn.commit()
    finally:
        conn.close()


def has_attendance_today(class_id: int, user_id: int) -> bool:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT 1 FROM attendance_logs
            WHERE user_id = %s AND class_id = %s
              AND timestamp::date = CURRENT_DATE
            """,
            (user_id, class_id),
        )
        return cur.fetchone() is not None
    finally:
        conn.close()


def get_attendance_logs(user_id: int, class_id: int | None = None):
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        if class_id:
            cur.execute(
                """
                SELECT l.id, l.user_name, l.timestamp, c.name AS class_name
                FROM attendance_logs l
                JOIN classes c ON l.class_id = c.id
                WHERE l.user_id = %s AND l.class_id = %s
                ORDER BY l.timestamp DESC
                """,
                (user_id, class_id),
            )
        else:
            cur.execute(
                """
                SELECT l.id, l.user_name, l.timestamp, c.name AS class_name
                FROM attendance_logs l
                JOIN classes c ON l.class_id = c.id
                WHERE l.user_id = %s
                ORDER BY l.timestamp DESC
                """,
                (user_id,),
            )
        return cur.fetchall()
    finally:
        conn.close()


def get_all_logs():
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            """
            SELECT l.id, l.user_name, l.timestamp, c.name AS class_name
            FROM attendance_logs l
            JOIN classes c ON l.class_id = c.id
            ORDER BY l.timestamp DESC
            """
        )
        return cur.fetchall()
    finally:
        conn.close()
