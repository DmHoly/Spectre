"""La base de données vue par un administrateur : la sauvegarder d'un bloc (un ZIP de tout
``data_dir()``) et en explorer les tables SQL pour la nettoyer ou la corriger à la main.

- **Sauvegarde** (:func:`write_backup`) : la base, copiée par l'API de sauvegarde de sqlite3 (une
  copie cohérente d'un fichier ouvert), et tous les fichiers de ``data_dir()`` - dépôts Follow des
  µprojets, pièces jointes, bibliothèques, caches - sauf ``backups/`` (les copies d'avant
  migration). Restaurer, c'est arrêter Spectre et dézipper l'archive à la place de ``data_dir()``.
- **Exploration** (:func:`tables`, :func:`rows`, :func:`update_row`, :func:`delete_row`) : toute
  table SQL, ses lignes désignées par leur ``rowid``, une recherche dans toutes les colonnes. Les
  clés étrangères sont actives : une suppression suit les ``ON DELETE`` du schéma, ou est refusée
  (409 ``integrity_error``). Les colonnes secrètes (mot de passe, sel, jeton, empreinte) sont masquées et
  ne s'écrivent pas ; les tables du noyau (``schema_migrations``, ``plugin_states``) se lisent
  seulement - l'activation des plugins se règle sur sa page. Chaque écriture est journalisée.

Les données que les plugins gardent hors de SQL (les études : dépôts Follow) ne sont pas des
tables : elles se gèrent par leurs propres API.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .db import backups_dir, connect, data_dir, db_path
from .errors import Conflict, InvalidInput, NotFound

logger = logging.getLogger(__name__)

READ_ONLY_TABLES = frozenset({"schema_migrations", "plugin_states"})
_SECRET_COLUMN_RE = re.compile(r"password|token|secret|hash|salt", re.IGNORECASE)
MASK = "••••••"
MAX_LIMIT = 200


# -- sauvegarde ----------------------------------------------------------------------------------


def backup_filename(now: datetime | None = None) -> str:
    return f"spectre-{(now or datetime.now()).strftime('%Y%m%d-%H%M%S')}.zip"


def _data_files(root: Path) -> list[Path]:
    """Les fichiers de ``root`` à archiver : tous, sauf ``backups/`` et la base elle-même (copiée à
    part, avec ses fichiers ``-wal`` / ``-journal``)."""
    database = db_path().name
    skipped_dir = backups_dir().resolve()
    found = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.resolve().is_relative_to(skipped_dir):
            continue
        if path.parent == root and path.name.startswith(database):
            continue
        found.append(path)
    return found


def write_backup(target: Path) -> dict[str, Any]:
    """Écrit dans ``target`` le ZIP de la base et de tous les fichiers de ``data_dir()``, avec un
    ``manifest.json`` (date, nombre de fichiers, taille) ; rend ce manifeste."""
    root = data_dir()
    files = _data_files(root)
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "database": db_path().name,
        "files": len(files) + 1,
        "bytes": 0,
    }
    with tempfile.TemporaryDirectory() as tmp:
        copy_path = Path(tmp) / db_path().name
        source = connect()
        copy = sqlite3.connect(copy_path)
        try:
            source.backup(copy)
        finally:
            copy.close()
            source.close()
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
            archive.write(copy_path, db_path().name)
            manifest["bytes"] += copy_path.stat().st_size
            for path in files:
                try:
                    archive.write(path, path.relative_to(root).as_posix())
                    manifest["bytes"] += path.stat().st_size
                except OSError as exc:  # un fichier retiré ou tenu pendant l'archivage
                    logger.warning("sauvegarde : %s ignoré (%s)", path, exc)
            archive.writestr("manifest.json", json.dumps(manifest, indent=2))
    return manifest


def data_summary() -> dict[str, Any]:
    """Ce que la sauvegarde emportera : la taille de la base, et le nombre et la taille des autres
    fichiers de ``data_dir()``."""
    files = _data_files(data_dir())
    return {
        "data_dir": str(data_dir()),
        "database_bytes": db_path().stat().st_size if db_path().exists() else 0,
        "files": len(files),
        "files_bytes": sum(path.stat().st_size for path in files),
    }


# -- exploration ---------------------------------------------------------------------------------


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _table_names(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
    return [row["name"] for row in rows]


def _has_rowid(conn: sqlite3.Connection, table: str) -> bool:
    try:
        conn.execute(f"SELECT rowid FROM {_quote(table)} LIMIT 0")
        return True
    except sqlite3.OperationalError:
        return False


def _check_table(conn: sqlite3.Connection, table: str) -> None:
    if table not in _table_names(conn):
        raise NotFound(f"Table inconnue : {table}.", code="table_not_found")


def _columns(conn: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    references = {row["from"]: f"{row['table']}.{row['to'] or 'rowid'}" for row in conn.execute(f"PRAGMA foreign_key_list({_quote(table)})")}
    return [
        {
            "name": row["name"],
            "type": row["type"] or "",
            "not_null": bool(row["notnull"]),
            "primary_key": bool(row["pk"]),
            "default": row["dflt_value"],
            "references": references.get(row["name"]),
            "secret": bool(_SECRET_COLUMN_RE.search(row["name"])),
        }
        for row in conn.execute(f"PRAGMA table_info({_quote(table)})")
    ]


def _editable(conn: sqlite3.Connection, table: str) -> bool:
    return table not in READ_ONLY_TABLES and _has_rowid(conn, table)


def tables() -> list[dict[str, Any]]:
    """Les tables SQL : nom, nombre de lignes et de colonnes, ``editable``."""
    conn = connect()
    try:
        found = []
        for name in _table_names(conn):
            count = conn.execute(f"SELECT COUNT(*) FROM {_quote(name)}").fetchone()[0]
            columns = conn.execute(f"PRAGMA table_info({_quote(name)})").fetchall()
            found.append({"name": name, "rows": count, "columns": len(columns), "editable": _editable(conn, name)})
        return found
    finally:
        conn.close()


def _shown(columns: list[dict[str, Any]], row: sqlite3.Row) -> dict[str, Any]:
    values = {}
    for column in columns:
        value = row[column["name"]]
        if column["secret"] and value is not None:
            value = MASK
        elif isinstance(value, bytes):
            value = f"<{len(value)} octets>"
        values[column["name"]] = value
    return {"rowid": row["__rowid__"], "values": values}


def rows(table: str, *, q: str = "", sort: str | None = None, descending: bool = False, offset: int = 0, limit: int = 50) -> dict[str, Any]:
    """Une page des lignes de ``table`` : ``{table, columns, editable, items: [{rowid, values}],
    total}``. ``q`` cherche dans toutes les colonnes (texte contenu, sans casse) ; ``sort`` : une
    colonne (le ``rowid`` sinon)."""
    conn = connect()
    try:
        _check_table(conn, table)
        columns = _columns(conn, table)
        names = [column["name"] for column in columns]
        if sort is not None and sort not in names:
            raise InvalidInput(f"Colonne inconnue : {sort}.", code="unknown_column")
        offset = max(0, offset)
        limit = min(max(1, limit), MAX_LIMIT)
        has_rowid = _has_rowid(conn, table)
        where, params = "", []
        searchable = [column["name"] for column in columns if not column["secret"]]
        if q.strip() and searchable:
            where = " WHERE " + " OR ".join(f"CAST({_quote(name)} AS TEXT) LIKE ? ESCAPE '\\'" for name in searchable)
            pattern = "%" + q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            params = [pattern] * len(searchable)
        order_by = _quote(sort) if sort else ("rowid" if has_rowid else "1")
        direction = "DESC" if descending else "ASC"
        rowid = "rowid" if has_rowid else "NULL"
        total = conn.execute(f"SELECT COUNT(*) FROM {_quote(table)}{where}", params).fetchone()[0]
        found = conn.execute(
            f"SELECT {rowid} AS __rowid__, * FROM {_quote(table)}{where} ORDER BY {order_by} {direction} LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
        return {
            "table": table,
            "columns": columns,
            "editable": _editable(conn, table),
            "items": [_shown(columns, row) for row in found],
            "total": total,
        }
    finally:
        conn.close()


def _row(conn: sqlite3.Connection, table: str, rowid: int) -> sqlite3.Row:
    row = conn.execute(f"SELECT rowid AS __rowid__, * FROM {_quote(table)} WHERE rowid = ?", (rowid,)).fetchone()
    if row is None:
        raise NotFound(f"Ligne {rowid} introuvable dans {table}.", code="row_not_found")
    return row


def _writable(conn: sqlite3.Connection, table: str) -> None:
    _check_table(conn, table)
    if not _editable(conn, table):
        raise Conflict(f"La table {table} se lit seulement.", code="read_only_table")


def _integrity(exc: sqlite3.Error) -> Conflict:
    return Conflict(f"Refusé par la base : {exc}.", code="integrity_error")


def update_row(table: str, rowid: int, values: dict[str, Any], *, actor: str) -> dict[str, Any]:
    """Écrit ``values`` (colonne -> valeur JSON : texte, nombre, booléen ou ``null``) dans la ligne
    ``rowid`` et la rend. Une colonne inconnue ou secrète est refusée (422)."""
    if not values:
        raise InvalidInput("Aucune valeur à écrire.", code="no_values")
    conn = connect()
    try:
        _writable(conn, table)
        columns = {column["name"]: column for column in _columns(conn, table)}
        for name, value in values.items():
            if name not in columns:
                raise InvalidInput(f"Colonne inconnue : {name}.", code="unknown_column")
            if columns[name]["secret"]:
                raise InvalidInput(f"La colonne {name} est secrète : elle ne s'écrit pas ici.", code="secret_column")
            if not (value is None or isinstance(value, (str, int, float, bool))):
                raise InvalidInput(f"Valeur invalide pour {name}.", code="invalid_value")
        _row(conn, table, rowid)
        assignments = ", ".join(f"{_quote(name)} = ?" for name in values)
        try:
            conn.execute(f"UPDATE {_quote(table)} SET {assignments} WHERE rowid = ?", [*values.values(), rowid])
            conn.commit()
        except sqlite3.IntegrityError as exc:
            raise _integrity(exc) from exc
        logger.warning("base : %s a modifié %s[%s] (%s)", actor, table, rowid, ", ".join(values))
        return _shown(list(columns.values()), _row(conn, table, rowid))
    finally:
        conn.close()


def delete_row(table: str, rowid: int, *, actor: str) -> None:
    """Supprime la ligne ``rowid`` - les clés étrangères suivent le schéma (cascade, ``SET NULL``),
    ou la suppression est refusée (409)."""
    conn = connect()
    try:
        _writable(conn, table)
        _row(conn, table, rowid)
        try:
            conn.execute(f"DELETE FROM {_quote(table)} WHERE rowid = ?", (rowid,))
            conn.commit()
        except sqlite3.IntegrityError as exc:
            raise _integrity(exc) from exc
        logger.warning("base : %s a supprimé %s[%s]", actor, table, rowid)
    finally:
        conn.close()
