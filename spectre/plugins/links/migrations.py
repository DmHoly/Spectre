"""Les tables du plugin links : liens entre µprojets et entre entités physiques."""

from __future__ import annotations

import logging
import sqlite3

from ...kernel.db import rebuild_table
from ...kernel.errors import NotFound
from ...kernel.plugin import Migration
from ..experiments import service as experiments
from ..experiments.repository import get_repository

logger = logging.getLogger(__name__)

SCHEMA = """
-- Cross-microproject links (spectre.plugins.links.service) - the one relationship that reaches
-- across two microprojects' otherwise-isolated Follow repositories, so it lives here rather than
-- as a Follow reference (follow.core.models.ReferenceLink is validated to always point within its
-- own repository - see repository.py's own commit-time check) or in Experiment.metadata (which,
-- like physical_tracking, only one side could ever read).
CREATE TABLE IF NOT EXISTS microproject_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    microproject_a_id INTEGER NOT NULL REFERENCES microprojects(id) ON DELETE CASCADE,
    microproject_b_id INTEGER NOT NULL REFERENCES microprojects(id) ON DELETE CASCADE,
    note TEXT NOT NULL DEFAULT '',
    created_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (microproject_a_id <> microproject_b_id)
);

-- One physical entity was identified by (microproject, experience version, index into that
-- version's physical_tracking list) - see 0002 for what replaced it.
CREATE TABLE IF NOT EXISTS entity_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    a_microproject_slug TEXT NOT NULL,
    a_experience_id TEXT NOT NULL,
    a_entity_index INTEGER NOT NULL,
    b_microproject_slug TEXT NOT NULL,
    b_experience_id TEXT NOT NULL,
    b_entity_index INTEGER NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_microproject_links_a ON microproject_links(microproject_a_id);
CREATE INDEX IF NOT EXISTS idx_microproject_links_b ON microproject_links(microproject_b_id);
CREATE INDEX IF NOT EXISTS idx_entity_links_a ON entity_links(a_microproject_slug);
CREATE INDEX IF NOT EXISTS idx_entity_links_b ON entity_links(b_microproject_slug);
"""

# Une entité désigne désormais la piste (le nom de branche Follow) et non une version : un lien
# survit à toute écriture sur l'une des deux études. Le µprojet est référencé par son id, si bien que
# sa suppression purge ses liens (ON DELETE CASCADE). L'index reste une position dans la liste
# physical_tracking de l'étude, vérifiée à la création du lien.
ENTITY_LINKS = """
CREATE TABLE entity_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    a_microproject_id INTEGER NOT NULL REFERENCES microprojects(id) ON DELETE CASCADE,
    a_experiment_id TEXT NOT NULL,
    a_entity_index INTEGER NOT NULL,
    b_microproject_id INTEGER NOT NULL REFERENCES microprojects(id) ON DELETE CASCADE,
    b_experiment_id TEXT NOT NULL,
    b_entity_index INTEGER NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
)
"""

# Les lignes d'avant dont la piste n'a pas pu être retrouvée (µprojet ou version disparus) : gardées
# telles quelles, hors de la table que lit l'application, plutôt que perdues.
UNRESOLVED_ENTITY_LINKS = """
CREATE TABLE IF NOT EXISTS entity_links_unresolved (
    id INTEGER PRIMARY KEY,
    a_microproject_slug TEXT NOT NULL,
    a_experience_id TEXT NOT NULL,
    a_entity_index INTEGER NOT NULL,
    b_microproject_slug TEXT NOT NULL,
    b_experience_id TEXT NOT NULL,
    b_entity_index INTEGER NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_by INTEGER NOT NULL,
    created_at TEXT NOT NULL
)
"""


def _experiment_of(slug: str, experience_id: str) -> str | None:
    """La piste d'une ancienne référence (un id de version, ou déjà un nom de piste), ``None`` si le
    dépôt du µprojet ne la connaît pas ou ne se lit pas."""
    try:
        repo = get_repository(slug)
        if experience_id in repo.branches:
            return experience_id
        return experiments.experiment_of_version(repo, experience_id)
    except NotFound:
        return None
    except Exception:  # un dépôt illisible ne doit pas bloquer le démarrage : la ligne est mise de côté
        logger.exception("dépôt Follow de %r illisible pendant la migration des liens d'entités", slug)
        return None


def _entity_links_by_experiment(conn: sqlite3.Connection) -> None:
    rows = conn.execute("SELECT * FROM entity_links").fetchall()
    ids = {row["slug"]: row["id"] for row in conn.execute("SELECT id, slug FROM microprojects")}
    pistes: dict[tuple[str, str], str | None] = {}

    def piste(slug: str, experience_id: str) -> str | None:
        if slug not in ids:
            return None
        if (slug, experience_id) not in pistes:
            pistes[slug, experience_id] = _experiment_of(slug, experience_id)
        return pistes[slug, experience_id]

    for column in ("a_microproject_id INTEGER", "a_experiment_id TEXT", "b_microproject_id INTEGER", "b_experiment_id TEXT"):
        conn.execute(f"ALTER TABLE entity_links ADD COLUMN {column}")
    unresolved = []
    for row in rows:
        a, b = piste(row["a_microproject_slug"], row["a_experience_id"]), piste(row["b_microproject_slug"], row["b_experience_id"])
        if a is None or b is None:
            unresolved.append(row["id"])
            continue
        conn.execute(
            "UPDATE entity_links SET a_microproject_id = ?, a_experiment_id = ?, b_microproject_id = ?, b_experiment_id = ? WHERE id = ?",
            (ids[row["a_microproject_slug"]], a, ids[row["b_microproject_slug"]], b, row["id"]),
        )
    if unresolved:
        logger.warning("%d lien(s) d'entités sans piste retrouvée, mis de côté dans entity_links_unresolved : %s", len(unresolved), unresolved)
        conn.execute(UNRESOLVED_ENTITY_LINKS)
        marks = ",".join("?" * len(unresolved))
        conn.execute(
            "INSERT INTO entity_links_unresolved SELECT id, a_microproject_slug, a_experience_id, a_entity_index, b_microproject_slug, "
            f"b_experience_id, b_entity_index, note, created_by, created_at FROM entity_links WHERE id IN ({marks})",
            unresolved,
        )
        conn.execute(f"DELETE FROM entity_links WHERE id IN ({marks})", unresolved)

    # les index sur les slugs disparaissent avec leurs colonnes ; les mêmes noms indexent les ids
    conn.execute("DROP INDEX IF EXISTS idx_entity_links_a")
    conn.execute("DROP INDEX IF EXISTS idx_entity_links_b")
    rebuild_table(conn, "entity_links", ENTITY_LINKS)
    conn.execute("CREATE INDEX idx_entity_links_a ON entity_links(a_microproject_id)")
    conn.execute("CREATE INDEX idx_entity_links_b ON entity_links(b_microproject_id)")


# Une paire de µprojets n'est liée qu'une fois, dans un sens ou dans l'autre : les doublons d'avant
# l'index (le service les refusait déjà, sans verrou) ne gardent que le plus ancien.
UNIQUE_MICROPROJECT_PAIR = """
DELETE FROM microproject_links WHERE id NOT IN (
    SELECT MIN(id) FROM microproject_links
    GROUP BY MIN(microproject_a_id, microproject_b_id), MAX(microproject_a_id, microproject_b_id)
);
CREATE UNIQUE INDEX idx_microproject_links_pair
    ON microproject_links(MIN(microproject_a_id, microproject_b_id), MAX(microproject_a_id, microproject_b_id));
"""

# Sur une base d'avant le renommage project -> microproject, ces tables viennent d'être renommées
# par la première migration du plugin microprojects : ``CREATE ... IF NOT EXISTS`` ne fait rien.
MIGRATIONS = (
    Migration("0001_initial", SCHEMA),
    Migration("0002_entity_links_by_experiment", _entity_links_by_experiment),
    Migration("0003_unique_microproject_pair", UNIQUE_MICROPROJECT_PAIR),
)
