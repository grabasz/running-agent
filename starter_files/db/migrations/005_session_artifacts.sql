-- ============================================
-- Migracja 005: session_artifacts
-- Purpose: przechowywanie dlugich markdown-artefaktow z sesji Claude
-- (test diagnostyczny, plan taperingu, recipe, howto, hypothesis)
-- ktore user chce miec dostepne z telefona (dashboard) bez AI musialo
-- czytac ich przy nowej sesji.
-- ============================================

CREATE TABLE IF NOT EXISTS session_artifacts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL DEFAULT 1 REFERENCES users(id),
    date          TEXT NOT NULL,                       -- YYYY-MM-DD utworzenia
    category      TEXT NOT NULL,                       -- diagnostic_test|plan|hypothesis|recipe|howto|other
    title         TEXT NOT NULL,                       -- krotki, w liscie
    summary       TEXT,                                -- 1-2 zdania, widoczne bez rozwijania
    content_md    TEXT NOT NULL,                       -- pelny markdown
    source        TEXT DEFAULT 'chat',                 -- chat|mcp|manual
    archived      INTEGER DEFAULT 0,                   -- 0 aktywne, 1 zarchiwizowane
    created_at    TEXT DEFAULT (datetime('now')),
    updated_at    TEXT
);

CREATE INDEX IF NOT EXISTS idx_artifacts_user_date
    ON session_artifacts(user_id, date DESC);
CREATE INDEX IF NOT EXISTS idx_artifacts_user_category
    ON session_artifacts(user_id, category);
