from __future__ import annotations

from support.microprojects import create_microproject, join_as, signup_with_microproject
from support.process_library import by_name, create_item, delete_item, list_items, names, step_preset, update_item
from support.structures import deposition, substrate


def test_create_a_microproject_scoped_deposition_preset(client):
    slug = signup_with_microproject(client, "presetA@example.com")

    created = create_item(client, "step-presets", step_preset("Nitrure maison", notes="recette perso"), microproject=slug)
    assert created["name"] == "Nitrure maison"
    assert created["scope"] == "microproject"
    assert created["microproject"] == slug
    assert created["notes"] == "recette perso"

    listed = list_items(client, "step-presets", microproject=slug)
    assert names(listed, "microproject") == ["Nitrure maison"]
    assert names(listed, "shared") == []


def test_create_an_etch_preset(client):
    slug = signup_with_microproject(client, "presetB@example.com")

    created = create_item(client, "step-presets", step_preset("Gravure selective", kind="etch", recipe="Dry Oxide Etch"), microproject=slug)
    assert created["payload"] == {"kind": "etch", "recipe": "Dry Oxide Etch"}


def test_shared_preset_is_visible_from_a_different_microproject(client):
    signup_with_microproject(client, "presetC@example.com")
    create_item(client, "step-presets", step_preset("Base commune"), scope="shared")

    slug_b = create_microproject(client, "Autre projet")["slug"]
    listed = list_items(client, "step-presets", microproject=slug_b)
    assert names(listed, "shared") == ["Base commune"]
    assert names(listed, "microproject") == []


def test_duplicate_name_in_the_same_library_is_rejected(client):
    slug = signup_with_microproject(client, "presetD@example.com")
    create_item(client, "step-presets", step_preset("Preset X"), microproject=slug)
    again = client.post("/api/step-presets", json={**step_preset("Preset X"), "scope": "microproject", "microproject": slug})
    assert again.status_code == 409


def test_rename_a_preset_in_place(client):
    slug = signup_with_microproject(client, "presetE@example.com")
    preset = create_item(client, "step-presets", step_preset("Nom initial"), microproject=slug)

    renamed = update_item(client, "step-presets", preset["id"], name="Nom corrige")
    assert renamed["id"] == preset["id"]
    assert names(list_items(client, "step-presets", microproject=slug), "microproject") == ["Nom corrige"]


def test_delete_a_preset(client):
    slug = signup_with_microproject(client, "presetF@example.com")
    preset = create_item(client, "step-presets", step_preset("A retirer"), microproject=slug)

    delete_item(client, "step-presets", preset["id"])
    assert names(list_items(client, "step-presets", microproject=slug), "microproject") == []


def test_builtin_presets_are_listed_and_usable_in_a_step(client):
    slug = signup_with_microproject(client, "presetG@example.com")

    builtins = list_items(client, "step-presets", scope="builtin")
    assert "MOCVD Epitaxial" in names(builtins)
    assert "Cl2 ICP-RIE (III-N)" in names(builtins)
    mocvd = by_name(builtins, "MOCVD Epitaxial")
    assert mocvd["scope"] == "builtin"
    assert mocvd["payload"]["recipe"] == "MOCVD Epitaxial"
    assert mocvd["can_edit"] is False

    # a preset only pre-fills a step's own fields - it's never referenced by name at simulate time
    sim = client.post(
        "/api/simulations",
        json={"substrate": substrate(), "steps": [deposition("GaN", "GaN", recipe=mocvd["payload"]["recipe"], thickness_nm=10)]},
    )
    assert sim.status_code == 200


def test_viewer_cannot_create_a_preset(client):
    slug = signup_with_microproject(client, "presetH-owner@example.com")
    join_as(client, slug, "presetH-viewer@example.com", owner="presetH-owner@example.com", role="viewer")
    denied = client.post("/api/step-presets", json={**step_preset("Interdit"), "scope": "microproject", "microproject": slug})
    assert denied.status_code == 403


def test_a_preset_must_name_an_existing_recipe_of_its_kind(client):
    slug = signup_with_microproject(client, "presetI@example.com")

    unknown = client.post(
        "/api/step-presets", json={**step_preset("Fantome", recipe="Recette inexistante"), "scope": "microproject", "microproject": slug}
    )
    assert unknown.status_code == 422
    assert unknown.json()["code"] == "unknown_recipe"
    # une recette de gravure ne fait pas un préset de dépôt
    wrong_kind = client.post(
        "/api/step-presets", json={**step_preset("Mauvais type", recipe="Dry Oxide Etch"), "scope": "microproject", "microproject": slug}
    )
    assert wrong_kind.status_code == 422

    preset = create_item(client, "step-presets", step_preset("Valide"), microproject=slug)
    changed = client.patch(f"/api/step-presets/{preset['id']}", json={"payload": {"kind": "deposition", "recipe": "<img src=x onerror=alert(1)>"}})
    assert changed.status_code == 422
    assert by_name(list_items(client, "step-presets", microproject=slug), "Valide")["payload"]["recipe"] == "CVD Conformal"


def test_a_preset_can_use_a_recipe_of_the_root_library(client):
    """« Gravure sélective Al2O3 » n'existe que dans recettes.yml : elle compte comme une recette."""
    slug = signup_with_microproject(client, "presetJ@example.com")
    created = create_item(client, "step-presets", step_preset("Selective", kind="etch", recipe="Gravure sélective Al2O3"), microproject=slug)
    assert created["payload"]["recipe"] == "Gravure sélective Al2O3"
