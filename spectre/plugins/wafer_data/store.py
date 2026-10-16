"""Le magasin des résumés de fiche data : ce qu'un bloc a calculé sur une plaque, gardé pour la relire
d'un coup plutôt que de repasser par PRISM à chaque affichage.

Pourquoi un magasin à part, et pas la base de Spectre ni des fichiers Parquet :

- **hors de** ``spectre.db`` : un fichier SQLite à lui (``<data>/wafer_data/digests.sqlite``, journal WAL).
  La base de Spectre garde ce qui se décide (les blocs d'un projet) ; ici, ce qui se recalcule. On peut
  supprimer ce fichier à tout moment : les fiches se recalculent depuis PRISM, qui fait foi ;
- **une ligne par plaque et par bloc**, écrite et relue à la clé - le geste de la page d'une plaque. Parquet
  est fait pour balayer des colonnes, pas pour remplacer une ligne parmi des millions : il faudrait réécrire
  un fichier entier à chaque plaque, ou en accumuler des milliers de petits ;
- **un résumé, jamais le brut** : une cartographie ramenée à 64 × 64 cases au plus, un histogramme en 30
  classes, une courbe en 60 points, à 4 chiffres significatifs, compressés (zlib) - de quelques centaines
  d'octets à quelques Ko par bloc, là où le cache brut de PRISM pèse jusqu'à 1,4 Mo par plaque (EQE) ;
- **un budget** (``SPECTRE_WAFER_DATA_BUDGET_MB``, 1024 Mo par défaut) : au-delà, les résumés les moins
  récemment lus sont oubliés (ils se recalculeront à la demande). Les **valeurs** des blocs « valeur »
  (une table étroite, ~50 octets par plaque et par bloc) ne sont jamais oubliées : elles situent une
  plaque parmi celles de son projet (rang, distribution) - 500 000 plaques × 10 valeurs ≈ 250 Mo.

Ordre de grandeur : 500 000 plaques × 6 blocs × ~2 Ko ≈ 6 Go de résumés si toutes étaient ouvertes un jour -
d'où le budget, qui garde les plus consultées.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import zlib
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from ...kernel.db import data_dir

BUDGET_ENV = "SPECTRE_WAFER_DATA_BUDGET_MB"
DEFAULT_BUDGET_MB = 1024
CHECK_EVERY = 200  # écritures entre deux vérifications du budget
EVICT_FRACTION = 0.2  # au-delà du budget, on oublie de quoi redescendre à 80 %

SCHEMA = """
CREATE TABLE IF NOT EXISTS digests (
    wafer_key TEXT NOT NULL,
    block_sig TEXT NOT NULL,
    status TEXT NOT NULL,            -- ok | empty | error
    computed_at TEXT NOT NULL,
    accessed_at TEXT NOT NULL,
    size INTEGER NOT NULL,
    payload BLOB NOT NULL,
    PRIMARY KEY (wafer_key, block_sig)
);
CREATE INDEX IF NOT EXISTS idx_digests_sig ON digests(block_sig);
CREATE INDEX IF NOT EXISTS idx_digests_accessed ON digests(accessed_at);

CREATE TABLE IF NOT EXISTS scalars (
    block_sig TEXT NOT NULL,
    wafer_key TEXT NOT NULL,
    value REAL NOT NULL,
    PRIMARY KEY (block_sig, wafer_key)
);
CREATE INDEX IF NOT EXISTS idx_scalars_value ON scalars(block_sig, value);
"""

_lock = threading.Lock()
_ready: set[Path] = set()
_writes = 0


def path() -> Path:
    return data_dir() / "wafer_data" / "digests.sqlite"


def budget_bytes() -> int:
    try:
        megabytes = float(os.environ.get(BUDGET_ENV, DEFAULT_BUDGET_MB))
    except ValueError:
        megabytes = DEFAULT_BUDGET_MB
    return int(max(megabytes, 1) * 1024 * 1024)


@contextmanager
def _conn() -> Iterator[sqlite3.Connection]:
    file = path()
    with _lock:
        if file not in _ready or not file.exists():
            file.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(file) as setup:
                setup.execute("PRAGMA journal_mode=WAL")
                setup.executescript(SCHEMA)
            _ready.add(file)
    conn = sqlite3.connect(file, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA synchronous=NORMAL")
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def encode(payload: Any) -> bytes:
    return zlib.compress(json.dumps(payload, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8"), 6)


def decode(blob: bytes) -> Any:
    return json.loads(zlib.decompress(blob).decode("utf-8"))


def read(wafer_key: str, sigs: list[str]) -> dict[str, dict[str, Any]]:
    """Les résumés gardés de ``wafer_key`` pour ces blocs : ``{sig: {status, computed_at, payload}}`` -
    et leur lecture est notée (le budget oublie d'abord les moins lus)."""
    if not sigs:
        return {}
    marks = ",".join("?" * len(sigs))
    with _conn() as conn:
        rows = conn.execute(
            f"SELECT block_sig, status, computed_at, payload FROM digests WHERE wafer_key = ? AND block_sig IN ({marks})",
            (wafer_key, *sigs),
        ).fetchall()
        if rows:
            conn.execute(f"UPDATE digests SET accessed_at = ? WHERE wafer_key = ? AND block_sig IN ({marks})", (_now(), wafer_key, *sigs))
    found = {}
    for row in rows:
        try:
            found[row["block_sig"]] = {"status": row["status"], "computed_at": row["computed_at"], "payload": decode(row["payload"])}
        except (zlib.error, ValueError):  # un résumé illisible est une absence : il se recalcule
            continue
    return found


def write(wafer_key: str, sig: str, status: str, payload: Any, *, scalar: float | None = None) -> str:
    """Garde le résumé d'un bloc sur une plaque (et sa valeur, pour un bloc « valeur ») ; rend sa date."""
    global _writes
    blob = encode(payload)
    now = _now()
    with _conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO digests (wafer_key, block_sig, status, computed_at, accessed_at, size, payload) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (wafer_key, sig, status, now, now, len(blob), blob),
        )
        if scalar is None:
            conn.execute("DELETE FROM scalars WHERE block_sig = ? AND wafer_key = ?", (sig, wafer_key))
        else:
            conn.execute("INSERT OR REPLACE INTO scalars (block_sig, wafer_key, value) VALUES (?, ?, ?)", (sig, wafer_key, scalar))
    _writes += 1
    if _writes % CHECK_EVERY == 0:
        enforce_budget()
    return now


def forget(sig: str) -> None:
    """Oublie tout ce qu'un bloc a calculé (il a changé, ou disparu)."""
    with _conn() as conn:
        conn.execute("DELETE FROM digests WHERE block_sig = ?", (sig,))
        conn.execute("DELETE FROM scalars WHERE block_sig = ?", (sig,))


def forget_wafer(wafer_key: str) -> None:
    with _conn() as conn:
        conn.execute("DELETE FROM digests WHERE wafer_key = ?", (wafer_key,))


def enforce_budget() -> int:
    """Au-delà du budget, oublie les résumés les moins récemment lus (jamais les valeurs) ; rend combien."""
    limit = budget_bytes()
    with _conn() as conn:
        total = conn.execute("SELECT COALESCE(SUM(size), 0) FROM digests").fetchone()[0]
        if total <= limit:
            return 0
        target = total - int(limit * (1 - EVICT_FRACTION))
        dropped, freed = [], 0
        for row in conn.execute("SELECT wafer_key, block_sig, size FROM digests ORDER BY accessed_at"):
            dropped.append((row["wafer_key"], row["block_sig"]))
            freed += row["size"]
            if freed >= target:
                break
        conn.executemany("DELETE FROM digests WHERE wafer_key = ? AND block_sig = ?", dropped)
    return len(dropped)


def population(sig: str, value: float, *, bins: int = 24) -> dict[str, Any] | None:
    """Où se place ``value`` parmi les valeurs du bloc sur toutes les plaques déjà calculées : ``count``,
    ``below`` / ``equal`` (de quoi un rang), ``minimum``, ``maximum`` et ``bins`` (une distribution en
    ``bins`` classes égales) - ``None`` s'il n'y a qu'elle."""
    with _conn() as conn:
        count, low, high = conn.execute("SELECT COUNT(*), MIN(value), MAX(value) FROM scalars WHERE block_sig = ?", (sig,)).fetchone()
        if count < 2:
            return None
        below = conn.execute("SELECT COUNT(*) FROM scalars WHERE block_sig = ? AND value < ?", (sig, value)).fetchone()[0]
        equal = conn.execute("SELECT COUNT(*) FROM scalars WHERE block_sig = ? AND value = ?", (sig, value)).fetchone()[0]
        counts = [0] * bins
        if high > low:
            width = (high - low) / bins
            for index, n in conn.execute(
                "SELECT MIN(CAST((value - ?) / ? AS INTEGER), ?) AS b, COUNT(*) FROM scalars WHERE block_sig = ? GROUP BY b",
                (low, width, bins - 1, sig),
            ):
                counts[int(index)] = n
        else:
            counts[0] = count
    return {"count": count, "below": below, "equal": equal, "minimum": low, "maximum": high, "bins": counts}


def stats() -> dict[str, Any]:
    """Ce que pèse le magasin : pour la page de configuration (et l'administrateur inquiet)."""
    with _conn() as conn:
        digests, size, wafers = conn.execute("SELECT COUNT(*), COALESCE(SUM(size), 0), COUNT(DISTINCT wafer_key) FROM digests").fetchone()
        scalars = conn.execute("SELECT COUNT(*) FROM scalars").fetchone()[0]
    file = path()
    on_disk = sum(p.stat().st_size for p in file.parent.glob(file.name + "*") if p.is_file())
    return {"digests": digests, "wafers": wafers, "scalars": scalars, "payload_bytes": size, "file_bytes": on_disk, "budget_bytes": budget_bytes()}
