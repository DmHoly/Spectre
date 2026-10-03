from __future__ import annotations

from support.microprojects import create_microproject, join_as, signup_with_microproject
from support.process_library import PGAN_STEPS, by_name, create_item, delete_item, list_items, names, saved_structure, update_item
from support.structures import substrate


def test_create_a_microproject_scoped_structure(client):
    slug = signup_with_microproject(client, "libA@example.com")

    created = create_item(client, "saved-structures", saved_structure("Epitaxie PGaN"), microproject=slug)
    assert created["scope"] == "microproject"
    listed = list_items(client, "saved-structures", microproject=slug)
    assert names(listed, "microproject") == ["Epitaxie PGaN"]
    assert names(listed, "shared") == []


def test_shared_structure_is_visible_from_a_different_microproject(client):
    signup_with_microproject(client, "libB@example.com")
    create_item(client, "saved-structures", saved_structure("Base commune"), scope="shared")

    slug_b = create_microproject(client, "Autre projet")["slug"]
    listed = list_items(client, "saved-structures", microproject=slug_b)
    assert names(listed, "shared") == ["Base commune"]
    assert names(listed, "microproject") == []


def test_derive_a_structure_keeps_a_derived_from_link(client):
    slug = signup_with_microproject(client, "libC@example.com")
    create_item(client, "saved-structures", saved_structure("Epitaxie"), microproject=slug)

    derived_steps = PGAN_STEPS + [
        {"kind": "deposition", "name": "Contact", "material": "Au", "recipe": "Evaporation (normal)", "thickness": {"value": 80, "unit": "nm"}}
    ]
    saved = create_item(
        client, "saved-structures", saved_structure("Epitaxie + contact", steps=derived_steps, derived_from="Epitaxie"), microproject=slug
    )
    assert saved["derived_from"] == "Epitaxie"
    assert len(saved["steps"]) == 2


def test_duplicate_name_in_the_same_library_is_rejected(client):
    slug = signup_with_microproject(client, "libD@example.com")
    create_item(client, "saved-structures", saved_structure("Structure X"), microproject=slug)
    again = client.post("/api/saved-structures", json={**saved_structure("Structure X"), "scope": "microproject", "microproject": slug})
    assert again.status_code == 409


def test_rename_a_saved_structure_in_place(client):
    slug = signup_with_microproject(client, "libE@example.com")
    structure = create_item(client, "saved-structures", saved_structure("Nom initial"), microproject=slug)

    update_item(client, "saved-structures", structure["id"], name="Nom corrige", substrate=substrate(), steps=PGAN_STEPS)
    assert names(list_items(client, "saved-structures", microproject=slug), "microproject") == ["Nom corrige"]


def test_delete_a_saved_structure(client):
    slug = signup_with_microproject(client, "libF@example.com")
    structure = create_item(client, "saved-structures", saved_structure("A retirer"), microproject=slug)

    delete_item(client, "saved-structures", structure["id"])
    assert names(list_items(client, "saved-structures", microproject=slug), "microproject") == []


def test_builtin_presets_are_listed_and_can_be_duplicated_into_a_real_structure(client):
    slug = signup_with_microproject(client, "libH@example.com")

    builtins = list_items(client, "saved-structures", scope="builtin")
    assert "Nanofil pointe semipolaire (V-pit inversé)" in names(builtins)
    preset = by_name(builtins, "Nanofil pointe semipolaire (V-pit inversé)")
    assert preset["scope"] == "builtin"
    assert any(step["kind"] == "faceted_growth" for step in preset["steps"])

    # duplicating a preset creates a real, editable structure (presets themselves aren't stored)
    saved = create_item(
        client,
        "saved-structures",
        saved_structure("Mon nanofil", substrate=preset["substrate"], steps=preset["steps"], derived_from=preset["name"]),
        microproject=slug,
    )
    assert saved["derived_from"] == "Nanofil pointe semipolaire (V-pit inversé)"
    assert saved["can_edit"] is True


def test_viewer_cannot_create_a_saved_structure(client):
    slug = signup_with_microproject(client, "libG-owner@example.com")
    join_as(client, slug, "libG-viewer@example.com", owner="libG-owner@example.com", role="viewer")
    denied = client.post("/api/saved-structures", json={**saved_structure("Interdit"), "scope": "microproject", "microproject": slug})
    assert denied.status_code == 403


def test_a_saved_structure_keeps_its_declared_parameters(client):
    slug = signup_with_microproject(client, "libDeclared@example.com")
    declared = {"0": [{"name": "dopage", "value": 1e19, "obtention": {"precurseur": "Cp2Mg"}}]}
    saved = create_item(client, "saved-structures", saved_structure("PGaN dope", declared_params=declared), microproject=slug)
    assert saved["declared_params"] == declared
