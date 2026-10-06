"""Les recettes propres au procédé : une gravure sélective (ou un dépôt) définie dans le constructeur,
sans passer par recettes.yml. Une étape la nomme comme n'importe quelle recette ; elle l'emporte sur
une recette de la bibliothèque du même nom ; elle voyage avec le procédé - simulation, campagne,
étude lancée et relue, structure enregistrée - et un procédé sans recette garde sa forme d'avant."""

from __future__ import annotations

from support.experiments import launch, launch_campaign, process
from support.microprojects import signup_with_microproject
from support.process_library import create_item, get_item, saved_structure
from support.structures import campaign_plan, deposition, etch, fixed_step_id, identified, simulate, substrate

SELECTIVE = {"name": "Sélective Al2O3", "mode": "isotropic", "selectivity_by_material": {"Al2O3": 1.0}, "default_factor": 0.0}
STACK = [
    deposition("GaN", "GaN", recipe="MOCVD Epitaxial", thickness_nm=60),
    deposition("Masque", "Al2O3", recipe="ALD Conformal", thickness_nm=20),
    etch("Retrait du masque", recipe="Sélective Al2O3", depth_nm=40),
]


def _final_materials(response) -> list[str]:
    assert response.status_code == 200, response.text
    return response.json()["frames"][-1]["materials"]


def test_a_selective_etch_defined_in_the_process_only_etches_its_material(client):
    signup_with_microproject(client, "own-recipe@example.com")
    body = {"substrate": substrate("Sapphire", width_nm=200, thickness_nm=50), "steps": STACK}
    # sans la recette : inconnue
    assert simulate(client, body).status_code == 422
    # avec : l'Al2O3 part, le GaN (bien que la profondeur le dépasse) reste
    assert _final_materials(simulate(client, {**body, "recipes": {"etch": [SELECTIVE]}})) == ["GaN", "Sapphire"]


def test_a_process_recipe_wins_over_a_library_recipe_of_the_same_name(client):
    signup_with_microproject(client, "own-recipe-shadow@example.com")
    steps = [*STACK[:2], etch("Gravure", recipe="Anisotropic RIE", depth_nm=40)]
    body = {"substrate": substrate("Sapphire", width_nm=200, thickness_nm=50), "steps": steps}
    assert "Al2O3" not in _final_materials(simulate(client, body))
    gentle = {"name": "Anisotropic RIE", "mode": "directional", "default_factor": 0.0}
    assert "Al2O3" in _final_materials(simulate(client, {**body, "recipes": {"etch": [gentle]}}))


def test_two_process_recipes_cannot_share_a_name(client):
    signup_with_microproject(client, "own-recipe-twice@example.com")
    body = {"substrate": substrate(), "steps": STACK, "recipes": {"etch": [SELECTIVE, {**SELECTIVE, "default_factor": 1.0}]}}
    assert simulate(client, body).status_code == 422


def test_a_launched_study_keeps_its_recipes_and_gives_them_back_to_the_builder(client):
    slug = signup_with_microproject(client, "own-recipe-launch@example.com")
    study = launch(client, slug, steps=STACK, recipes={"etch": [SELECTIVE]})
    editable = process(client, slug, study["id"])
    assert editable["recipes"] == {"etch": [{**SELECTIVE, "angle_deg": 0.0, "selectivity_by_category": {}, "notes": None}]}
    # sans recette du procédé, la forme d'avant : pas de clé
    plain = launch(client, slug, title="Sans recette")
    assert "recipes" not in process(client, slug, plain["id"])


def test_a_campaign_simulates_each_variant_with_the_process_recipes(client):
    slug = signup_with_microproject(client, "own-recipe-campaign@example.com")
    steps = identified(STACK)
    plan = campaign_plan([20, 40], step_id=fixed_step_id(3), field="depth")
    study = launch_campaign(client, slug, plan=plan, steps=steps, recipes={"etch": [SELECTIVE]})
    variant = process(client, slug, study["id"], variant=1)
    assert variant["recipes"]["etch"][0]["name"] == "Sélective Al2O3"


def test_a_saved_structure_keeps_its_recipes(client):
    slug = signup_with_microproject(client, "own-recipe-library@example.com")
    created = create_item(client, "saved-structures", saved_structure("Masque retiré", steps=STACK, recipes={"etch": [SELECTIVE]}), microproject=slug)
    assert get_item(client, "saved-structures", created["id"])["recipes"]["etch"][0]["selectivity_by_material"] == {"Al2O3": 1.0}
