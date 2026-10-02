"""Cross-microproject links (spectre.plugins.links): linking two microprojects, or two
physical entities tracked on (possibly different) microprojects' experiences - the one relationship
allowed to reach across Follow repositories, since Follow itself refuses a same-repository-only
ReferenceLink pointed at another microproject. See docs-architecture.html for why this needed its own
mechanism rather than reusing Follow's.
"""

from __future__ import annotations

from support.accounts import login, signup
from support.experiments import launch, track_entities
from support.microprojects import create_microproject, join_as, signup_with_microproject


def _link(client, slug_a, slug_b, **fields):
    return client.post("/api/liens-projets", json={"microproject_a": slug_a, "microproject_b": slug_b, **fields})


def test_editor_on_both_microprojects_can_link_them(client):
    slug_a = signup_with_microproject(client, "linker@example.com", "Projet A")
    slug_b = create_microproject(client, "Projet B")["slug"]

    created = _link(client, slug_a, slug_b, note="Même famille de matériaux")
    assert created.status_code == 201
    assert created.json()["note"] == "Même famille de matériaux"

    atlas = client.get("/api/atlas?theme=non-classe").json()
    assert len(atlas["microproject_links"]) == 1
    assert atlas["microproject_links"][0]["note"] == "Même famille de matériaux"


def test_cannot_link_a_microproject_to_itself(client):
    slug = signup_with_microproject(client, "selflink@example.com")
    assert _link(client, slug, slug).status_code == 422


def test_cannot_link_two_microprojects_twice(client):
    slug_a = signup_with_microproject(client, "twice@example.com", "Projet A")
    slug_b = create_microproject(client, "Projet B")["slug"]
    _link(client, slug_a, slug_b)
    assert _link(client, slug_b, slug_a).status_code == 422


def test_viewer_cannot_link_a_microproject_they_only_view(client):
    owner_slug = signup_with_microproject(client, "owner-links@example.com", "Chez le propriétaire")
    join_as(client, owner_slug, "viewer-links@example.com", owner="owner-links@example.com", role="viewer")

    own_slug = create_microproject(client, "Chez le viewer")["slug"]
    assert client.get(f"/api/microprojets/{owner_slug}").json()["role"] == "viewer"
    assert _link(client, own_slug, owner_slug).status_code == 403


def test_microproject_link_only_appears_in_atlas_for_members_of_both_sides(client):
    slug_a = signup_with_microproject(client, "visibility-a@example.com", "Projet A")
    slug_b = create_microproject(client, "Projet B")["slug"]
    _link(client, slug_a, slug_b)

    # a third user, unrelated to either microproject, sees neither the microprojects nor the link
    signup_with_microproject(client, "visibility-c@example.com", "Projet C")
    atlas = client.get("/api/atlas?theme=non-classe").json()
    assert atlas["microproject_links"] == []


def test_editor_on_both_microprojects_can_link_two_physical_entities(client):
    slug_a = signup_with_microproject(client, "entity-link-a@example.com", "Projet A")
    exp_a = launch(client, slug_a, title="Etude A", intent="Depart", entities=[{"sample_id": "placeholder"}])
    track_entities(client, slug_a, exp_a["id"], [{"sample_id": "W-A1", "location": "Salle blanche"}])

    slug_b = create_microproject(client, "Projet B")["slug"]
    exp_b = launch(client, slug_b, title="Etude B", intent="Depart", entities=[{"sample_id": "placeholder"}])
    track_entities(client, slug_b, exp_b["id"], [{"sample_id": "W-B1", "location": "Salle blanche"}])

    created = client.post(
        "/api/liens-entites",
        json={
            "a": {"microproject_slug": slug_a, "experience_id": exp_a["id"], "entity_index": 0},
            "b": {"microproject_slug": slug_b, "experience_id": exp_b["id"], "entity_index": 0},
            "note": "Même lot de substrat",
        },
    )
    assert created.status_code == 201

    atlas = client.get("/api/atlas?theme=non-classe").json()
    assert len(atlas["entity_links"]) == 1
    link = atlas["entity_links"][0]
    assert link["a"]["microproject_slug"] == slug_a
    assert link["b"]["microproject_slug"] == slug_b
    assert link["note"] == "Même lot de substrat"


def test_delete_microproject_link_requires_editor_on_at_least_one_side(client):
    slug_a = signup_with_microproject(client, "delete-links-a@example.com", "Projet A")
    slug_b = create_microproject(client, "Projet B")["slug"]
    link_id = _link(client, slug_a, slug_b).json()["id"]

    # an unrelated user cannot delete it
    signup(client, "delete-links-stranger@example.com", name="S")
    assert client.delete(f"/api/liens-projets/{link_id}").status_code == 403

    # but the original creator (editor on both) can
    login(client, "delete-links-a@example.com")
    assert client.delete(f"/api/liens-projets/{link_id}").status_code == 200

    atlas = client.get("/api/atlas?theme=non-classe").json()
    assert atlas["microproject_links"] == []
