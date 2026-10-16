"""La table du plugin wafer_data : les blocs de la fiche data, par projet corporate. Les résumés calculés
par plaque ne sont pas ici - ils vivent dans leur propre fichier (:mod:`.store`), hors de la base de Spectre."""

from __future__ import annotations

from ...kernel.plugin import Migration

SCHEMA = """
-- Un bloc de l'onglet « Data » des plaques d'un projet corporate (spectre.plugins.wafer_data.blocks) : une
-- valeur, un histogramme, une cartographie, une courbe (``hook`` : un type de données PRISM par plaque) ou
-- des images (``hook`` vide : des fichiers cherchés d'après un modèle de chemin). ``config`` : un objet JSON,
-- propre au genre de bloc (colonnes, agrégat, filtres...). Le projet ne garde que ce choix - les valeurs se
-- calculent sur chaque plaque et se gardent, résumées, dans le magasin à part du plugin.
CREATE TABLE IF NOT EXISTS area_wafer_sheet_blocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    area_id INTEGER NOT NULL REFERENCES management_areas(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    hook TEXT NOT NULL DEFAULT '',
    config TEXT NOT NULL DEFAULT '{}',
    label TEXT NOT NULL DEFAULT '',
    position INTEGER NOT NULL DEFAULT 0,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_wafer_sheet_blocks_area ON area_wafer_sheet_blocks(area_id, position);
"""

MIGRATIONS = (Migration("0001_initial", SCHEMA),)
