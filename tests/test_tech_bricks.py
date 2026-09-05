"""Tech bricks (spectre.api.structures's briques-technologiques routes): a named, reusable
sequence of process steps, with no substrate of its own - the "sequence" analog of a single-step
StepPreset, the same way a SavedStructure is the "sequence + substrate" one. See
spectre.core.tech_bricks for the module docstring explaining the "point of departure, not a live
link" philosophy this mirrors from the structure library and step presets.
"""

from __future__ import annotations


def _steps():
    return [
        {
            "kind": "deposition",
            "name": "PGaN",
            "material": "GaN",
            "recipe": "CVD Conformal",
            "thickness": {"value": 50, "unit": "nm"},
        }
    ]


def _register_and_project(client, email, project_name="Projet"):
    client.post("/api/auth/register", json={"email": email, "password": "supersecret", "name": "T"})
    return client.post("/api/projects", json={"name": project_name}).json()["slug"]


def test_create_a_project_scoped_tech_brick(client):
    slug = _register_and_project(client, "brickA@example.com")

    created = client.post(
        f"/api/projects/{slug}/briques-technologiques",
        json={"name": "Masque + gravure RIE", "steps": _steps(), "partagee": False},
    )
    assert created.status_code == 201
    body = created.json()
    assert [b["name"] for b in body["projet"]] == ["Masque + gravure RIE"]
    assert body["partagees"] == []
    assert len(body["projet"][0]["steps"]) == 1
    assert body["projet"][0]["steps"][0]["material"] == "GaN"


def test_shared_tech_brick_is_visible_from_a_different_project(client):
    slug_a = _register_and_project(client, "brickB@example.com")
    client.post(
        f"/api/projects/{slug_a}/briques-technologiques",
        json={"name": "Brique commune", "steps": _steps(), "partagee": True},
    )

    slug_b = client.post("/api/projects", json={"name": "Autre projet"}).json()["slug"]
    listed = client.get(f"/api/projects/{slug_b}/briques-technologiques").json()
    assert [b["name"] for b in listed["partagees"]] == ["Brique commune"]
    assert listed["projet"] == []


def test_duplicate_name_in_the_same_library_is_rejected(client):
    slug = _register_and_project(client, "brickC@example.com")
    payload = {"name": "Brique X", "steps": _steps(), "partagee": False}
    first = client.post(f"/api/projects/{slug}/briques-technologiques", json=payload)
    assert first.status_code == 201
    again = client.post(f"/api/projects/{slug}/briques-technologiques", json=payload)
    assert again.status_code == 409


def test_rename_a_tech_brick_in_place(client):
    slug = _register_and_project(client, "brickD@example.com")
    client.post(
        f"/api/projects/{slug}/briques-technologiques",
        json={"name": "Nom initial", "steps": _steps(), "partagee": False},
    )
    renamed = client.put(
        f"/api/projects/{slug}/briques-technologiques/Nom initial",
        params={"partagee": False},
        json={"name": "Nom corrige", "steps": _steps()},
    )
    assert renamed.status_code == 200
    names = [b["name"] for b in renamed.json()["projet"]]
    assert names == ["Nom corrige"]


def test_delete_a_tech_brick(client):
    slug = _register_and_project(client, "brickE@example.com")
    client.post(
        f"/api/projects/{slug}/briques-technologiques",
        json={"name": "A retirer", "steps": _steps(), "partagee": False},
    )
    deleted = client.delete(f"/api/projects/{slug}/briques-technologiques/A retirer", params={"partagee": False})
    assert deleted.status_code == 200
    assert deleted.json()["projet"] == []


def test_a_tech_brick_needs_no_substrate_unlike_a_saved_structure(client):
    """The whole point of a brick vs. a saved structure: it's just a sequence of steps, with
    nothing substrate-shaped in its request/response shape at all."""
    slug = _register_and_project(client, "brickF@example.com")
    created = client.post(
        f"/api/projects/{slug}/briques-technologiques",
        json={"name": "Sans substrat", "steps": _steps(), "partagee": False},
    )
    assert created.status_code == 201
    assert "substrate" not in created.json()["projet"][0]


def test_viewer_cannot_create_a_tech_brick(client):
    slug = _register_and_project(client, "brickG-owner@example.com")
    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={"email": "brickG-viewer@example.com", "password": "supersecret", "name": "V"})
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "brickG-owner@example.com", "password": "supersecret"})
    client.post(f"/api/projects/{slug}/members", json={"email": "brickG-viewer@example.com", "role": "viewer"})

    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "brickG-viewer@example.com", "password": "supersecret"})
    denied = client.post(
        f"/api/projects/{slug}/briques-technologiques",
        json={"name": "Interdit", "steps": _steps(), "partagee": False},
    )
    assert denied.status_code == 403
