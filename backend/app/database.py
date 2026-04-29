import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def get_connection():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    """Initializes the database tables if they do not exist."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        # Table for Users
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT DEFAULT 'student'
            );
        """)
        # Table for Voice Profiles
        cur.execute("""
            CREATE TABLE IF NOT EXISTS voice_profiles (
                user_id INTEGER PRIMARY KEY REFERENCES users(id),
                embedding FLOAT8[] NOT NULL
            );
        """)
        # Table for Attendance Logs
        cur.execute("""
            CREATE TABLE IF NOT EXISTS attendance_logs (
                id SERIAL PRIMARY KEY,
                user_name TEXT NOT NULL,
                class_id INTEGER,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
    finally:
        conn.close()

def create_user(name, email, hashed_password, role="student"):
    """Creates a new user in the database."""
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            "INSERT INTO users (name, email, password, role) VALUES (%s, %s, %s, %s) RETURNING id, name, email, role",
            (name, email, hashed_password, role)
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

def get_voice_profile(user_id):
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT embedding FROM voice_profiles WHERE user_id = %s", (user_id,))
        return cur.fetchone()
    finally:
        conn.close()

def save_attendance(user_id, user_name, class_id=None):
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            "INSERT INTO attendance_logs (user_name, class_id) VALUES (%s, %s) RETURNING *",
            (user_name, class_id)
        )
        conn.commit()
        return cur.fetchone()
    finally:
        conn.close()
