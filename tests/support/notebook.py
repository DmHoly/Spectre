"""Cahier de données (plugin notebook) : instantanés d'un µprojet et entrées du cahier d'une étude
(PRISM ou manuelles). Les aides ``post_*``, ``patch_*`` et ``delete_*`` renvoient la réponse telle
quelle (pour en vérifier un refus) ; les autres vérifient leur code de succès. ``if_match`` envoie
l'en-tête ``If-Match``.

Plus deux fabriques hors routes, pour les données d'avant le cahier unique : :func:`write_legacy`
écrit une version comme le faisait l'ancien code (vues ``data_notebook``, preuves Follow et leurs
métadonnées, jeux de l'ancienne galerie d'images externes), et :func:`objects_checksums` relève les
objets Follow d'un µprojet, pour vérifier qu'aucun n'est réécrit."""

from __future__ import annotations

import hashlib
from typing import Any, Callable

from .attachments import upload_file
from .http import assert_created, assert_ok


def snapshots_url(slug: str) -> str:
    return f"/api/microprojects/{slug}/snapshots"


def entries_url(slug: str, experiment_id: str) -> str:
    return f"/api/microprojects/{slug}/experiments/{experiment_id}/notebook-entries"


def _headers(if_match: str | None) -> dict:
    return {"If-Match": f'"{if_match}"'} if if_match else {}


def post_snapshot(client: Any, slug: str, hook: str = "eqe", wafers: tuple[str, ...] | list[str] = ("W12-A3", "W12-A4"), **fields: Any) -> Any:
    return client.post(snapshots_url(slug), json={"hook": hook, "wafers": list(wafers), **fields})


def take_snapshot(client: Any, slug: str, hook: str = "eqe", wafers: tuple[str, ...] | list[str] = ("W12-A3", "W12-A4")) -> dict:
    """POST /snapshots - renvoie l'instantané (``snapshot_id`` et le jeu de données)."""
    return assert_created(post_snapshot(client, slug, hook, wafers))


def get_snapshot(client: Any, slug: str, snapshot_id: str) -> Any:
    return client.get(f"{snapshots_url(slug)}/{snapshot_id}")


def upload_notebook_file(client: Any, slug: str, name: str = "mesure.png", **fields: Any) -> str:
    """Un fichier d'une entrée du cahier (POST .../attachments, purpose=notebook ; une image PNG par
    défaut, ``content=`` et ``content_type=`` pour un document) - renvoie son id."""
    return upload_file(client, slug, "notebook", name, **fields)["id"]


def entries(client: Any, slug: str, experiment_id: str, version: str | None = None, **filters: Any) -> list[dict]:
    """GET /notebook-entries : le cahier (de la pointe, ou de ``version``), filtré (``step``,
    ``wafer``, ``kind``)."""
    params = {**({"version": version} if version else {}), **filters}
    return assert_ok(client.get(entries_url(slug, experiment_id), params=params))


def entries_by_id(client: Any, slug: str, experiment_id: str, version: str | None = None) -> dict[str, dict]:
    return {entry["id"]: entry for entry in entries(client, slug, experiment_id, version)}


def step_counts(client: Any, slug: str, experiment_id: str, version: str | None = None, **filters: Any) -> dict[str, int]:
    """GET /notebook-entries?summary=steps - ``{step_id: n}``."""
    params = {"summary": "steps", **({"version": version} if version else {}), **filters}
    return assert_ok(client.get(entries_url(slug, experiment_id), params=params))


def get_entry(client: Any, slug: str, experiment_id: str, entry_id: str, version: str | None = None) -> Any:
    return client.get(f"{entries_url(slug, experiment_id)}/{entry_id}", params={"version": version} if version else {})


def post_entry(client: Any, slug: str, experiment_id: str, *, if_match: str | None = None, **body: Any) -> Any:
    return client.post(entries_url(slug, experiment_id), json=body, headers=_headers(if_match))


def prism_body(snapshot_id: str, *, title: str = "Vue", component: str = "table", options: dict | None = None, step_id: str | None = None, **fields: Any) -> dict:
    """Le corps d'une entrée PRISM d'une seule vue."""
    measurement = {"step_id": step_id, "snapshot_id": snapshot_id, "component": component, "options": options or {}}
    return {"kind": "prism", "title": title, "measurements": [measurement], **fields}


def add_entry(client: Any, slug: str, experiment_id: str, snapshot_id: str, *, if_match: str | None = None, **fields: Any) -> dict:
    """POST /notebook-entries : une entrée PRISM (voir :func:`prism_body`) - renvoie l'entrée."""
    return assert_created(post_entry(client, slug, experiment_id, if_match=if_match, **prism_body(snapshot_id, **fields)))


def add_manual(
    client: Any, slug: str, experiment_id: str, title: str = "Mesure", *, measurements: list[dict] | None = None, if_match: str | None = None, **fields: Any
) -> dict:
    """POST /notebook-entries : une entrée manuelle (une mesure non située, vide, par défaut) -
    renvoie l'entrée."""
    body = {"kind": "manual", "title": title, "measurements": [{}] if measurements is None else measurements, **fields}
    return assert_created(post_entry(client, slug, experiment_id, if_match=if_match, **body))


def patch_entry(client: Any, slug: str, experiment_id: str, entry_id: str, *, if_match: str | None = None, **changes: Any) -> Any:
    return client.patch(f"{entries_url(slug, experiment_id)}/{entry_id}", json=changes, headers=_headers(if_match))


def update_entry(client: Any, slug: str, experiment_id: str, entry_id: str, *, if_match: str | None = None, **changes: Any) -> dict:
    """PATCH /notebook-entries/{entry_id} (``position`` pour la déplacer) - renvoie l'entrée."""
    return assert_ok(patch_entry(client, slug, experiment_id, entry_id, if_match=if_match, **changes))


def delete_entry(client: Any, slug: str, experiment_id: str, entry_id: str, *, if_match: str | None = None) -> Any:
    return client.delete(f"{entries_url(slug, experiment_id)}/{entry_id}", headers=_headers(if_match))


def get_external_image(client: Any, slug: str, experiment_id: str, entry_id: str, index: int | str, **params: Any) -> Any:
    """GET /notebook-entries/{entry_id}/external-images/{index} (la réponse : les octets, ou le refus)."""
    return client.get(f"{entries_url(slug, experiment_id)}/{entry_id}/external-images/{index}", params=params)


def as_input(measurement: dict) -> dict:
    """Une mesure lue, telle qu'une écriture la renvoie (sans ce que le serveur calcule)."""
    dropped = {"step_retired", "snapshot"}
    sent = {key: value for key, value in measurement.items() if key not in dropped and value is not None}
    if "attachments" in sent:
        sent["attachments"] = [{"id": a["id"], "caption": a.get("caption")} for a in sent["attachments"]]
    if "external_images" in sent:
        sent["external_images"] = [{"path": i["path"], "caption": i.get("caption")} for i in sent["external_images"]]
    return sent


# -- les données d'avant le cahier unique ----------------------------------------------------------


def write_legacy(slug: str, line: str, change: Callable[[Any, Any], None], *, keep_step_ids: bool = True) -> str:
    """Écrit sur la piste ``line`` une version comme le faisait le code d'avant le cahier unique -
    hors de Spectre, avec Follow seul, par Ada : la pointe reportée (preuves comprises), puis
    ``change(builder, parent)`` ; sans ``process_step_ids`` si ``keep_step_ids`` est faux (une version
    d'avant les ids d'étape). Renvoie l'id de la version."""
    import follow

    from spectre.plugins.experiments import repository

    outside = follow.Repository(repository.follow_repo_path(slug))
    parent = outside.get(outside.branches[line])
    builder = outside.derive(parent.id, title=parent.title, intent=parent.intent, hypothesis=parent.hypothesis, author="Ada")
    builder.metadata = {key: value for key, value in parent.metadata.items() if keep_step_ids or key != "process_step_ids"}
    builder.form_answers = dict(parent.form_answers)
    builder.evidence = list(parent.evidence)
    builder.tags = list(parent.tags)
    builder.conclusion = parent.conclusion
    change(builder, parent)
    return builder.commit().id


def legacy_evidence(
    builder: Any,
    evidence_id: str,
    description: str = "Mesure",
    *,
    source: str = "",
    metrics: dict | None = None,
    step_index: int | None = None,
    links: list[str] | None = None,
    images: list[dict] | None = None,
    **extra: Any,
) -> None:
    """Ajoute à ``builder`` une preuve telle que l'ancien plugin evidence l'écrivait : la preuve
    Follow, ses champs Spectre (``extra`` : ``kind``, ``objective``, ``interpretation``,
    ``graph_config``, ``image_annotations``) sous ``evidence_extra``, ses liens sous
    ``evidence_links`` et ses images (``{id, filename, content_type, size, caption}``) dans
    ``attachments``, avec son ``evidence_id``."""
    import follow

    builder.add_evidence(
        id=evidence_id,
        description=description,
        source=source,
        metrics={name: follow.Quantity(**quantity) for name, quantity in (metrics or {}).items()},
        step_index=step_index,
    )
    builder.metadata["evidence_extra"] = {**builder.metadata.get("evidence_extra", {}), evidence_id: {"kind": "standard", **extra}}
    if links:
        builder.metadata["evidence_links"] = {**builder.metadata.get("evidence_links", {}), evidence_id: list(links)}
    if images:
        builder.metadata["attachments"] = list(builder.metadata.get("attachments", [])) + [
            {"entity_index": None, "evidence_id": evidence_id, "uploaded_by": "Ada", "uploaded_at": "2026-01-02T03:04:05+00:00", **image} for image in images
        ]


def legacy_view(builder: Any, view_id: str, snapshot: dict, *, title: str = "Vue", component: str = "table", **fields: Any) -> None:
    """Ajoute à ``builder`` une vue de l'ancien cahier (``data_notebook``), sur l'instantané
    ``snapshot`` (la réponse de ``POST /snapshots``)."""
    view = {
        "id": view_id,
        "title": title,
        "snapshot_id": snapshot["snapshot_id"],
        "hook": snapshot["hook"],
        "hook_title": snapshot.get("hook_title"),
        "wafers": snapshot["wafers"],
        "source": snapshot["source"],
        "fetched_at": snapshot["fetched_at"],
        "row_count": len(snapshot["rows"]),
        "component": component,
        "options": {},
        "note": None,
        "objective": None,
        "in_report": True,
        "created_by": "Ada",
        "created_at": "2026-01-02T03:04:05+00:00",
        "updated_by": "Ada",
        "updated_at": "2026-01-02T03:04:05+00:00",
        **fields,
    }
    builder.metadata["data_notebook"] = [*builder.metadata.get("data_notebook", []), view]


def legacy_image_set(
    builder: Any,
    set_id: str,
    paths: list[str],
    *,
    title: str | None = None,
    note: str | None = None,
    entity_index: int | None = None,
    pinned_index: int = 0,
) -> None:
    """Ajoute à ``builder`` un jeu de l'ancienne galerie d'images externes (``data_items``), tel que
    l'ancien plugin external_images l'écrivait."""
    record = {
        "id": set_id,
        "title": title,
        "note": note,
        "entity_index": entity_index,
        "image_paths": list(paths),
        "pinned_index": pinned_index,
        "created_by": "Ada",
        "created_at": "2026-01-02T03:04:05+00:00",
    }
    builder.metadata["data_items"] = [*builder.metadata.get("data_items", []), record]


def objects_checksums(slug: str) -> dict[str, str]:
    """La somme SHA-256 de chaque objet Follow du µprojet, par nom de fichier."""
    from spectre.plugins.experiments import repository

    objects = repository.follow_repo_path(slug) / "objects"
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(objects.rglob("*")) if path.is_file()}
