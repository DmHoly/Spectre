"""Les tables du plugin lumiere : les rapports générés, les modèles de rapport."""

from __future__ import annotations

from ...kernel.plugin import Migration

SCHEMA = """
-- Un rapport demandé par un utilisateur (spectre.plugins.lumiere.service) : son modèle (``template`` : une clé
-- de templates), son contexte (``context_kind`` : wafer... ; ``context_key`` : le lasermark...), son état
-- (queued, running, done, error) et, une fois fait, le fichier HTML sous <data>/lumiere/reports/.
CREATE TABLE IF NOT EXISTS lumiere_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    template TEXT NOT NULL,
    context_kind TEXT NOT NULL,
    context_key TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    message TEXT NOT NULL DEFAULT '',
    file TEXT,
    bytes INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    started_at TEXT,
    finished_at TEXT
);
CREATE INDEX IF NOT EXISTS lumiere_reports_context ON lumiere_reports(context_kind, context_key);
"""

TEMPLATES = """
-- Un modèle de rapport composé dans l'éditeur (spectre.plugins.lumiere.templates) : sa clé (unique, lisible),
-- son nom, le contexte qu'il attend (wafer...), ses slides (JSON : la forme documentée dans templates.py) et
-- son auteur. Les modèles livrés avec Spectre ne sont pas ici (BUILTIN).
CREATE TABLE IF NOT EXISTS lumiere_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    context TEXT NOT NULL,
    slides TEXT NOT NULL,
    owner_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

MIGRATIONS = (Migration("0001_initial", SCHEMA), Migration("0002_templates", TEMPLATES))
