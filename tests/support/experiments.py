"""Expériences (plugin experiments) : lancer, faire évoluer, conclure... Chaque aide encapsule une
route actuelle et vérifie son code de succès ; ``fields`` complète ou remplace le corps envoyé."""

from __future__ import annotations

from typing import Any

from .http import PNG_1PX, assert_created, assert_ok
from .attachments import upload_file
from .structures import campaign_plan, steps, substrate


def _experiences(slug: str) -> str:
    return f"/api/microprojets/{slug}/experiences"


def launch_body(*, title: str = "Essai", intent: str = "Verifier", entities: list[dict] | None = None, **fields: Any) -> dict:
    """Le corps d'un lancement : une couche d'oxyde sur Si, suivie sur le wafer W1, sauf mention
    contraire."""
    return {
        "substrate": substrate(),
        "steps": steps(),
        "title": title,
        "intent": intent,
        "entities": [{"sample_id": "W1"}] if entities is None else entities,
        **fields,
    }


def launch(client: Any, slug: str, **fields: Any) -> dict:
    """POST /experiences (voir :func:`launch_body`) - renvoie ``{id, branch}``."""
    return assert_created(client.post(_experiences(slug), json=launch_body(**fields)))


def launch_campaign(client: Any, slug: str, plan: dict | None = None, **fields: Any) -> dict:
    """POST /experiences/campagne - par défaut trois épaisseurs d'oxyde (10, 20, 30 nm)."""
    fields = {"title": "Campagne", "intent": "Balayer l'epaisseur", **fields}
    body = launch_body(plan=plan or campaign_plan([10, 20, 30]), **fields)
    return assert_created(client.post(f"{_experiences(slug)}/campagne", json=body))


def launch_image(client: Any, slug: str, images: list[dict], **fields: Any) -> dict:
    """POST /experiences/image : une structure donnée en images (``{image_id, kind, caption}``)."""
    body = {"images": images, "title": "Coupe", "intent": "Documenter", "entities": [{"sample_id": "W1"}], **fields}
    return assert_created(client.post(f"{_experiences(slug)}/image", json=body))


def get_experience(client: Any, slug: str, ref: str) -> dict:
    return assert_ok(client.get(f"{_experiences(slug)}/{ref}"))


def timeline(client: Any, slug: str, ref: str) -> dict:
    return assert_ok(client.get(f"{_experiences(slug)}/{ref}/timeline"))


def lineage(client: Any, slug: str) -> dict:
    """Le graphe de filiation du µprojet (``{nodes, edges}``)."""
    return assert_ok(client.get(f"/api/microprojets/{slug}/filiation"))


def evolve(client: Any, slug: str, ref: str, *, title: str = "Essai", intent: str = "Suite", **fields: Any) -> dict:
    """POST /evoluer - par défaut le même procédé ; ``steps=...`` pour le changer."""
    body = {"substrate": substrate(), "steps": steps(), "title": title, "intent": intent, **fields}
    return assert_created(client.post(f"{_experiences(slug)}/{ref}/evoluer", json=body))


def evolve_image(client: Any, slug: str, ref: str, images: list[dict], *, title: str = "Coupe", intent: str = "Suite", **fields: Any) -> dict:
    body = {"images": images, "title": title, "intent": intent, **fields}
    return assert_created(client.post(f"{_experiences(slug)}/{ref}/evoluer-image", json=body))


def conclude(client: Any, slug: str, ref: str, status: str = "concluded", **fields: Any) -> dict:
    """POST /conclure - ``fields`` : ``decision``, ``summary``, ``objective_results``..."""
    return assert_created(client.post(f"{_experiences(slug)}/{ref}/conclure", json={"status": status, **fields}))


def set_status(client: Any, slug: str, ref: str, status: str, **fields: Any) -> dict:
    """POST /statut (brouillon, en cours, en pause) - ``reason`` pour une pause."""
    return assert_created(client.post(f"{_experiences(slug)}/{ref}/statut", json={"status": status, **fields}))


def tag(client: Any, slug: str, ref: str, tags: list[str]) -> dict:
    return assert_created(client.post(f"{_experiences(slug)}/{ref}/etiquettes", json={"tags": tags}))


def track_entities(client: Any, slug: str, ref: str, entities: list[dict]) -> dict:
    """POST /entites : les échantillons physiques suivis (un par variante d'une campagne)."""
    return assert_created(client.post(f"{_experiences(slug)}/{ref}/entites", json={"entities": entities}))


def add_evidence(client: Any, slug: str, ref: str, description: str = "Mesure", **fields: Any) -> dict:
    """POST /preuves - renvoie ``{id, evidence_id}``."""
    body = {"description": description, "source": "labo", **fields}
    return assert_created(client.post(f"{_experiences(slug)}/{ref}/preuves", json=body))


def combine(client: Any, slug: str, ref: str, other_id: str, *, title: str = "Fusion", intent: str = "Reunir") -> dict:
    body = {"other_id": other_id, "title": title, "intent": intent}
    return assert_created(client.post(f"{_experiences(slug)}/{ref}/combiner", json=body))


def create_ref(client: Any, slug: str, ref: str, name: str | None = None) -> dict:
    """POST /ref : marque la version comme ref (``name`` : un surnom, sinon « ref vX.Y.Z »)."""
    body = {} if name is None else {"name": name}
    return assert_created(client.post(f"{_experiences(slug)}/{ref}/ref", json=body))


def upload_attachment(client: Any, slug: str, ref: str, filename: str = "mesure.png", content: bytes = PNG_1PX, content_type: str = "image/png", **form: Any) -> dict:
    """POST /pieces-jointes - ``form`` : ``entity_index``, ``evidence_id``. Renvoie ``{id, attachment}``."""
    response = client.post(f"{_experiences(slug)}/{ref}/pieces-jointes", data=form, files={"file": (filename, content, content_type)})
    return assert_created(response)


def upload_image(client: Any, slug: str, name: str = "mesure.png") -> str:
    """Une image collée dans le formulaire de preuve (POST .../attachments, purpose=evidence) - renvoie son id."""
    return upload_file(client, slug, "evidence", name)["id"]
