"""Tech bricks (``/api/tech-bricks``): a named, reusable sequence of process steps, with no
substrate of its own - the "sequence" analog of a single-step StepPreset, the same way a
SavedStructure is the "sequence + substrate" one. See spectre.plugins.process_library.tech_bricks
for the module docstring explaining the "point of departure, not a live link" philosophy this
mirrors from the structure library and step presets.
"""

from __future__ import annotations

from support.microprojects import create_microproject, join_as, signup_with_microproject
from support.process_library import create_item, delete_item, list_items, names, tech_brick, update_item


def test_create_a_microproject_scoped_tech_brick(client):
    slug = signup_with_microproject(client, "brickA@example.com")

    created = create_item(client, "tech-bricks", tech_brick("Masque + gravure RIE"), microproject=slug)
    assert len(created["steps"]) == 1
    assert created["steps"][0]["material"] == "GaN"
    listed = list_items(client, "tech-bricks", microproject=slug)
    assert names(listed, "microproject") == ["Masque + gravure RIE"]
    assert names(listed, "shared") == []


def test_shared_tech_brick_is_visible_from_a_different_microproject(client):
    signup_with_microproject(client, "brickB@example.com")
    create_item(client, "tech-bricks", tech_brick("Brique commune"), scope="shared")

    slug_b = create_microproject(client, "Autre projet")["slug"]
    listed = list_items(client, "tech-bricks", microproject=slug_b)
    assert names(listed, "shared") == ["Brique commune"]
    assert names(listed, "microproject") == []


def test_duplicate_name_in_the_same_library_is_rejected(client):
    slug = signup_with_microproject(client, "brickC@example.com")
    create_item(client, "tech-bricks", tech_brick("Brique X"), microproject=slug)
    again = client.post("/api/tech-bricks", json={**tech_brick("Brique X"), "scope": "microproject", "microproject": slug})
    assert again.status_code == 409


def test_rename_a_tech_brick_in_place(client):
    slug = signup_with_microproject(client, "brickD@example.com")
    brick = create_item(client, "tech-bricks", tech_brick("Nom initial"), microproject=slug)

    update_item(client, "tech-bricks", brick["id"], name="Nom corrige")
    assert names(list_items(client, "tech-bricks", microproject=slug), "microproject") == ["Nom corrige"]


def test_delete_a_tech_brick(client):
    slug = signup_with_microproject(client, "brickE@example.com")
    brick = create_item(client, "tech-bricks", tech_brick("A retirer"), microproject=slug)

    delete_item(client, "tech-bricks", brick["id"])
    assert names(list_items(client, "tech-bricks", microproject=slug), "microproject") == []


def test_a_tech_brick_needs_no_substrate_unlike_a_saved_structure(client):
    """The whole point of a brick vs. a saved structure: it's just a sequence of steps, with
    nothing substrate-shaped in its request/response shape at all."""
    slug = signup_with_microproject(client, "brickF@example.com")
    created = create_item(client, "tech-bricks", tech_brick("Sans substrat"), microproject=slug)
    assert "substrate" not in created


def test_viewer_cannot_create_a_tech_brick(client):
    slug = signup_with_microproject(client, "brickG-owner@example.com")
    join_as(client, slug, "brickG-viewer@example.com", owner="brickG-owner@example.com", role="viewer")
    denied = client.post("/api/tech-bricks", json={**tech_brick("Interdit"), "scope": "microproject", "microproject": slug})
    assert denied.status_code == 403


def test_a_tech_brick_keeps_its_declared_parameters(client):
    slug = signup_with_microproject(client, "brickDeclared@example.com")
    declared = {"0": [{"name": "dopage", "value": 3e18, "obtention": {}}]}
    created = create_item(client, "tech-bricks", tech_brick("PGaN dope", declared_params=declared), microproject=slug)
    assert created["declared_params"] == declared
