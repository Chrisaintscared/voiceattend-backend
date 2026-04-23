-- ============================================================
-- VoiceAttend AI – PostgreSQL Database Setup
-- ============================================================
-- Run this script ONCE as a PostgreSQL superuser (e.g. postgres):
--
--   Windows (PowerShell):
--       psql -U postgres -f database_setup.sql
--
--   macOS / Linux:
--       sudo -u postgres psql -f database_setup.sql
-- ============================================================


-- 1. Create the application user
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'voiceuser') THEN
        CREATE ROLE voiceuser LOGIN PASSWORD 'voicepass';
    END IF;
END
$$;


-- 2. Create the database owned by the new user
SELECT 'CREATE DATABASE voiceattend OWNER voiceuser'
WHERE NOT EXISTS (
    SELECT FROM pg_database WHERE datname = 'voiceattend'
)\gexec


-- 3. Connect to the new database
\connect voiceattend


-- 4. Grant schema privileges
GRANT ALL PRIVILEGES ON DATABASE voiceattend TO voiceuser;
GRANT ALL ON SCHEMA public TO voiceuser;


-- 5. Create the attendance_logs table
CREATE TABLE IF NOT EXISTS attendance_logs (
    id        SERIAL      PRIMARY KEY,
    user_name TEXT        NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- 6. Transfer ownership to voiceuser
ALTER TABLE attendance_logs OWNER TO voiceuser;


-- 7. Confirmation
SELECT 'VoiceAttend database setup complete.' AS result;
