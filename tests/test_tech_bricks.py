"""Tech bricks (spectre.api.structures's briques-technologiques routes): a named, reusable
sequence of process steps, with no substrate of its own - the "sequence" analog of a single-step
StepPreset, the same way a SavedStructure is the "sequence + substrate" one. See
spectre.core.tech_bricks for the module docstring explaining the "point of departure, not a live
link" philosophy this mirrors from the structure library and step presets.
"""

from __future__ import annotations

from support.microprojects import create_microproject, join_as, signup_with_microproject
from support.structures import deposition


PGAN_STEPS = [deposition("PGaN", "GaN", thickness_nm=50)]


def test_create_a_microproject_scoped_tech_brick(client):
    slug = signup_with_microproject(client, "brickA@example.com")

    created = client.post(
        f"/api/microprojets/{slug}/briques-technologiques",
        json={"name": "Masque + gravure RIE", "steps": PGAN_STEPS, "partagee": False},
    )
    assert created.status_code == 201
    body = created.json()
    assert [b["name"] for b in body["microprojet"]] == ["Masque + gravure RIE"]
    assert body["partagees"] == []
    assert len(body["microprojet"][0]["steps"]) == 1
    assert body["microprojet"][0]["steps"][0]["material"] == "GaN"


def test_shared_tech_brick_is_visible_from_a_different_microproject(client):
    slug_a = signup_with_microproject(client, "brickB@example.com")
    client.post(
        f"/api/microprojets/{slug_a}/briques-technologiques",
        json={"name": "Brique commune", "steps": PGAN_STEPS, "partagee": True},
    )

    slug_b = create_microproject(client, "Autre projet")["slug"]
    listed = client.get(f"/api/microprojets/{slug_b}/briques-technologiques").json()
    assert [b["name"] for b in listed["partagees"]] == ["Brique commune"]
    assert listed["microprojet"] == []


def test_duplicate_name_in_the_same_library_is_rejected(client):
    slug = signup_with_microproject(client, "brickC@example.com")
    payload = {"name": "Brique X", "steps": PGAN_STEPS, "partagee": False}
    first = client.post(f"/api/microprojets/{slug}/briques-technologiques", json=payload)
    assert first.status_code == 201
    again = client.post(f"/api/microprojets/{slug}/briques-technologiques", json=payload)
    assert again.status_code == 409


def test_rename_a_tech_brick_in_place(client):
    slug = signup_with_microproject(client, "brickD@example.com")
    client.post(
        f"/api/microprojets/{slug}/briques-technologiques",
        json={"name": "Nom initial", "steps": PGAN_STEPS, "partagee": False},
    )
    renamed = client.put(
        f"/api/microprojets/{slug}/briques-technologiques/Nom initial",
        params={"partagee": False},
        json={"name": "Nom corrige", "steps": PGAN_STEPS},
    )
    assert renamed.status_code == 200
    names = [b["name"] for b in renamed.json()["microprojet"]]
    assert names == ["Nom corrige"]


def test_delete_a_tech_brick(client):
    slug = signup_with_microproject(client, "brickE@example.com")
    client.post(
        f"/api/microprojets/{slug}/briques-technologiques",
        json={"name": "A retirer", "steps": PGAN_STEPS, "partagee": False},
    )
    deleted = client.delete(f"/api/microprojets/{slug}/briques-technologiques/A retirer", params={"partagee": False})
    assert deleted.status_code == 200
    assert deleted.json()["microprojet"] == []


def test_a_tech_brick_needs_no_substrate_unlike_a_saved_structure(client):
    """The whole point of a brick vs. a saved structure: it's just a sequence of steps, with
    nothing substrate-shaped in its request/response shape at all."""
    slug = signup_with_microproject(client, "brickF@example.com")
    created = client.post(
        f"/api/microprojets/{slug}/briques-technologiques",
        json={"name": "Sans substrat", "steps": PGAN_STEPS, "partagee": False},
    )
    assert created.status_code == 201
    assert "substrate" not in created.json()["microprojet"][0]


def test_viewer_cannot_create_a_tech_brick(client):
    slug = signup_with_microproject(client, "brickG-owner@example.com")
    join_as(client, slug, "brickG-viewer@example.com", owner="brickG-owner@example.com", role="viewer")
    denied = client.post(
        f"/api/microprojets/{slug}/briques-technologiques",
        json={"name": "Interdit", "steps": PGAN_STEPS, "partagee": False},
    )
    assert denied.status_code == 403


def test_a_tech_brick_keeps_its_declared_parameters(client):
    slug = signup_with_microproject(client, "brickDeclared@example.com")
    declared = {"0": [{"name": "dopage", "value": 3e18, "obtention": {}}]}
    body = client.post(
        f"/api/microprojets/{slug}/briques-technologiques",
        json={"name": "PGaN dope", "steps": PGAN_STEPS, "declared_params": declared},
    ).json()
    assert body["microprojet"][0]["declared_params"] == declared
