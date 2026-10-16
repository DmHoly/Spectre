"""Les tables du plugin wafers : l'index des plaques se lit dans les études elles-mêmes ; ici, les
plaques des FDL saisies à la main (:mod:`.fdl_source`, la base locale), la vie de chaque plaque en
ligne telle qu'elle a été lue en dernier (:mod:`.tracking`) et les fiches de plaque - les plaques
enregistrées pour elles-mêmes, avant toute étude (:mod:`.records`) -, les noms successifs d'une
plaque (:mod:`.links`) et la structure attachée à une plaque sans étude (:mod:`.structures`)."""

from __future__ import annotations

import json
import sqlite3

from ...kernel.db import column_names
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



def _line_facts(conn: sqlite3.Connection) -> None:
    """Ce que la vie en ligne dit de la plaque, lisible sans relire la fiche entière : ses FDL
    (``fdls``, JSON, normalisées) et son nom de lot JIRA (``lot_name``) - la page de la plaque, la
    recherche par FDL et les lots détectés les lisent ; recalculés depuis les fiches déjà gardées."""
    columns = column_names(conn, "wafer_tracking")
    if "fdls" not in columns:
        conn.execute("ALTER TABLE wafer_tracking ADD COLUMN fdls TEXT NOT NULL DEFAULT '[]'")
    if "lot_name" not in columns:
        conn.execute("ALTER TABLE wafer_tracking ADD COLUMN lot_name TEXT")
    from .tracking_model import plate_fdls

    for row in conn.execute("SELECT wafer_key, payload FROM wafer_tracking").fetchall():
        try:
            payload = json.loads(row[1])
        except ValueError:
            continue
        conn.execute(
            "UPDATE wafer_tracking SET fdls = ?, lot_name = ? WHERE wafer_key = ?",
            (json.dumps(plate_fdls(payload)), payload.get("lot_name"), row[0]),
        )


def _run_names(conn: sqlite3.Connection) -> None:
    """Les noms de run d'épitaxie de la plaque (``run_names``, JSON, le plus récent - le principal -
    d'abord) : ses noms courants, par lesquels on la cherche ; recalculés des fiches déjà gardées."""
    if "run_names" not in column_names(conn, "wafer_tracking"):
        conn.execute("ALTER TABLE wafer_tracking ADD COLUMN run_names TEXT NOT NULL DEFAULT '[]'")
    from .tracking_model import plate_runs

    for row in conn.execute("SELECT wafer_key, payload FROM wafer_tracking").fetchall():
        try:
            payload = json.loads(row[1])
        except ValueError:
            continue
        conn.execute("UPDATE wafer_tracking SET run_names = ? WHERE wafer_key = ?", (json.dumps(plate_runs(payload.get("epitaxy") or [])), row[0]))


def _fdl_closures(conn: sqlite3.Connection) -> None:
    """Où en est chacune des FDL de la plaque (``fdl_closures``, JSON ``{numéro: {closed, at}}``) :
    la clôture automatique d'un lot la lit sans relire les fiches ; recalculée des fiches déjà gardées."""
    if "fdl_closures" not in column_names(conn, "wafer_tracking"):
        conn.execute("ALTER TABLE wafer_tracking ADD COLUMN fdl_closures TEXT NOT NULL DEFAULT '{}'")
    from .tracking_model import fdl_closures

    for row in conn.execute("SELECT wafer_key, payload FROM wafer_tracking").fetchall():
        try:
            payload = json.loads(row[1])
        except ValueError:
            continue
        conn.execute("UPDATE wafer_tracking SET fdl_closures = ? WHERE wafer_key = ?", (json.dumps(fdl_closures(payload)), row[0]))


LINKS = """
-- Une plaque qui change de nom (spectre.plugins.wafers.links) : d'abord XX, puis YY après un
-- collage. Une ligne par passage d'un nom au suivant, vue dans la MES (source 'mes' : une étape
-- entrée sous un identifiant, sortie sous un autre) ou déclarée à la main ('manual').
CREATE TABLE IF NOT EXISTS wafer_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_key TEXT NOT NULL,
    from_lasermark TEXT NOT NULL,
    to_key TEXT NOT NULL,
    to_lasermark TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('mes', 'manual')),
    note TEXT NOT NULL DEFAULT '',
    happened_at TEXT,
    created_by TEXT NOT NULL,
    created_by_id INTEGER,
    created_at TEXT NOT NULL,
    UNIQUE (from_key, to_key)
);
CREATE INDEX IF NOT EXISTS idx_wafer_links_to ON wafer_links(to_key);
"""

STRUCTURES = """
-- La structure attachée à une plaque elle-même (spectre.plugins.wafers.structures), sans étude ni
-- µprojet : une version de référence ou une structure de la bibliothèque, avec son dessin (SVG)
-- calculé le jour où elle a été attachée. Une plaque n'en a qu'une.
CREATE TABLE IF NOT EXISTS wafer_structures (
    wafer_key TEXT PRIMARY KEY,
    lasermark TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('reference', 'saved')),
    source_id TEXT NOT NULL,
    version TEXT,
    label TEXT NOT NULL,
    svg TEXT,
    note TEXT NOT NULL DEFAULT '',
    attached_by TEXT NOT NULL,
    attached_by_id INTEGER,
    attached_at TEXT NOT NULL
);
"""

NOTES = """
-- Le contexte d'une plaque écrit sur sa page (spectre.plugins.wafers.notes) : pourquoi elle est là,
-- ce qu'on voulait voir, ce qu'on a compris grâce à elle - quand aucune étude ne le dit pour elle.
CREATE TABLE IF NOT EXISTS wafer_notes (
    wafer_key TEXT PRIMARY KEY,
    lasermark TEXT NOT NULL,
    context TEXT,
    hypothesis TEXT,
    learnings TEXT,
    updated_by TEXT NOT NULL,
    updated_by_id INTEGER,
    updated_at TEXT NOT NULL
);
"""

MIGRATIONS = (
    Migration("0001_fdl_wafers", SCHEMA),
    Migration("0002_wafer_tracking", TRACKING),
    Migration("0003_wafer_records", RECORDS),
    Migration("0004_tracking_line_facts", _line_facts),
    Migration("0005_wafer_links", LINKS),
    Migration("0006_wafer_structures", STRUCTURES),
    Migration("0007_tracking_run_names", _run_names),
    Migration("0008_wafer_notes", NOTES),
    Migration("0009_tracking_fdl_closures", _fdl_closures),
)
