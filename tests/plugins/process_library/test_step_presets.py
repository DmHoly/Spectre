"""Les présets d'étape : une étape entière déjà réglée (n'importe quel type, ses champs, ses
paramètres déclarés, son étiquette, la recette du procédé qu'elle nomme, les paramètres à faire
varier), dans une bibliothèque (intégrée, partagée, µprojet) ; sa version monte quand son contenu
change, pas quand on la renomme."""

from __future__ import annotations

from support.microprojects import create_microproject, join_as, signup_with_microproject
from support.process_library import by_name, create_item, delete_item, list_items, names, step_preset, update_item
from support.structures import etch, layer_label, simulate, substrate

SELECTIVE = {"name": "Sélective Al2O3", "mode": "isotropic", "selectivity_by_material": {"Al2O3": 1.0}, "default_factor": 0.0}
PYRAMID = {
    "kind": "faceted_growth",
    "name": "Pyramide",
    "material": "GaN",
    "thickness": {"value": 200, "unit": "nm"},
    "rate_c": 0.2,
    "rate_m": 0.1,
    "rate_sp": 1.0,
    "semi_polar_angle_deg": 28,
}


def _post(client, slug, body):
    return client.post("/api/step-presets", json={**body, "scope": "microproject", "microproject": slug})


def test_create_a_microproject_scoped_deposition_preset(client):
    slug = signup_with_microproject(client, "presetA@example.com")

    created = create_item(client, "step-presets", step_preset("Nitrure maison", notes="recette perso"), microproject=slug)
    assert (created["name"], created["scope"], created["microproject"], created["notes"]) == ("Nitrure maison", "microproject", slug, "recette perso")
    assert created["step"]["kind"] == "deposition" and created["version"] == 1

    listed = list_items(client, "step-presets", microproject=slug)
    assert names(listed, "microproject") == ["Nitrure maison"]
    assert names(listed, "shared") == []


def test_a_preset_holds_a_whole_step_with_its_parameters_label_and_variable_fields(client):
    slug = signup_with_microproject(client, "presetB@example.com")
    body = step_preset(
        "Pyramide GaN",
        step=PYRAMID,
        declared_params=[{"name": "température", "value": 1000, "unit": "°C"}, {"name": "dopage Si", "value": 5e18, "unit": "cm⁻³"}],
        layer_label=layer_label("", "thickness", "declared:dopage Si"),
        variable_fields=["thickness", "rate_sp", "declared:température"],
    )
    created = create_item(client, "step-presets", body, microproject=slug)
    assert created["step"]["rate_sp"] == 1.0 and created["step"]["semi_polar_angle_deg"] == 28
    assert [p["name"] for p in created["declared_params"]] == ["température", "dopage Si"]
    assert created["layer_label"] == {"text": "", "values": ["thickness", "declared:dopage Si"]}
    assert created["variable_fields"] == ["thickness", "rate_sp", "declared:température"]


def test_a_variable_field_must_be_one_of_the_step_or_of_its_declared_parameters(client):
    slug = signup_with_microproject(client, "presetC@example.com")
    assert _post(client, slug, step_preset("P", step=PYRAMID, variable_fields=["depth"])).status_code == 422
    assert _post(client, slug, step_preset("P", step=PYRAMID, variable_fields=["declared:absent"])).status_code == 422
    assert _post(client, slug, step_preset("P", step=PYRAMID, variable_fields=["name"])).status_code == 422


def test_a_selective_etch_preset_carries_its_own_recipe(client):
    slug = signup_with_microproject(client, "presetD@example.com")
    step = etch("Retrait Al2O3", recipe="Sélective Al2O3", depth_nm=50)
    # sans sa recette, la recette nommée n'existe pas
    refused = _post(client, slug, step_preset("Gravure sélective", step=step))
    assert refused.status_code == 422 and refused.json()["code"] == "unknown_recipe"
    created = create_item(client, "step-presets", step_preset("Gravure sélective", step=step, recipes={"etch": [SELECTIVE]}), microproject=slug)
    assert created["recipes"]["etch"][0]["selectivity_by_material"] == {"Al2O3": 1.0}


def test_the_version_goes_up_when_the_content_changes_not_the_name(client):
    slug = signup_with_microproject(client, "presetE@example.com")
    preset = create_item(client, "step-presets", step_preset("Nom initial"), microproject=slug)

    renamed = update_item(client, "step-presets", preset["id"], name="Nom corrige", notes="note")
    assert (renamed["id"], renamed["version"]) == (preset["id"], 1)
    thicker = {**preset["step"], "thickness": {"value": 50, "unit": "nm"}}
    assert update_item(client, "step-presets", preset["id"], step=thicker)["version"] == 2
    assert update_item(client, "step-presets", preset["id"], variable_fields=["thickness"])["version"] == 3
    assert update_item(client, "step-presets", preset["id"], step=thicker)["version"] == 3  # rien de neuf
    assert names(list_items(client, "step-presets", microproject=slug), "microproject") == ["Nom corrige"]


def test_shared_preset_is_visible_from_a_different_microproject(client):
    signup_with_microproject(client, "presetF@example.com")
    create_item(client, "step-presets", step_preset("Base commune"), scope="shared")

    slug_b = create_microproject(client, "Autre projet")["slug"]
    listed = list_items(client, "step-presets", microproject=slug_b)
    assert names(listed, "shared") == ["Base commune"]
    assert names(listed, "microproject") == []


def test_duplicate_name_in_the_same_library_is_rejected(client):
    slug = signup_with_microproject(client, "presetG@example.com")
    create_item(client, "step-presets", step_preset("Preset X"), microproject=slug)
    assert _post(client, slug, step_preset("Preset X")).status_code == 409


def test_delete_a_preset(client):
    slug = signup_with_microproject(client, "presetH@example.com")
    preset = create_item(client, "step-presets", step_preset("A retirer"), microproject=slug)

    delete_item(client, "step-presets", preset["id"])
    assert names(list_items(client, "step-presets", microproject=slug), "microproject") == []


def test_builtin_presets_are_whole_steps_that_simulate(client):
    signup_with_microproject(client, "presetI@example.com")

    builtins = list_items(client, "step-presets", scope="builtin")
    selective, pyramid, clean = (by_name(builtins, name) for name in ("Gravure sélective Al2O3", "Pyramide GaN", "Clean HF"))
    assert (selective["scope"], selective["can_edit"]) == ("builtin", False)
    assert selective["recipes"]["etch"][0]["name"] == selective["step"]["recipe"]
    assert pyramid["step"]["kind"] == "faceted_growth" and "thickness" in pyramid["variable_fields"]
    assert clean["step"]["kind"] == "chemical" and clean["layer_label"]["values"] == ["declared:durée"]

    # chaque préset intégré s'insère tel quel dans un procédé et se simule
    base = substrate("GaN", width_nm=400, thickness_nm=200)
    for preset in builtins:
        response = simulate(client, {"substrate": base, "steps": [preset["step"]], "recipes": preset["recipes"]})
        assert response.status_code == 200, (preset["name"], response.text)


def test_viewer_cannot_create_a_preset(client):
    slug = signup_with_microproject(client, "presetJ-owner@example.com")
    join_as(client, slug, "presetJ-viewer@example.com", owner="presetJ-owner@example.com", role="viewer")
    assert _post(client, slug, step_preset("Interdit")).status_code == 403


def test_a_preset_must_name_an_existing_recipe_of_its_kind(client):
    slug = signup_with_microproject(client, "presetK@example.com")

    unknown = _post(client, slug, step_preset("Fantome", recipe="Recette inexistante"))
    assert unknown.status_code == 422
    assert unknown.json()["code"] == "unknown_recipe"
    # une recette de gravure ne fait pas un préset de dépôt
    assert _post(client, slug, step_preset("Mauvais type", recipe="Dry Oxide Etch")).status_code == 422

    preset = create_item(client, "step-presets", step_preset("Valide"), microproject=slug)
    changed = client.patch(f"/api/step-presets/{preset['id']}", json={"step": {**preset["step"], "recipe": "<img src=x onerror=alert(1)>"}})
    assert changed.status_code == 422
    assert by_name(list_items(client, "step-presets", microproject=slug), "Valide")["step"]["recipe"] == "CVD Conformal"


def test_a_preset_can_use_a_recipe_of_the_root_library(client):
    """« Gravure sélective Al2O3 » existe aussi dans recettes.yml : elle compte comme une recette."""
    slug = signup_with_microproject(client, "presetL@example.com")
    created = create_item(client, "step-presets", step_preset("Selective", kind="etch", recipe="Gravure sélective Al2O3"), microproject=slug)
    assert created["step"]["recipe"] == "Gravure sélective Al2O3"


def test_a_study_remembers_which_preset_and_version_each_step_came_from(client):
    from support.experiments import launch, process

    slug = signup_with_microproject(client, "presetM@example.com")
    preset = create_item(client, "step-presets", step_preset("Oxyde maison"), microproject=slug)
    origin = {"id": preset["id"], "name": preset["name"], "version": preset["version"]}
    study = launch(client, slug, steps=[preset["step"]], preset_origins={"0": origin, "7": origin})
    # l'origine d'une étape hors du procédé est ignorée
    assert process(client, slug, study["id"])["preset_origins"] == {"0": origin}
    # une trace, pas un lien : modifier le préset ne change pas l'étude
    update_item(client, "step-presets", preset["id"], step={**preset["step"], "thickness": {"value": 99, "unit": "nm"}})
    assert process(client, slug, study["id"])["steps"][0]["thickness"]["value"] == 20
