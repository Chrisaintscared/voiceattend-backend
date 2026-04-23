-- VoiceAttend AI — Full schema (Auth + Admin + Voice Enrollment)
-- Run: psql -U postgres -f database_setup.sql

-- Create database and user
CREATE DATABASE voiceattend;
CREATE USER voiceattend_user WITH ENCRYPTED PASSWORD 'voiceattend_pass';
GRANT ALL PRIVILEGES ON DATABASE voiceattend TO voiceattend_user;

\connect voiceattend

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ─────────────────────────────────────────────
-- USERS
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name          TEXT NOT NULL,
    email         TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('admin', 'user')),
    created_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ─────────────────────────────────────────────
-- VOICE PROFILES
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS voice_profiles (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    voice_embedding TEXT NOT NULL,          -- JSON-serialised float list
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ─────────────────────────────────────────────
-- ATTENDANCE LOGS
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS attendance_logs (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID REFERENCES users(id) ON DELETE SET NULL,
    timestamp  TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    status     TEXT NOT NULL DEFAULT 'present',
    confidence FLOAT,
    raw_audio  BYTEA                        -- optional: store raw WAV
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_attendance_user    ON attendance_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_attendance_time    ON attendance_logs(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_voice_profiles_user ON voice_profiles(user_id);

-- Seed default admin (password: admin123 — CHANGE IN PRODUCTION)
INSERT INTO users (name, email, password_hash, role)
VALUES (
    'System Admin',
    'admin@voiceattend.local',
    -- bcrypt hash of 'admin123'
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj4gvVc.MQ9O',
    'admin'
) ON CONFLICT (email) DO NOTHING;

GRANT ALL PRIVILEGES ON ALL TABLES    IN SCHEMA public TO voiceattend_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO voiceattend_user;
