"""Cross-microproject links (spectre.core.links / spectre.api.links): linking two microprojects, or two
physical entities tracked on (possibly different) microprojects' experiences - the one relationship
allowed to reach across Follow repositories, since Follow itself refuses a same-repository-only
ReferenceLink pointed at another microproject. See docs-architecture.html for why this needed its own
mechanism rather than reusing Follow's.
"""

from __future__ import annotations


def _substrate():
    return {"material": "Si", "domain_width": {"value": 200, "unit": "nm"}, "thickness": {"value": 50, "unit": "nm"}}


def _steps(thickness=20):
    return [
        {"kind": "deposition", "name": "Oxyde", "material": "SiO2", "recipe": "CVD Conformal", "thickness": {"value": thickness, "unit": "nm"}}
    ]


def _register_and_microproject(client, email, microproject_name="Projet"):
    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={"email": email, "password": "supersecret", "name": "T"})
    return client.post("/api/microprojets", json={"name": microproject_name}).json()["slug"]


def test_editor_on_both_microprojects_can_link_them(client):
    slug_a = _register_and_microproject(client, "linker@example.com", "Projet A")
    slug_b = client.post("/api/microprojets", json={"name": "Projet B"}).json()["slug"]

    created = client.post("/api/liens-projets", json={"microproject_a": slug_a, "microproject_b": slug_b, "note": "Même famille de matériaux"})
    assert created.status_code == 201
    body = created.json()
    assert body["note"] == "Même famille de matériaux"

    atlas = client.get("/api/atlas").json()
    assert len(atlas["microproject_links"]) == 1
    assert atlas["microproject_links"][0]["note"] == "Même famille de matériaux"


def test_cannot_link_a_microproject_to_itself(client):
    slug = _register_and_microproject(client, "selflink@example.com")
    response = client.post("/api/liens-projets", json={"microproject_a": slug, "microproject_b": slug})
    assert response.status_code == 422


def test_cannot_link_two_microprojects_twice(client):
    slug_a = _register_and_microproject(client, "twice@example.com", "Projet A")
    slug_b = client.post("/api/microprojets", json={"name": "Projet B"}).json()["slug"]
    client.post("/api/liens-projets", json={"microproject_a": slug_a, "microproject_b": slug_b})
    duplicate = client.post("/api/liens-projets", json={"microproject_a": slug_b, "microproject_b": slug_a})
    assert duplicate.status_code == 422


def test_viewer_cannot_link_a_microproject_they_only_view(client):
    owner_slug = _register_and_microproject(client, "owner-links@example.com", "Chez le propriétaire")
    client.post("/api/microprojets/{}/members".format(owner_slug), json={"email": "viewer-links@example.com", "role": "viewer"})

    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={"email": "viewer-links@example.com", "password": "supersecret", "name": "V"})
    own_slug = client.post("/api/microprojets", json={"name": "Chez le viewer"}).json()["slug"]

    response = client.post("/api/liens-projets", json={"microproject_a": own_slug, "microproject_b": owner_slug})
    assert response.status_code == 403


def test_microproject_link_only_appears_in_atlas_for_members_of_both_sides(client):
    slug_a = _register_and_microproject(client, "visibility-a@example.com", "Projet A")
    slug_b = client.post("/api/microprojets", json={"name": "Projet B"}).json()["slug"]
    client.post("/api/liens-projets", json={"microproject_a": slug_a, "microproject_b": slug_b})

    # a third user, unrelated to either microproject, sees neither the microprojects nor the link
    _register_and_microproject(client, "visibility-c@example.com", "Projet C")
    atlas = client.get("/api/atlas").json()
    assert atlas["microproject_links"] == []


def test_editor_on_both_microprojects_can_link_two_physical_entities(client):
    slug_a = _register_and_microproject(client, "entity-link-a@example.com", "Projet A")
    exp_a = client.post(
        f"/api/microprojets/{slug_a}/experiences",
        json={
            "substrate": _substrate(),
            "steps": _steps(),
            "title": "Etude A",
            "intent": "Depart",
            "entities": [{"sample_id": "placeholder"}],
        },
    ).json()
    client.post(f"/api/microprojets/{slug_a}/experiences/{exp_a['id']}/entites", json={"entities": [{"sample_id": "W-A1", "location": "Salle blanche"}]})

    slug_b = client.post("/api/microprojets", json={"name": "Projet B"}).json()["slug"]
    exp_b = client.post(
        f"/api/microprojets/{slug_b}/experiences",
        json={
            "substrate": _substrate(),
            "steps": _steps(),
            "title": "Etude B",
            "intent": "Depart",
            "entities": [{"sample_id": "placeholder"}],
        },
    ).json()
    client.post(f"/api/microprojets/{slug_b}/experiences/{exp_b['id']}/entites", json={"entities": [{"sample_id": "W-B1", "location": "Salle blanche"}]})

    created = client.post(
        "/api/liens-entites",
        json={
            "a": {"microproject_slug": slug_a, "experience_id": exp_a["id"], "entity_index": 0},
            "b": {"microproject_slug": slug_b, "experience_id": exp_b["id"], "entity_index": 0},
            "note": "Même lot de substrat",
        },
    )
    assert created.status_code == 201

    atlas = client.get("/api/atlas").json()
    assert len(atlas["entity_links"]) == 1
    link = atlas["entity_links"][0]
    assert link["a"]["microproject_slug"] == slug_a
    assert link["b"]["microproject_slug"] == slug_b
    assert link["note"] == "Même lot de substrat"


def test_delete_microproject_link_requires_editor_on_at_least_one_side(client):
    slug_a = _register_and_microproject(client, "delete-links-a@example.com", "Projet A")
    slug_b = client.post("/api/microprojets", json={"name": "Projet B"}).json()["slug"]
    link_id = client.post("/api/liens-projets", json={"microproject_a": slug_a, "microproject_b": slug_b}).json()["id"]

    # an unrelated user cannot delete it
    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={"email": "delete-links-stranger@example.com", "password": "supersecret", "name": "S"})
    forbidden = client.delete(f"/api/liens-projets/{link_id}")
    assert forbidden.status_code == 403

    # but the original creator (editor on both) can
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "delete-links-a@example.com", "password": "supersecret"})
    ok = client.delete(f"/api/liens-projets/{link_id}")
    assert ok.status_code == 200

    atlas = client.get("/api/atlas").json()
    assert atlas["microproject_links"] == []
