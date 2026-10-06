"""The database over HTTP, admin only - the mechanics are the kernel's (:mod:`spectre.kernel.database`):

- ``GET /api/database`` : what a backup will hold (database size, number and size of the other files);
- ``GET /api/database/backup`` : the ZIP of the whole data directory, built on the fly;
- ``GET /api/database/tables`` : the SQL tables, ``GET .../tables/{table_name}/rows`` a page of one
  (``q``, ``sort``, ``desc``, ``offset``, ``limit``) ;
- ``PATCH .../rows/{row_id}`` ``{values: {column: value}}`` writes cells, ``DELETE`` removes the row
  (foreign keys follow the schema, or 409 ``integrity_error``).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from ...kernel import database
from ..accounts.deps import require_admin
from ..accounts.service import User
from .schemas import RowPatch

router = APIRouter(prefix="/database", tags=["settings"])  # inclus sous /api par api.py


def _actor(user: User) -> str:
    return f"{user.email} (#{user.id})"


@router.get("")
def summary(_user: User = Depends(require_admin)) -> dict:
    return database.data_summary()


@router.get("/backup")
def backup(user: User = Depends(require_admin)) -> FileResponse:
    handle = tempfile.NamedTemporaryFile(prefix="spectre-backup-", suffix=".zip", delete=False)
    handle.close()
    target = Path(handle.name)
    try:
        database.write_backup(target)
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    database.logger.warning("base : %s a téléchargé une sauvegarde", _actor(user))
    return FileResponse(
        target,
        media_type="application/zip",
        filename=database.backup_filename(),
        background=BackgroundTask(target.unlink, missing_ok=True),
    )


@router.get("/tables")
def list_tables(_user: User = Depends(require_admin)) -> list[dict]:
    return database.tables()


@router.get("/tables/{table_name}/rows")
def list_rows(
    table_name: str,
    q: str = "",
    sort: str | None = None,
    desc: bool = False,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=database.MAX_LIMIT),
    _user: User = Depends(require_admin),
) -> dict:
    return database.rows(table_name, q=q, sort=sort, descending=desc, offset=offset, limit=limit)


@router.patch("/tables/{table_name}/rows/{row_id}")
def update_row(table_name: str, row_id: int, body: RowPatch, user: User = Depends(require_admin)) -> dict:
    return database.update_row(table_name, row_id, body.values, actor=_actor(user))


@router.delete("/tables/{table_name}/rows/{row_id}", status_code=204)
def delete_row(table_name: str, row_id: int, user: User = Depends(require_admin)) -> Response:
    database.delete_row(table_name, row_id, actor=_actor(user))
    return Response(status_code=204)
