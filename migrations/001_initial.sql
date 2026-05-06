CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE resume (
    id                 SERIAL PRIMARY KEY,
    file_id            TEXT NOT NULL UNIQUE,
    source_uri         TEXT NOT NULL,
    normalizer_version INT NOT NULL DEFAULT 1,
    normalized_at      TIMESTAMPTZ NOT NULL,
    contact_name       TEXT,
    contact_email      TEXT,
    contact_phone      TEXT,
    contact_linkedin   TEXT,
    contact_github     TEXT,
    contact_website    TEXT
);

CREATE TABLE experience (
    id                 SERIAL PRIMARY KEY,
    resume_id          INT NOT NULL REFERENCES resume(id) ON DELETE CASCADE,
    company_raw        TEXT NOT NULL,
    company_canonical  TEXT NOT NULL,
    title              TEXT NOT NULL,
    location_raw       TEXT,
    location_canonical TEXT,
    is_remote          BOOLEAN NOT NULL DEFAULT false,
    start_date_raw     TEXT,
    start_date_iso     TEXT,
    end_date_raw       TEXT,
    end_date_iso       TEXT,
    is_current         BOOLEAN NOT NULL DEFAULT false,
    position           INT NOT NULL
);

CREATE TABLE education (
    id                  SERIAL PRIMARY KEY,
    resume_id           INT NOT NULL REFERENCES resume(id) ON DELETE CASCADE,
    institution         TEXT NOT NULL,
    degree              TEXT,
    field               TEXT,
    gpa                 TEXT,
    graduation_date_raw TEXT,
    graduation_date_iso TEXT,
    is_expected         BOOLEAN NOT NULL DEFAULT false,
    honors              JSONB,
    courses             JSONB,
    position            INT NOT NULL
);

CREATE TABLE project (
    id           SERIAL PRIMARY KEY,
    resume_id    INT NOT NULL REFERENCES resume(id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    technologies JSONB,
    links        JSONB,
    position     INT NOT NULL
);

CREATE TABLE bullet (
    id            SERIAL PRIMARY KEY,
    experience_id INT REFERENCES experience(id) ON DELETE CASCADE,
    project_id    INT REFERENCES project(id) ON DELETE CASCADE,
    text          TEXT NOT NULL,
    embedding     vector(1536),
    position      INT NOT NULL,
    CONSTRAINT bullet_one_parent CHECK (
        (experience_id IS NOT NULL)::int + (project_id IS NOT NULL)::int = 1
    )
);

CREATE TABLE skill (
    id        SERIAL PRIMARY KEY,
    canonical TEXT NOT NULL UNIQUE
);

CREATE TABLE resume_skill (
    id        SERIAL PRIMARY KEY,
    resume_id INT NOT NULL REFERENCES resume(id) ON DELETE CASCADE,
    skill_id  INT NOT NULL REFERENCES skill(id),
    raw       TEXT NOT NULL,
    category  TEXT,
    UNIQUE (resume_id, skill_id)
);

CREATE TABLE other_section (
    id           SERIAL PRIMARY KEY,
    resume_id    INT NOT NULL REFERENCES resume(id) ON DELETE CASCADE,
    section_type TEXT NOT NULL,
    raw_header   TEXT,
    raw_text     TEXT NOT NULL,
    position     INT NOT NULL
);

CREATE INDEX ON experience (resume_id);
CREATE INDEX ON education (resume_id);
CREATE INDEX ON project (resume_id);
CREATE INDEX ON bullet (experience_id);
CREATE INDEX ON bullet (project_id);
CREATE INDEX ON resume_skill (resume_id);
CREATE INDEX ON resume_skill (skill_id);
CREATE INDEX ON other_section (resume_id, section_type);
