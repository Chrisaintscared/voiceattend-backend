"""
VoiceAttend AI - PostgreSQL Database Layer (FIXED FOR DEPLOYMENT)
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timezone

# 🔥 USE ENVIRONMENT VARIABLE (Render + Supabase)
DATABASE_URL = os.getenv("DATABASE_URL")


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
                        timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    );
                """)

        print("[DB] Connected to cloud database")
    finally:
        conn.close()
