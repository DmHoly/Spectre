"""Les tables du plugin links : liens entre µprojets et entre entités physiques."""

from __future__ import annotations

from ...kernel.plugin import Migration

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

-- One physical entity is identified by (microproject, experience, index into that experience's
-- current physical_tracking list) - the same addressing the atlas already uses for its entity
-- nodes (entity:{experience_id}:{index}). Not a foreign key: the referenced experience lives in
-- a Follow repository, not this database, so nothing here can enforce it still exists - a link to
-- a since-deleted microproject or a physical_tracking entry that got reordered/removed by a later edit
-- is a stale row the atlas just quietly stops resolving, same as it already does for entities.
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

# Sur une base d'avant le renommage project -> microproject, ces tables viennent d'être renommées
# par la première migration du plugin microprojects : ``CREATE ... IF NOT EXISTS`` ne fait rien.
MIGRATIONS = (Migration("0001_initial", SCHEMA),)
