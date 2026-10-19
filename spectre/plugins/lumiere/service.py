"""Les rapports générés : demandés (:func:`request`), faits en tâche de fond (un fil par rapport, un seul à la fois
par utilisateur), gardés sous ``<data>/lumiere/reports/<id>.html`` et listés. Un rapport appartient à qui l'a
demandé ; un administrateur les voit tous. ``SPECTRE_LUMIERE_SYNC=1`` : la génération se fait dans la requête
(les tests)."""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ...kernel.db import data_dir, get_conn
from ...kernel.errors import DomainError, Forbidden, InvalidInput, NotFound
from ..accounts.service import User
from . import context as contexts
from . import templates

log = logging.getLogger(__name__)

STATUSES = ("queued", "running", "done", "error")
MAX_PER_USER_RUNNING = 1
KEEP_PER_CONTEXT = 20  # au-delà, les plus vieux rapports d'un même contexte et d'un même utilisateur sont retirés

_lock = threading.Lock()
_running: set[int] = set()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def reports_dir() -> Path:
    path = data_dir() / "lumiere" / "reports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _payload(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "template": row["template"],
        "context": {"kind": row["context_kind"], "key": row["context_key"]},
        "title": row["title"],
        "status": row["status"],
        "message": row["message"],
        "bytes": row["bytes"],
        "created_at": row["created_at"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "file_url": f"/api/lumiere/reports/{row['id']}/file" if row["status"] == "done" else None,
    }


def _row(report_id: int) -> Any:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM lumiere_reports WHERE id = ?", (report_id,)).fetchone()
    if row is None:
        raise NotFound("Rapport inconnu.", code="unknown_report")
    return row


def _visible(user: User, row: Any) -> Any:
    if row["user_id"] != user.id and not user.is_admin:
        raise Forbidden("Ce rapport n'est pas le vôtre.", code="not_report_owner")
    return row


def clean_context(user: User, template: templates.Template, context: dict[str, Any] | None) -> tuple[str, str, str]:
    """(genre, clé, titre) d'un contexte pour ce modèle : du bon genre, existant et visible de ``user`` (422, 404,
    403 sinon)."""
    context = context or {}
    kind = str(context.get("kind") or "")
    key = " ".join(str(context.get("key") or "").split())
    if kind != template.context:
        raise InvalidInput(f"Le modèle « {template.name} » s'applique à {templates.CONTEXTS.get(template.context, template.context)}.", code="wrong_context")
    if not key or len(key) > 200:
        raise InvalidInput("Indiquez ce que le rapport décrit (la plaque, l'analyse, l'étude...).", code="missing_context_key")
    title = f"{template.name} · {contexts.make(user, kind, key).title}"
    return kind, key, title


def request(user: User, template_key: str, context: dict[str, Any] | None) -> dict[str, Any]:
    """Demande un rapport : la ligne est créée ``queued`` et la génération part en tâche de fond."""
    template = templates.get(template_key)
    kind, key, title = clean_context(user, template, context)
    with get_conn() as conn:
        running = conn.execute("SELECT COUNT(*) FROM lumiere_reports WHERE user_id = ? AND status IN ('queued', 'running')", (user.id,)).fetchone()[0]
        if running >= MAX_PER_USER_RUNNING:
            raise InvalidInput("Un rapport est déjà en cours pour vous : attendez qu'il soit fait.", code="report_running")
        cursor = conn.execute(
            "INSERT INTO lumiere_reports (user_id, template, context_kind, context_key, title, status, created_at) VALUES (?, ?, ?, ?, ?, 'queued', ?)",
            (user.id, template.key, kind, key, title, _now()),
        )
        report_id = cursor.lastrowid
    _forget_old(user, kind, key)
    if os.environ.get("SPECTRE_LUMIERE_SYNC") == "1":
        _run(report_id, user)
    else:
        threading.Thread(target=_run, args=(report_id, user), name=f"lumiere-report-{report_id}", daemon=True).start()
    return _payload(_row(report_id))


def _set(report_id: int, **values: Any) -> None:
    keys = ", ".join(f"{k} = ?" for k in values)
    with get_conn() as conn:
        conn.execute(f"UPDATE lumiere_reports SET {keys} WHERE id = ?", (*values.values(), report_id))


def _run(report_id: int, user: User) -> None:
    with _lock:
        _running.add(report_id)
    _set(report_id, status="running", started_at=_now())
    try:
        row = _row(report_id)
        template = templates.get(row["template"])
        html = templates.build(user, template, row["context_key"]).render()
        path = reports_dir() / f"{report_id}.html"
        path.write_text(html, encoding="utf-8")
        _set(report_id, status="done", file=path.name, bytes=path.stat().st_size, finished_at=_now(), message="")
    except DomainError as exc:
        _set(report_id, status="error", finished_at=_now(), message=str(exc))
    except Exception as exc:  # une erreur du moteur ne doit pas rester muette
        log.exception("rapport Lumière %s en échec", report_id)
        _set(report_id, status="error", finished_at=_now(), message=f"Le moteur de rapports a échoué : {type(exc).__name__} : {exc}"[:500])
    finally:
        with _lock:
            _running.discard(report_id)


def _forget_old(user: User, kind: str, key: str) -> None:
    with get_conn() as conn:
        old = conn.execute(
            "SELECT id, file FROM lumiere_reports WHERE user_id = ? AND context_kind = ? AND context_key = ? ORDER BY id DESC LIMIT -1 OFFSET ?",
            (user.id, kind, key, KEEP_PER_CONTEXT),
        ).fetchall()
        for row in old:
            conn.execute("DELETE FROM lumiere_reports WHERE id = ?", (row["id"],))
    for row in old:
        _unlink(row["file"])


def _unlink(name: str | None) -> None:
    if name:
        try:
            (reports_dir() / name).unlink(missing_ok=True)
        except OSError as exc:
            log.warning("rapport %s non supprimé : %s", name, exc)


def list_reports(user: User, *, context_kind: str | None = None, context_key: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    """Les rapports de l'utilisateur (tous pour un administrateur), les plus récents d'abord ; filtrés par contexte."""
    where, params = [], []
    if not user.is_admin:
        where.append("user_id = ?")
        params.append(user.id)
    if context_kind:
        where.append("context_kind = ?")
        params.append(context_kind)
    if context_key:
        where.append("context_key = ?")
        params.append(" ".join(context_key.split()))
    sql = "SELECT * FROM lumiere_reports" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY id DESC LIMIT ?"
    with get_conn() as conn:
        rows = conn.execute(sql, (*params, limit)).fetchall()
    return [_payload(r) for r in rows]


def get(user: User, report_id: int) -> dict[str, Any]:
    return _payload(_visible(user, _row(report_id)))


def file_path(user: User, report_id: int) -> tuple[Path, str]:
    """Le fichier d'un rapport fait et le nom sous lequel le télécharger."""
    row = _visible(user, _row(report_id))
    if row["status"] != "done" or not row["file"]:
        raise NotFound("Ce rapport n'est pas (encore) fait.", code="report_not_ready")
    path = reports_dir() / row["file"]
    if not path.is_file():
        raise NotFound("Le fichier de ce rapport a disparu du serveur.", code="report_file_missing")
    safe = "".join(c if c.isalnum() or c in "-_." else "-" for c in f"{row['template']}-{row['context_key']}")
    return path, f"rapport-{safe}-{report_id}.html"


def delete(user: User, report_id: int) -> None:
    row = _visible(user, _row(report_id))
    if row["status"] in ("queued", "running"):
        raise InvalidInput("Ce rapport est en cours : attendez qu'il soit fait.", code="report_running")
    with get_conn() as conn:
        conn.execute("DELETE FROM lumiere_reports WHERE id = ?", (report_id,))
    _unlink(row["file"])


def storage() -> dict[str, Any]:
    """Ce que pèsent les rapports gardés."""
    with get_conn() as conn:
        count, total = conn.execute("SELECT COUNT(*), COALESCE(SUM(bytes), 0) FROM lumiere_reports WHERE status = 'done'").fetchone()
    return {"reports": count, "bytes": total, "running": len(_running)}
