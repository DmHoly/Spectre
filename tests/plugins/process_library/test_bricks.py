"""L'appartenance des étapes aux briques dans les bibliothèques (TODO § 3 ter) : une structure
enregistrée et une brique la gardent, par positions d'étape comme les étiquettes, et la rendent au
chargement ; une structure publiée depuis une version d'étude garde celle de la version."""

from __future__ import annotations

from support.experiments import launch, process
from support.microprojects import signup_with_microproject
from support.process_library import create_item, get_item, saved_structure, tech_brick, update_item
from support.structures import deposition, simulate, substrate

THREE_STEPS = [deposition("n-GaN", "GaN", thickness_nm=200), deposition("Puits", "InGaN", thickness_nm=3), deposition("p-GaN", "GaN", thickness_nm=100)]
BRICK = {"group_id": "brick-1", "name": "Jonction", "source": "abc123", "step_indexes": [1, 2]}


def test_a_saved_structure_and_a_brick_keep_their_bricks(client):
    slug = signup_with_microproject(client, "lib-bricks@example.com")
    structure = create_item(client, "saved-structures", saved_structure("Diode", steps=THREE_STEPS, bricks=[BRICK]), microproject=slug)
    assert get_item(client, "saved-structures", structure["id"])["bricks"] == [BRICK]
    composed = create_item(client, "tech-bricks", tech_brick("Composée", steps=THREE_STEPS, bricks=[BRICK]), microproject=slug)
    assert get_item(client, "tech-bricks", composed["id"])["bricks"] == [BRICK]

    changed = update_item(client, "saved-structures", structure["id"], bricks=[{**BRICK, "step_indexes": [0, 1]}])
    assert changed["bricks"] == [{**BRICK, "step_indexes": [0, 1]}]
    assert create_item(client, "saved-structures", saved_structure("Nue"), microproject=slug)["bricks"] == []
    # une brique hors des étapes : refusée
    response = client.post(
        "/api/tech-bricks", json={**tech_brick("Hors", bricks=[{**BRICK, "step_indexes": [3]}]), "scope": "microproject", "microproject": slug}
    )
    assert response.status_code == 422 and response.json()["code"] == "invalid_brick"


def test_a_structure_published_from_a_study_keeps_its_bricks(client):
    slug = signup_with_microproject(client, "lib-bricks-publish@example.com")
    study = launch(client, slug, steps=THREE_STEPS, bricks=[BRICK])
    published = create_item(client, "saved-structures", {**process(client, slug, study["id"]), "name": "Publiée"}, scope="shared")
    assert published["bricks"] == [BRICK]


def test_the_name_of_a_brick_is_no_longer_than_a_process_brick_accepts(client):
    """Le nom d'une brique de bibliothèque est celui que reprend la brique d'un procédé où on
    l'insère (``ProcessBrick``, 120 caractères au plus) : plus long, il est refusé à la création et
    à la modification - avant, il passait, et chaque simulation de la brique insérée était refusée."""
    slug = signup_with_microproject(client, "lib-bricks-name@example.com")
    too_long = client.post("/api/tech-bricks", json={**tech_brick("x" * 121), "scope": "microproject", "microproject": slug})
    assert too_long.status_code == 422
    brick = create_item(client, "tech-bricks", tech_brick("é" * 120), microproject=slug)
    assert client.patch(f"/api/tech-bricks/{brick['id']}", json={"name": "y" * 121}).status_code == 422
    # le nom le plus long qu'accepte la bibliothèque, une simulation l'accepte aussi
    simulated = simulate(client, {"substrate": substrate(), "steps": THREE_STEPS, "bricks": [{**BRICK, "name": brick["name"]}]})
    assert simulated.status_code == 200, simulated.text
