"""Les tables du plugin wafers : l'index des plaques se lit dans les études elles-mêmes ; ici,
seulement les plaques des FDL saisies à la main (:mod:`.fdl_source`, la base locale)."""

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

MIGRATIONS = (Migration("0001_fdl_wafers", SCHEMA),)
