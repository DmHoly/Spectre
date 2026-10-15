"""Les tables du plugin wafers : l'index des plaques se lit dans les études elles-mêmes ; ici, les
plaques des FDL saisies à la main (:mod:`.fdl_source`, la base locale), la vie de chaque plaque en
ligne telle qu'elle a été lue en dernier (:mod:`.tracking`) et les fiches de plaque - les plaques
enregistrées pour elles-mêmes, avant toute étude (:mod:`.records`)."""

from __future__ import annotations

from ...kernel.plugin import Migration

SCHEMA = """
-- Les plaques d'une FDL (spectre.plugins.wafers.fdl_source.LocalSource), collées à la main en
-- attendant la base de la ligne (PRISM) : une ligne par plaque, dans l'ordre du lot.
CREATE TABLE IF NOT EXISTS fdl_wafers (
    fdl TEXT NOT NULL,
    position INTEGER NOT NULL,
    lasermark TEXT NOT NULL,
    author TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL,
    PRIMARY KEY (fdl, position)
);
"""

TRACKING = """
-- La vie d'une plaque en ligne (spectre.plugins.wafers.tracking) : la fiche assemblée (JSON), lue
-- par la source dite (prism, demo) à fetched_at, le dernier mouvement connu de la plaque
-- ('YYYY-MM-DD HH:MM', toutes sources confondues : c'est lui qui arrête la relecture automatique)
-- et la dernière erreur de relecture quand la fiche gardée est plus vieille que prévu.
CREATE TABLE IF NOT EXISTS wafer_tracking (
    wafer_key TEXT PRIMARY KEY,
    lasermark TEXT NOT NULL,
    source TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    last_movement TEXT,
    payload TEXT NOT NULL,
    error TEXT
);
"""

RECORDS = """
-- Les fiches de plaque (spectre.plugins.wafers.records) : une plaque enregistrée dans Spectre pour
-- elle-même, trouvée dans les bases de la ligne (source 'prism', 'demo') ou créée sans elles
-- ('manual'), avec ce que la base en disait le jour de la fiche (summary, JSON : lot, produit,
-- dernière étape...) - de quoi la retrouver, lui rattacher une étude plus tard, lire ses données.
CREATE TABLE IF NOT EXISTS wafer_records (
    wafer_key TEXT PRIMARY KEY,
    lasermark TEXT NOT NULL,
    source TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '{}',
    created_by TEXT NOT NULL,
    created_by_id INTEGER,
    created_at TEXT NOT NULL
);
"""

MIGRATIONS = (
    Migration("0001_fdl_wafers", SCHEMA),
    Migration("0002_wafer_tracking", TRACKING),
    Migration("0003_wafer_records", RECORDS),
)
