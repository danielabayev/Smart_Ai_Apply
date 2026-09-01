-- ============================================================
-- Migration: User Schema
-- פלטפורמת התאמת קו"ח אוטומטית למשרות
-- PostgreSQL
-- ============================================================

-- דרוש עבור gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ============================================================
-- ENUM Types
-- ============================================================

CREATE TYPE work_arrangement_type AS ENUM ('remote', 'hybrid', 'onsite');
CREATE TYPE conversation_type AS ENUM ('profiling', 'refinement', 'application_edit');
CREATE TYPE conversation_status AS ENUM ('active', 'finished');
CREATE TYPE message_sender AS ENUM ('user', 'agent');
CREATE TYPE building_block_category AS ENUM (
    'project', 'technical_skills', 'education', 'about_user', 'role'
);
CREATE TYPE application_status AS ENUM (
    'pending_tailoring', 'pending_approval', 'approved', 'rejected'
);

-- ============================================================
-- Table: users
-- ============================================================

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    phone_number VARCHAR(50),
    linkedin_url VARCHAR(512),
    github_url VARCHAR(512),
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now()
);

-- ============================================================
-- Table: user_preferences (1:1 with users)
-- ============================================================

CREATE TABLE user_preferences (
    user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    match_threshold SMALLINT NOT NULL DEFAULT 70 CHECK (match_threshold BETWEEN 0 AND 100),
    min_salary NUMERIC(12,2),
    salary_currency VARCHAR(3) DEFAULT 'ILS',
    include_jobs_without_salary BOOLEAN NOT NULL DEFAULT TRUE,
    location VARCHAR(255),
    work_arrangement work_arrangement_type,
    employment_types TEXT[] NOT NULL DEFAULT '{}',
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now()
);

-- ============================================================
-- Table: conversations
-- הערה: building_block_id ו-application_id נשארים ללא FK בשלב זה
-- (תלות מעגלית עם building_blocks / applications) - ה-FK יתווסף
-- בסוף הקובץ, אחרי שהטבלאות האלה נוצרות.
-- ============================================================

CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type conversation_type NOT NULL DEFAULT 'profiling',
    building_block_id UUID,
    application_id UUID,
    status conversation_status NOT NULL DEFAULT 'active',
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE INDEX idx_conversations_user_id ON conversations(user_id);

-- ============================================================
-- Table: messages
-- ============================================================

CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    sender message_sender NOT NULL,
    content TEXT NOT NULL,
    model_used VARCHAR(100),
    response_time_ms INTEGER,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE INDEX idx_messages_conversation_id ON messages(conversation_id);

-- ============================================================
-- Table: building_blocks
-- ============================================================

CREATE TABLE building_blocks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    category building_block_category NOT NULL,
    title VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    variants JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE INDEX idx_building_blocks_user_id ON building_blocks(user_id);
CREATE INDEX idx_building_blocks_conversation_id ON building_blocks(conversation_id);

COMMENT ON COLUMN building_blocks.variants IS
    'Array of {"angle": "<free text>", "content": "<bullet text>"} objects - '
    'the 3 distinct-angle rewrites generated alongside the primary content. '
    'Angle labels are chosen dynamically by the agent, not a fixed enum.';

-- ============================================================
-- Table: applications
-- הערה: job_id הוא הפניה ל-jobs שב-Company Schema (BIGINT,
-- תואם למספור העוקב של jobs.id). ללא FK אמיתי בכוונה - אם
-- המשרה נמחקת (תהליך רקע, למשל אחרי שהמשתמש כבר הגיש בעצמו),
-- ה-application יכול "להתייתם" ולא נמחק יחד איתה.
-- פירוט דרישות/עמידה (מה שבונה את match_score) נשמר בלוגי
-- ריצת Agent 4, לא כאן.
-- ============================================================

CREATE TABLE applications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    job_id BIGINT NOT NULL,
    match_score SMALLINT NOT NULL CHECK (match_score BETWEEN 0 AND 100),
    status application_status NOT NULL DEFAULT 'pending_tailoring',
    document_content TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE INDEX idx_applications_user_id ON applications(user_id);
CREATE INDEX idx_applications_status ON applications(status);
CREATE INDEX idx_applications_job_id ON applications(job_id);

-- ============================================================
-- Table: application_building_blocks (Many-to-Many)
-- אילו building blocks שומשו לבניית הגשה ספציפית
-- ============================================================

CREATE TABLE application_building_blocks (
    application_id UUID NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    building_block_id UUID NOT NULL REFERENCES building_blocks(id) ON DELETE CASCADE,
    PRIMARY KEY (application_id, building_block_id)
);

-- ============================================================
-- סגירת התלות המעגלית: הוספת ה-FK החסרים ל-conversations
-- ============================================================

ALTER TABLE conversations
    ADD CONSTRAINT fk_conversations_building_block
    FOREIGN KEY (building_block_id) REFERENCES building_blocks(id) ON DELETE CASCADE;

ALTER TABLE conversations
    ADD CONSTRAINT fk_conversations_application
    FOREIGN KEY (application_id) REFERENCES applications(id) ON DELETE CASCADE;

-- ============================================================
-- Trigger: עדכון אוטומטי של updated_at בכל טבלה רלוונטית
-- ============================================================

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_user_preferences_updated_at
    BEFORE UPDATE ON user_preferences
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_conversations_updated_at
    BEFORE UPDATE ON conversations
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_building_blocks_updated_at
    BEFORE UPDATE ON building_blocks
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_applications_updated_at
    BEFORE UPDATE ON applications
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
