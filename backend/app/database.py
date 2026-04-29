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
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT DEFAULT 'student'
            );
            CREATE TABLE IF NOT EXISTS classes (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                code TEXT UNIQUE NOT NULL,
                teacher_id INTEGER REFERENCES users(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS class_members (
                id SERIAL PRIMARY KEY,
                class_id INTEGER REFERENCES classes(id),
                student_id INTEGER REFERENCES users(id),
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS voice_profiles (
                user_id INTEGER PRIMARY KEY REFERENCES users(id),
                embedding FLOAT8[] NOT NULL
            );
            CREATE TABLE IF NOT EXISTS attendance_logs (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id),
                user_name TEXT NOT NULL,
                class_id INTEGER REFERENCES classes(id),
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
    finally:
        conn.close()


def create_user(name, email, hashed_password, role="student"):
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            "INSERT INTO users (name, email, password, role) VALUES (%s, %s, %s, %s) RETURNING id, name, email, role",
            (name, email, hashed_password, role),
        )
        user = cur.fetchone()
        conn.commit()
        return user
    finally:
        conn.close()


def get_user_by_email(email):
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM users WHERE email = %s", (email,))
        return cur.fetchone()
    finally:
        conn.close()


def get_user_by_id(user_id):
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT id, name, email, role FROM users WHERE id = %s", (user_id,))
        return cur.fetchone()
    finally:
        conn.close()


def get_all_voice_profiles():
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT user_id, embedding FROM voice_profiles")
        return cur.fetchall()
    finally:
        conn.close()


def get_voice_profile(user_id):
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            "SELECT embedding FROM voice_profiles WHERE user_id = %s", (user_id,)
        )
        return cur.fetchone()
    finally:
        conn.close()


def save_voice_profile(user_id, embedding):
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            """INSERT INTO voice_profiles (user_id, embedding)
               VALUES (%s, %s)
               ON CONFLICT (user_id) DO UPDATE SET embedding = EXCLUDED.embedding
               RETURNING user_id""",
            (user_id, embedding),
        )
        result = cur.fetchone()
        conn.commit()
        return result
    finally:
        conn.close()


def is_enrolled(class_id, student_id):
    """Returns True if the student is a member of the given class."""
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


def has_attendance_today(class_id, user_id):
    """Returns True if the user already has an attendance log for today in this class."""
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


def save_attendance(user_id, user_name, class_id):
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            """INSERT INTO attendance_logs (user_id, user_name, class_id)
               VALUES (%s, %s, %s) RETURNING *""",
            (user_id, user_name, class_id),
        )
        conn.commit()
        return cur.fetchone()
    finally:
        conn.close()


def get_attendance_logs(user_id=None, class_id=None):
    """Fetch attendance logs, optionally filtered by user and/or class."""
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
