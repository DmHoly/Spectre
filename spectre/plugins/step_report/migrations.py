"""La table du plugin step_report : les commentaires d'étape."""

from __future__ import annotations

from ...kernel.plugin import Migration

SCHEMA = """
-- Le commentaire d'une étape d'un procédé (spectre.plugins.step_report.service). L'étape est désignée par
-- son id (``st_<8 hex>``, stable d'une version de l'étude à la suivante) sous le µprojet qui la porte :
-- l'id seul ne dit pas à qui est l'étude, et un commentaire ne se lit ni ne s'écrit hors de son µprojet.
-- Le procédé n'en sait rien : un commentaire n'entre dans aucune version, ni dans leur comparaison.
CREATE TABLE IF NOT EXISTS step_comments (
    microproject_id INTEGER NOT NULL REFERENCES microprojects(id) ON DELETE CASCADE,
    step_id TEXT NOT NULL,
    text TEXT NOT NULL,
    updated_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (microproject_id, step_id)
);
"""

MIGRATIONS = (Migration("0001_initial", SCHEMA),)
