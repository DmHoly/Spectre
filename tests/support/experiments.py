"""Expériences (plugin experiments) : lancer une piste, la faire évoluer, la conclure... Chaque aide
encapsule une route et vérifie son code de succès ; ``fields`` complète ou remplace le corps envoyé.
Les aides d'écriture renvoient l'étude à jour (``id`` : la piste, ``version_id`` : sa dernière
version) ; ``if_match`` envoie l'en-tête ``If-Match`` (la version affichée)."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from .http import assert_created, assert_ok
from .structures import campaign_plan, steps, substrate

# Les champs d'une structure, rangés sous ``structure`` (le reste est l'intention).
STRUCTURE_FIELDS = ("substrate", "steps", "declared_params", "layer_labels", "bricks", "recipes", "preset_origins", "plan", "images", "description", "factors", "wafers")


def experiments_url(slug: str) -> str:
    return f"/api/microprojects/{slug}/experiments"


def experiment_url(slug: str, ref: str) -> str:
    return f"{experiments_url(slug)}/{ref}"


def _headers(if_match: str | None) -> dict:
    return {"If-Match": f'"{if_match}"'} if if_match else {}


def _split(kind: str, fields: dict) -> dict:
    """``fields`` dont les champs de structure passent sous ``structure`` (``kind`` compris)."""
    structure = {"kind": kind, **{key: fields.pop(key) for key in STRUCTURE_FIELDS if key in fields}}
    if kind not in ("images", "declared"):
        structure.setdefault("substrate", substrate())
        structure.setdefault("steps", steps())
    return {"structure": structure, **fields}


def launch_body(*, title: str = "Essai", intent: str = "Verifier", entities: list[dict] | None = None, kind: str = "process", **fields: Any) -> dict:
    """Le corps d'un lancement : une couche d'oxyde sur Si, suivie sur le wafer W1, sauf mention
    contraire (``steps=``, ``substrate=``, ``plan=``, ``images=`` vont dans ``structure``)."""
    body = {"title": title, "intent": intent, "entities": [{"sample_id": "W1"}] if entities is None else entities, **fields}
    return _split(kind, body)


def post_launch(client: Any, slug: str, **fields: Any) -> Any:
    """POST /experiments, tel quel (la réponse, pour en vérifier un refus)."""
    return client.post(experiments_url(slug), json=launch_body(**fields))


def launch(client: Any, slug: str, **fields: Any) -> dict:
    """POST /experiments (voir :func:`launch_body`) - renvoie l'étude créée."""
    return assert_created(post_launch(client, slug, **fields))


def launch_campaign(client: Any, slug: str, plan: dict | None = None, **fields: Any) -> dict:
    """Une campagne - par défaut trois épaisseurs d'oxyde (10, 20, 30 nm)."""
    fields = {"title": "Campagne", "intent": "Balayer l'epaisseur", **fields}
    return launch(client, slug, kind="campaign", plan=plan or campaign_plan([10, 20, 30]), **fields)


def launch_image(client: Any, slug: str, images: list[dict], **fields: Any) -> dict:
    """Une structure donnée en images (``{image_id, kind, caption}``)."""
    fields = {"title": "Coupe", "intent": "Documenter", **fields}
    return launch(client, slug, kind="images", images=images, **fields)


def launch_declared(client: Any, slug: str, factors: list[str] | None = None, wafers: list[dict] | None = None, **fields: Any) -> dict:
    """Une expérience sans structure : décrite, son split déclaré (par défaut une colonne « Recuit »,
    deux plaques - la réf et un recuit long), aucune plaque nommée sauf ``entities=``."""
    fields = {"title": "Recuit", "intent": "Voir l'effet du recuit", "entities": [], "description": "Contact P sur GaN", **fields}
    factors = ["Recuit"] if factors is None else factors
    wafers = [{"label": "réf", "values": ["standard"]}, {"values": ["long"]}] if wafers is None else wafers
    return launch(client, slug, kind="declared", factors=factors, wafers=wafers, **fields)


def get_experiment(client: Any, slug: str, ref: str) -> dict:
    return assert_ok(client.get(experiment_url(slug, ref)))



def get_version(client: Any, slug: str, ref: str, version_id: str) -> dict:
    return assert_ok(client.get(f"{experiment_url(slug, ref)}/versions/{version_id}"))


def versions(client: Any, slug: str, ref: str) -> list[dict]:
    """La frise de la piste : chaque version, de la première à la pointe."""
    return assert_ok(client.get(f"{experiment_url(slug, ref)}/versions"))


def lineage(client: Any, slug: str) -> dict:
    """Le graphe de filiation du µprojet (``{nodes, edges}``)."""
    return assert_ok(client.get(f"/api/microprojects/{slug}/lineage"))


def post_evolve(client: Any, slug: str, ref: str, *, kind: str = "process", if_match: str | None = None, **fields: Any) -> Any:
    return client.post(f"{experiment_url(slug, ref)}/versions", json=_split(kind, fields), headers=_headers(if_match))


def evolve(client: Any, slug: str, ref: str, *, title: str = "Essai", intent: str = "Suite", **fields: Any) -> dict:
    """POST /versions - par défaut le même procédé ; ``steps=...`` pour le changer."""
    return assert_created(post_evolve(client, slug, ref, title=title, intent=intent, **fields))


def evolve_image(client: Any, slug: str, ref: str, images: list[dict], *, title: str = "Coupe", intent: str = "Suite", **fields: Any) -> dict:
    return assert_created(post_evolve(client, slug, ref, kind="images", images=images, title=title, intent=intent, **fields))


def _put(client: Any, slug: str, ref: str, resource: str, body: dict, if_match: str | None) -> Any:
    return client.put(f"{experiment_url(slug, ref)}/{resource}", json=body, headers=_headers(if_match))


def conclude(client: Any, slug: str, ref: str, status: str = "concluded", *, if_match: str | None = None, **fields: Any) -> dict:
    """PUT /conclusion - ``fields`` : ``decision``, ``summary``, ``objective_results``..."""
    return assert_ok(_put(client, slug, ref, "conclusion", {"status": status, **fields}, if_match))


def set_status(client: Any, slug: str, ref: str, status: str, *, if_match: str | None = None, **fields: Any) -> dict:
    """PUT /status (brouillon, en cours, en pause) - ``hold_reason`` pour une pause."""
    return assert_ok(_put(client, slug, ref, "status", {"status": status, **fields}, if_match))


def tag(client: Any, slug: str, ref: str, tags: list[str], *, if_match: str | None = None) -> dict:
    return assert_ok(_put(client, slug, ref, "tags", {"tags": tags}, if_match))


def track_entities(client: Any, slug: str, ref: str, entities: list[dict], *, if_match: str | None = None) -> dict:
    """PUT /entities : les échantillons physiques suivis (un par variante d'une campagne)."""
    return assert_ok(_put(client, slug, ref, "entities", {"entities": entities}, if_match))


def replace_structure_images(client: Any, slug: str, ref: str, images: list[dict], *, if_match: str | None = None) -> dict:
    return assert_ok(_put(client, slug, ref, "structure-images", {"images": images}, if_match))


def combine_body(
    first: str | dict, second: str | dict, *, title: str = "Combinée", intent: str = "Réunir", entities: list[dict] | None = None, **fields: Any
) -> dict:
    """Le corps d'une combinaison : deux études (une piste, ou ``{experiment_id, version_id}``), et ce
    qu'un lancement demande - une nouvelle plaque, W9 sauf mention contraire."""
    sources = [{"experiment_id": source} if isinstance(source, str) else source for source in (first, second)]
    return {"merge_of": sources, "title": title, "intent": intent, "entities": [{"sample_id": "W9"}] if entities is None else entities, **fields}


def post_combine(client: Any, slug: str, first: str | dict, second: str | dict, **fields: Any) -> Any:
    """POST /experiments avec ``merge_of``, tel quel (la réponse, pour en vérifier un refus)."""
    return client.post(experiments_url(slug), json=combine_body(first, second, **fields))


def combine(client: Any, slug: str, first: str | dict, second: str | dict, **fields: Any) -> dict:
    """Combine deux études en une nouvelle (voir :func:`combine_body`) - renvoie la nouvelle étude."""
    return assert_created(post_combine(client, slug, first, second, **fields))


def post_from_wafers(
    client: Any, slug: str, origin_slug: str, origin_ref: str, wafers: list[str | dict], *, version_id: str | None = None, **fields: Any
) -> Any:
    """POST /experiments avec ``wafer_origin`` (l'étude ``origin_ref`` du µprojet ``origin_slug``)
    et ses plaques ``wafers`` (des lasermarks, ou des entités entières) comme ``entities`` - le
    procédé par défaut des tests sauf mention contraire. La réponse, telle quelle."""
    origin = {"microproject": origin_slug, "experiment_id": origin_ref, **({"version_id": version_id} if version_id else {})}
    entities = [{"sample_id": wafer} if isinstance(wafer, str) else wafer for wafer in wafers]
    fields = {"title": "Suite des plaques", "intent": "Continuer", **fields}
    return client.post(experiments_url(slug), json={**launch_body(entities=entities, **fields), "wafer_origin": origin})


def from_wafers(client: Any, slug: str, origin_slug: str, origin_ref: str, wafers: list[str | dict], **fields: Any) -> dict:
    """Une nouvelle étude partie de plaques existantes (voir :func:`post_from_wafers`)."""
    return assert_created(post_from_wafers(client, slug, origin_slug, origin_ref, wafers, **fields))


def delete_experiment(client: Any, slug: str, ref: str, *, if_match: str | None = None) -> Any:
    """DELETE, tel quel (la réponse : 204, ou le refus)."""
    return client.delete(experiment_url(slug, ref), headers=_headers(if_match))


def get_process(client: Any, slug: str, ref: str, version: str | None = None, *, variant: int | None = None) -> Any:
    """GET /process, tel quel (la réponse) - ``variant`` : le procédé d'une variante d'une campagne."""
    params = {key: value for key, value in (("version", version), ("variant", variant)) if value is not None}
    return client.get(f"{experiment_url(slug, ref)}/process", params=params)


def process(client: Any, slug: str, ref: str, version: str | None = None, *, variant: int | None = None) -> dict:
    return assert_ok(get_process(client, slug, ref, version, variant=variant))


def step_ids(client: Any, slug: str, ref: str, version: str | None = None) -> list[str]:
    """GET /process : l'id de chaque étape du procédé, dans l'ordre."""
    return [step["id"] for step in process(client, slug, ref, version)["steps"]]


def structure_diff(client: Any, slug: str, ref: str, **params: Any) -> dict:
    """GET /structure-diff - ``version``, ``against_version``, ``against_experiment``, ``against_microproject``."""
    return assert_ok(client.get(f"{experiment_url(slug, ref)}/structure-diff", params=params))


def variants(client: Any, slug: str, ref: str) -> dict:
    return assert_ok(client.get(f"{experiment_url(slug, ref)}/variants"))


def list_experiments(client: Any, slug: str, **params: Any) -> dict:
    """GET /experiments (``status``, ``q``, ``offset``, ``limit``) - ``{items, total}``."""
    return assert_ok(client.get(experiments_url(slug), params=params))


def refs(client: Any, slug: str) -> dict:
    """GET /refs - ``{refs, edges}``."""
    return assert_ok(client.get(f"/api/microprojects/{slug}/refs"))


def create_ref(client: Any, slug: str, ref: str, name: str | None = None, *, version_id: str | None = None) -> dict:
    """POST /refs : marque la pointe de la piste (ou ``version_id``) comme ref (``name`` : un
    surnom, sinon « ref vX.Y.Z »)."""
    body = {"experiment_id": ref, **({"name": name} if name is not None else {}), **({"version_id": version_id} if version_id else {})}
    return assert_created(client.post(f"/api/microprojects/{slug}/refs", json=body))


def ref_url(slug: str, name: str) -> str:
    return f"/api/microprojects/{slug}/refs/{quote(name, safe='')}"


def get_ref(client: Any, slug: str, name: str) -> dict:
    """GET /refs/{ref_name} - la ref (``name``) et sa version."""
    return assert_ok(client.get(ref_url(slug, name)))


def patch_ref(client: Any, slug: str, name: str, new_name: str | None) -> Any:
    """PATCH /refs/{ref_name} ``{name}``, tel quel (la réponse, pour en vérifier un refus)."""
    return client.patch(ref_url(slug, name), json={"name": new_name})


def rename_ref(client: Any, slug: str, name: str, new_name: str) -> dict:
    return assert_ok(patch_ref(client, slug, name, new_name))


def delete_ref(client: Any, slug: str, name: str) -> Any:
    """DELETE /refs/{ref_name}, tel quel (204, ou le refus)."""
    return client.delete(ref_url(slug, name))


def structure_history(client: Any, slug: str, *, all_versions: bool | None = None) -> dict:
    """GET /structure-history (``all_versions``) - ``{lanes, nodes, edges}``."""
    params = {} if all_versions is None else {"all_versions": str(all_versions).lower()}
    return assert_ok(client.get(f"/api/microprojects/{slug}/structure-history", params=params))


def experiment_stats(client: Any, **filters: Any) -> list[dict]:
    """GET /api/experiment-stats (``area``, ``microproject``) - une ligne par µprojet."""
    return assert_ok(client.get("/api/experiment-stats", params=filters))


def experiment_timeline(client: Any, **filters: Any) -> list[dict]:
    """GET /api/experiment-timeline (``area``, ``thematic``) - la frise, une ligne par µprojet."""
    return assert_ok(client.get("/api/experiment-timeline", params=filters))


def write_old_merge(slug: str, line: str, other: str) -> str:
    """Une fusion telle que l'ancien code l'écrivait (avant qu'une combinaison crée une nouvelle
    piste) : une version de ``line`` à deux parents, sa pointe et celle de ``other`` - hors de
    Spectre, avec Follow seul. Renvoie l'id de la version."""
    import follow

    from spectre.plugins.experiments import repository

    outside = follow.Repository(repository.follow_repo_path(slug))
    tip = outside.get(outside.branches[line])
    builder = outside.merge(tip.id, outside.branches[other], branch=line, title=tip.title, intent=tip.intent, hypothesis=tip.hypothesis, author="Ada")
    builder.metadata = dict(tip.metadata)
    return builder.commit().id
