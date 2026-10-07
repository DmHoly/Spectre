"""Les tables du plugin experiments : les études elles-mêmes vivent dans le dépôt Follow de chaque
µprojet ; ici, seulement les expériences prévisionnelles (:mod:`.plans`), qui n'en sont pas encore,
et les rattachements (:mod:`.attachments`), posés à la main par-dessus la filiation."""

from __future__ import annotations

from ...kernel.plugin import Migration

SCHEMA = """
-- Une expérience prévisionnelle (spectre.plugins.experiments.plans) : prévue depuis l'arbre d'un
-- µprojet - un titre, une intention, la version dont elle part (aucune pour une racine) et soit les
-- plaques de cette version qu'elle reprendra (mode 'same_wafers', liste JSON de lasermarks), soit le
-- nombre de nouvelles plaques qu'on pense lancer (mode 'new_wafers'). Ni structure ni split : elle
-- devient une étude Follow quand on la lance, et la ligne est alors supprimée.
CREATE TABLE IF NOT EXISTS experiment_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    microproject_id INTEGER NOT NULL REFERENCES microprojects(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    intent TEXT NOT NULL DEFAULT '',
    parent_experiment_id TEXT,
    parent_version_id TEXT,
    mode TEXT NOT NULL CHECK (mode IN ('same_wafers', 'new_wafers')),
    wafers TEXT NOT NULL DEFAULT '[]',
    wafer_count INTEGER,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    author TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (mode = 'new_wafers' OR parent_version_id IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_experiment_plans_microproject ON experiment_plans(microproject_id);
"""

ATTACHMENTS = """
-- Un rattachement (spectre.plugins.experiments.attachments) : une étude partie de rien (sa piste,
-- experiment_id) accrochée après coup sous une version d'une autre étude du µprojet. Un lien posé à
-- la main, par-dessus la filiation du dépôt Follow, qui n'est pas réécrite.
CREATE TABLE IF NOT EXISTS experiment_attachments (
    microproject_id INTEGER NOT NULL REFERENCES microprojects(id) ON DELETE CASCADE,
    experiment_id TEXT NOT NULL,
    parent_experiment_id TEXT NOT NULL,
    parent_version_id TEXT NOT NULL,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    author TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    PRIMARY KEY (microproject_id, experiment_id)
);
"""

MIGRATIONS = (Migration("0001_plans", SCHEMA), Migration("0002_attachments", ATTACHMENTS))
