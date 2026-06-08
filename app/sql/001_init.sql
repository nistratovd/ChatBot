CREATE TABLE IF NOT EXISTS questions (
    id BIGSERIAL PRIMARY KEY,
    sort_order INTEGER NOT NULL UNIQUE,
    text TEXT NOT NULL,
    photo_url TEXT,
    photo_file_id TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS answer_options (
    id BIGSERIAL PRIMARY KEY,
    question_id BIGINT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    is_correct BOOLEAN NOT NULL DEFAULT FALSE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (question_id, sort_order)
);

CREATE TABLE IF NOT EXISTS quiz_attempts (
    id BIGSERIAL PRIMARY KEY,
    telegram_user_id BIGINT NOT NULL,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    total_questions INTEGER NOT NULL DEFAULT 0,
    correct_answers INTEGER NOT NULL DEFAULT 0,
    is_all_correct BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS user_answers (
    id BIGSERIAL PRIMARY KEY,
    attempt_id BIGINT NOT NULL REFERENCES quiz_attempts(id) ON DELETE CASCADE,
    telegram_user_id BIGINT NOT NULL,
    question_id BIGINT NOT NULL REFERENCES questions(id) ON DELETE RESTRICT,
    option_id BIGINT NOT NULL REFERENCES answer_options(id) ON DELETE RESTRICT,
    is_correct BOOLEAN NOT NULL,
    answered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (attempt_id, question_id)
);

CREATE TABLE IF NOT EXISTS successful_users (
    telegram_user_id BIGINT PRIMARY KEY,
    attempt_id BIGINT NOT NULL UNIQUE REFERENCES quiz_attempts(id) ON DELETE CASCADE,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    completed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


CREATE TABLE IF NOT EXISTS bot_chat_messages (
    chat_id BIGINT NOT NULL,
    message_id BIGINT NOT NULL,
    telegram_user_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (chat_id, message_id)
);

CREATE TABLE IF NOT EXISTS quiz_allowed_users (
    telegram_user_id BIGINT PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bot_chat_messages_user ON bot_chat_messages (telegram_user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_questions_active_order ON questions (is_active, sort_order);
CREATE INDEX IF NOT EXISTS idx_options_question_order ON answer_options (question_id, sort_order);
CREATE INDEX IF NOT EXISTS idx_attempts_user_completed ON quiz_attempts (telegram_user_id, completed_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS ux_attempts_one_active_per_user ON quiz_attempts (telegram_user_id) WHERE completed_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_answers_user_attempt ON user_answers (telegram_user_id, attempt_id);
