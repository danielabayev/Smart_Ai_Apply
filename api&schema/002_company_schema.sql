-- ============================================================
-- Migration: Company Schema
-- פלטפורמת התאמת קו"ח אוטומטית למשרות
-- PostgreSQL
--
-- הערה: קובץ זה תלוי ב-migration_user_schema.sql שכבר רץ קודם -
-- הוא משתמש מחדש ב-work_arrangement_type שהוגדר שם (אותו DB,
-- 2 סכמות לוגיות).
--
-- companies ו-jobs משתמשים במספור עוקב (BIGINT, לא UUID) כדי
-- לאפשר ל-Agent 4 לסרוק משרות לפי סמן (cursor) פשוט למשתמש,
-- במקום לשמור רשומת match לכל בדיקה.
-- ============================================================

-- ============================================================
-- ENUM Types
-- ============================================================

CREATE TYPE company_status AS ENUM ('active', 'flagged_for_review');
CREATE TYPE employment_type_type AS ENUM ('full_time', 'part_time', 'contract');

-- ============================================================
-- Table: companies
-- ============================================================

CREATE TABLE companies (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    website VARCHAR(512) NOT NULL,
    status company_status NOT NULL DEFAULT 'active',
    last_checked_at TIMESTAMP,
    last_job_found_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now()
);

-- ============================================================
-- Table: jobs
-- ============================================================

CREATE TABLE jobs (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_id BIGINT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    requirements TEXT[] NOT NULL DEFAULT '{}',
    source_url VARCHAR(1024) NOT NULL,
    salary_min NUMERIC(12,2),
    salary_max NUMERIC(12,2),
    salary_currency VARCHAR(3),
    employment_type employment_type_type,
    work_arrangement work_arrangement_type, -- shared type from User Schema
    location VARCHAR(255),
    discovered_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE INDEX idx_jobs_company_id ON jobs(company_id);

-- ============================================================
-- Table: user_job_scan_cursor
-- שורה אחת לכל משתמש: מאיפה Agent 4 ממשיך לסרוק משרות בפעם
-- הבאה. מחליף טבלת matches - בלי לשמור רשומה לכל בדיקה.
--
-- last_checked_job_id מתאפס ל-0 ע"י User Server כשה-
-- user_preferences או building_blocks של המשתמש משתנים,
-- כדי לבדוק מחדש מהתחלה (לוגיקת אפליקציה, לא DB trigger -
-- כי זה חוצה שירותים).
-- ============================================================

CREATE TABLE user_job_scan_cursor (
    user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE, -- אותו DB פיזי, FK תקין
    last_checked_job_id BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMP NOT NULL DEFAULT now()
);

-- ============================================================
-- Trigger: עדכון אוטומטי של updated_at
-- (משתמש בפונקציה set_updated_at() שהוגדרה ב-migration_user_schema.sql)
-- ============================================================

CREATE TRIGGER trg_companies_updated_at
    BEFORE UPDATE ON companies
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_jobs_updated_at
    BEFORE UPDATE ON jobs
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_user_job_scan_cursor_updated_at
    BEFORE UPDATE ON user_job_scan_cursor
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
