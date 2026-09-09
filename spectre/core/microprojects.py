"""Microprojects and membership - the data-access layer over the ``microprojects``/``memberships`` tables,
plus where each microproject's own Follow repository, saved structures, and step presets live on disk.
Follow and StructureForge never know a "microproject" exists; this is the one place that maps a slug
to the paths they're given.
"""

from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from .db import data_dir, get_conn

ROLE_ORDER = {"viewer": 0, "editor": 1, "owner": 2}


class MicroprojectNotFoundError(Exception):
    pass


@dataclass(frozen=True)
class Microproject:
    """A "µprojet": one topic addressed under a management area (:mod:`spectre.core.management`).
    Table/dir/API keep the historical name ``microproject``.
    """

    id: int
    slug: str
    name: str
    description: str
    created_by: int
    management_area_id: int | None = None


def _microproject_from_row(row: sqlite3.Row) -> Microproject:
    keys = row.keys()
    return Microproject(
        id=row["id"],
        slug=row["slug"],
        name=row["name"],
        description=row["description"],
        created_by=row["created_by"],
        management_area_id=row["management_area_id"] if "management_area_id" in keys else None,
    )


def slugify(name: str) -> str:
    """A URL-safe slug from a display name: strip diacritics ("Fiabilité" -> "fiabilite"), then
    collapse anything non-alphanumeric to single dashes. Shared with :mod:`spectre.core.management`.
    """
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.strip().lower()).strip("-")


def _slugify(name: str) -> str:
    return slugify(name) or "microprojet"


def _unique_slug(conn: sqlite3.Connection, base: str) -> str:
    slug = base
    suffix = 2
    while conn.execute("SELECT 1 FROM microprojects WHERE slug = ?", (slug,)).fetchone():
        slug = f"{base}-{suffix}"
        suffix += 1
    return slug


def create(name: str, description: str, *, owner_id: int, management_area_id: int | None = None) -> Microproject:
    name = name.strip()
    if not name:
        raise ValueError("le nom du µprojet est obligatoire")
    with get_conn() as conn:
        if management_area_id is None:
            management_area_id = conn.execute(
                "SELECT id FROM management_areas WHERE slug = ?", ("non-classe",)
            ).fetchone()["id"]
        slug = _unique_slug(conn, _slugify(name))
        cursor = conn.execute(
            "INSERT INTO microprojects (slug, name, description, management_area_id, created_by) VALUES (?, ?, ?, ?, ?)",
            (slug, name, description.strip(), management_area_id, owner_id),
        )
        microproject_id = cursor.lastrowid
        conn.execute(
            "INSERT INTO memberships (microproject_id, user_id, role) VALUES (?, ?, 'owner')",
            (microproject_id, owner_id),
        )
    microproject_dir(slug)  # create the on-disk home for this microproject's Follow repo/structures upfront
    return Microproject(
        id=microproject_id,
        slug=slug,
        name=name,
        description=description.strip(),
        created_by=owner_id,
        management_area_id=management_area_id,
    )


def set_management_area(microproject_id: int, management_area_id: int) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE microprojects SET management_area_id = ? WHERE id = ?", (management_area_id, microproject_id))


def list_by_management_area(management_area_id: int) -> list[Microproject]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM microprojects WHERE management_area_id = ? ORDER BY created_at DESC", (management_area_id,)
        ).fetchall()
    return [_microproject_from_row(row) for row in rows]


def list_all() -> list[Microproject]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM microprojects ORDER BY created_at DESC").fetchall()
    return [_microproject_from_row(row) for row in rows]


def get_by_slug(slug: str) -> Microproject:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM microprojects WHERE slug = ?", (slug,)).fetchone()
    if row is None:
        raise MicroprojectNotFoundError(slug)
    return _microproject_from_row(row)


def get_by_id(microproject_id: int) -> Microproject:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM microprojects WHERE id = ?", (microproject_id,)).fetchone()
    if row is None:
        raise MicroprojectNotFoundError(str(microproject_id))
    return _microproject_from_row(row)


def list_for_user(user_id: int) -> list[tuple[Microproject, str]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT microprojects.*, memberships.role AS role FROM microprojects "
            "JOIN memberships ON memberships.microproject_id = microprojects.id "
            "WHERE memberships.user_id = ? ORDER BY microprojects.created_at DESC",
            (user_id,),
        ).fetchall()
    return [(_microproject_from_row(row), row["role"]) for row in rows]


def role_for(microproject_id: int, user_id: int) -> str | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT role FROM memberships WHERE microproject_id = ? AND user_id = ?", (microproject_id, user_id)
        ).fetchone()
    return row["role"] if row else None


def list_members(microproject_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT users.id, users.name, users.email, memberships.role FROM memberships "
            "JOIN users ON users.id = memberships.user_id WHERE memberships.microproject_id = ? "
            "ORDER BY users.name",
            (microproject_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def add_member(microproject_id: int, microproject_name: str, email: str, role: str, *, invited_by: int) -> str:
    """Add ``email`` to the microproject directly if they already have an account (returns
    ``"added"``), or create a two-week invitation and e-mail them a signup link otherwise
    (returns ``"invited"``) - see :func:`accept_invitation` for the other end of that link.
    """
    from . import accounts
    from . import email as email_module
    from . import security

    if role not in ROLE_ORDER:
        raise ValueError(f"rôle inconnu : {role!r}")
    email = email.strip().lower()
    user = accounts.get_by_email(email)
    if user is not None:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO memberships (microproject_id, user_id, role) VALUES (?, ?, ?) "
                "ON CONFLICT(microproject_id, user_id) DO UPDATE SET role = excluded.role",
                (microproject_id, user.id, role),
            )
        return "added"

    token = security.new_token()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO invitations (token, microproject_id, email, role, invited_by, expires_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (token, microproject_id, email, role, invited_by, security.invitation_expiry()),
        )
    inviter = accounts.get_by_id(invited_by)
    link = f"{email_module.base_url()}/inscription?invitation={token}"
    email_module.send_email(
        email,
        f"Invitation à rejoindre « {microproject_name} » sur Spectre",
        f"{inviter.name if inviter else 'Un membre'} vous invite à rejoindre le projet "
        f"« {microproject_name} » sur Spectre.\n\n"
        f"Pour créer votre compte et rejoindre le projet, ouvrez ce lien (valable 14 jours) :\n{link}",
    )
    return "invited"


def remove_member(microproject_id: int, user_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM memberships WHERE microproject_id = ? AND user_id = ?", (microproject_id, user_id))


def list_invitations(microproject_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT token, email, role, created_at FROM invitations WHERE microproject_id = ? ORDER BY created_at DESC",
            (microproject_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def cancel_invitation(microproject_id: int, token: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM invitations WHERE microproject_id = ? AND token = ?", (microproject_id, token))


def get_invitation(token: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT invitations.token, invitations.email, invitations.role, invitations.microproject_id, "
            "microprojects.name AS microproject_name FROM invitations JOIN microprojects ON microprojects.id = invitations.microproject_id "
            "WHERE invitations.token = ? AND invitations.expires_at > datetime('now')",
            (token,),
        ).fetchone()
    return dict(row) if row else None


def accept_invitation(token: str, user_id: int, user_email: str) -> bool:
    """Consume an invitation for a just-registered user - only if its email matches the one the
    invitation was addressed to (a token alone isn't proof of that email address, since it
    travels inside a plain URL). Returns whether it was accepted.
    """
    invitation = get_invitation(token)
    if invitation is None or invitation["email"] != user_email.strip().lower():
        return False
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO memberships (microproject_id, user_id, role) VALUES (?, ?, ?) "
            "ON CONFLICT(microproject_id, user_id) DO UPDATE SET role = excluded.role",
            (invitation["microproject_id"], user_id, invitation["role"]),
        )
        conn.execute("DELETE FROM invitations WHERE token = ?", (token,))
    return True


def delete(microproject: Microproject) -> None:
    """Permanently delete a microproject: its database rows (memberships and pending invitations
    cascade via the foreign keys) and the on-disk directory holding its Follow repository, saved
    structures, step presets, and tech bricks - there is no undo, this is real experiment history.
    """
    import shutil

    with get_conn() as conn:
        conn.execute("DELETE FROM microprojects WHERE id = ?", (microproject.id,))
    shutil.rmtree(microproject_dir(microproject.slug), ignore_errors=True)


def microproject_dir(slug: str) -> Path:
    path = data_dir() / "microprojects" / slug
    path.mkdir(parents=True, exist_ok=True)
    return path


def follow_repo_path(slug: str) -> Path:
    return microproject_dir(slug) / "follow"


def attachments_dir(slug: str) -> Path:
    """Where uploaded files live for this microproject (see :mod:`spectre.api.experiments`'s
    attachment routes) - one blob plus a small JSON sidecar (original filename/content
    type/size) per attachment, named by its id rather than the uploaded filename so nothing here
    ever has to sanitize that into a safe path.
    """
    path = microproject_dir(slug) / "attachments"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _scoped_store_getters(own_filename: str, shared_filename: str, store_factory):
    """A ``(get_own, get_shared)`` pair of store getters for a JSON-backed keyed collection that
    lives, the same way for every one of them (see :mod:`spectre.core.keyed_store`), as one file
    inside a microproject's own directory and one shared file visible from every microproject - the split
    :func:`get_structure_store`/:func:`get_step_preset_store` and their ``get_shared_*``
    counterparts both need, with only the filename and the store type differing.
    """

    def get_own(slug: str):
        return store_factory(microproject_dir(slug) / own_filename)

    def get_shared():
        return store_factory(data_dir() / shared_filename)

    return get_own, get_shared


def _structure_library_store(path: Path):
    from .structure_library import StructureLibraryStore

    return StructureLibraryStore(path)


get_structure_store, get_shared_structure_store = _scoped_store_getters(
    "structures.json", "structures_partagees.json", _structure_library_store
)


def _intent_form_store(path: Path):
    from .intent_forms import IntentFormStore

    return IntentFormStore(path)


get_intent_form_store, get_shared_intent_form_store = _scoped_store_getters(
    "formulaires_intention.json", "formulaires_intention_partagees.json", _intent_form_store
)


def active_intent_form_path(slug: str) -> Path:
    return microproject_dir(slug) / "formulaire_intention_actif.json"


def get_active_intent_form(slug: str) -> dict | None:
    """Which library entry (``{"name": ..., "partagee": bool}``) this microproject currently uses as
    its Follow commit form, if any - just a pointer to the library entry (so the settings page can
    show "formulaire actif : X" and offer to deactivate it) alongside the real materialized copy,
    ``<repo>/commit_form.yml``, which is the only file Follow itself ever reads.
    """
    path = active_intent_form_path(slug)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def activate_intent_form(slug: str, *, name: str, partagee: bool, form) -> None:
    """Materialize ``form`` (a :class:`follow.storage.commit_form.CommitForm`) as this microproject's
    active commit form - written to ``<repo>/commit_form.yml``, which
    ``follow.storage.repository.Repository`` picks up automatically the next time this microproject's
    repository is opened (every :func:`get_repository` call - nothing is cached), and remember
    which library entry it came from.
    """
    from .intent_forms import dump_yaml_form

    repo_path = follow_repo_path(slug)
    repo_path.mkdir(parents=True, exist_ok=True)
    (repo_path / "commit_form.yml").write_text(dump_yaml_form(form), encoding="utf-8")
    active_intent_form_path(slug).write_text(json.dumps({"name": name, "partagee": partagee}), encoding="utf-8")


def deactivate_intent_form(slug: str) -> None:
    (follow_repo_path(slug) / "commit_form.yml").unlink(missing_ok=True)
    active_intent_form_path(slug).unlink(missing_ok=True)


def get_repository(slug: str):
    """A fresh ``follow.storage.repository.Repository`` for this microproject, reloaded from disk on
    every call - Spectre serves many microprojects from one process, so nothing is cached in memory
    the way ``follow_api`` (one repository per process) can afford to.
    """
    import follow

    return follow.Repository(follow_repo_path(slug))


RUNNING_STATUSES = {"draft", "running"}
CONCLUDED_STATUSES = {"concluded", "abandoned"}


def branch_tips(repo) -> list:
    """One experiment per branch - its current tip - rather than every version ever committed to
    it. A branch is one line of study: "conclure"/"preuves"/"étiquettes" all record a new,
    otherwise-identical version (experiments are immutable), so without this a single study could
    show up as several cards, its own earlier drafts included, even after being concluded. The
    full version-by-version history is still there on the fiche itself ("Suivi de l'expérience")
    and on the microproject's graph - this only thins out summary lists (the experiences list, microproject
    counts, "comparer avec", "combiner avec").
    """
    seen_ids: set[str] = set()
    tips = []
    for tip_id in repo.branches.values():
        if tip_id in seen_ids:
            continue
        seen_ids.add(tip_id)
        tips.append(repo.get(tip_id))
    return tips


def _step_preset_store(path: Path):
    from .step_presets import StepPresetStore

    return StepPresetStore(path)


get_step_preset_store, get_shared_step_preset_store = _scoped_store_getters(
    "presets_etapes.json", "presets_etapes_partages.json", _step_preset_store
)


def _tech_brick_store(path: Path):
    from .tech_bricks import TechBrickStore

    return TechBrickStore(path)


get_tech_brick_store, get_shared_tech_brick_store = _scoped_store_getters(
    "briques.json", "briques_partagees.json", _tech_brick_store
)
