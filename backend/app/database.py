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

# --- User & Admin Helpers ---
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
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
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

def get_all_logs():
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
