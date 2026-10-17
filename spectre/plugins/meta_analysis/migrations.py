"""Les tables du plugin meta_analysis : les analyses de plaques et les plaques de chacune."""

from __future__ import annotations

from ...kernel.plugin import Migration

SCHEMA = """
-- Une analyse de plaques (spectre.plugins.meta_analysis.service) : une question posée à quelques plaques,
-- d'une étude ou d'une autre, et ce qu'on en a conclu. Ce que chaque plaque a appris va dans ses notes
-- (wafer_notes, plugin wafers) : il la suit partout ; ici, seulement la conclusion de l'analyse.
CREATE TABLE IF NOT EXISTS wafer_analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    question TEXT NOT NULL DEFAULT '',
    conclusion TEXT NOT NULL DEFAULT '',
    created_by TEXT NOT NULL,
    created_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    updated_by TEXT NOT NULL,
    updated_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    updated_at TEXT NOT NULL
);

-- Les plaques d'une analyse, dans l'ordre de la page : la première (position 0) est la référence, à
-- laquelle les autres se comparent. ``lasermark`` : tel qu'écrit à l'ajout ; ``wafer_key`` : la clé de
-- la plaque (wafers.service.wafer_key), pour retrouver les analyses d'une plaque.
CREATE TABLE IF NOT EXISTS wafer_analysis_wafers (
    analysis_id INTEGER NOT NULL REFERENCES wafer_analyses(id) ON DELETE CASCADE,
    wafer_key TEXT NOT NULL,
    lasermark TEXT NOT NULL,
    position INTEGER NOT NULL,
    PRIMARY KEY (analysis_id, wafer_key)
);

CREATE INDEX IF NOT EXISTS idx_wafer_analysis_wafers_key ON wafer_analysis_wafers(wafer_key);
"""

# Les KPI que l'analyse compare (JSON : [{hook, column, label, filters, better}], '[]' sans KPI) - une colonne d'un
# type de données PRISM par plaque, comme les KPI suivis d'un projet (plugin kpi_tracking) ; ``better`` (high, low
# ou null) dit quel sens d'écart à la référence est un progrès. Les valeurs se recalculent à chaque lecture.
KPIS = "ALTER TABLE wafer_analyses ADD COLUMN kpis TEXT NOT NULL DEFAULT '[]';"

MIGRATIONS = (Migration("0001_initial", SCHEMA), Migration("0002_kpis", KPIS))
