"""Les étiquettes de couches dans les bibliothèques (TODO § 3 ter) : une structure enregistrée et une
brique les gardent, par position d'étape comme les paramètres déclarés, et les rendent au
chargement ; une structure publiée depuis une version d'étude garde les siennes."""

from __future__ import annotations

from support.experiments import launch, process
from support.microprojects import signup_with_microproject
from support.process_library import create_item, get_item, saved_structure, tech_brick, update_item
from support.structures import deposition, layer_label

TWO_STEPS = [deposition("n-GaN", "GaN", thickness_nm=200), deposition("p-GaN", "GaN", thickness_nm=100)]


def test_a_saved_structure_and_a_brick_keep_their_labels(client):
    slug = signup_with_microproject(client, "lib-labels@example.com")
    labels = {"1": layer_label("p-GaN", "thickness")}
    structure = create_item(client, "saved-structures", saved_structure("Diode", steps=TWO_STEPS, layer_labels=labels), microproject=slug)
    assert get_item(client, "saved-structures", structure["id"])["layer_labels"] == labels
    brick = create_item(client, "tech-bricks", tech_brick("Jonction", steps=TWO_STEPS, layer_labels=labels), microproject=slug)
    assert get_item(client, "tech-bricks", brick["id"])["layer_labels"] == labels

    # modifiées comme le reste ; sans étiquette, un élément n'en a pas
    changed = update_item(client, "saved-structures", structure["id"], layer_labels={"0": layer_label("n", "thickness")})
    assert changed["layer_labels"] == {"0": layer_label("n", "thickness")}
    plain = create_item(client, "saved-structures", saved_structure("Nue"), microproject=slug)
    assert plain["layer_labels"] == {}


def test_a_label_outside_the_steps_is_refused(client):
    slug = signup_with_microproject(client, "lib-labels-bad@example.com")
    response = client.post(
        "/api/saved-structures",
        json={**saved_structure("Hors", steps=TWO_STEPS, layer_labels={"2": layer_label("x")}), "scope": "microproject", "microproject": slug},
    )
    assert response.status_code == 422
    response = client.post(
        "/api/tech-bricks", json={**tech_brick("Hors", layer_labels={"0": layer_label("x", "poids")}), "scope": "microproject", "microproject": slug}
    )
    assert response.status_code == 422
    # un chiffre en exposant n'est pas une position : le même refus, avec son code
    for kind, item in (("saved-structures", saved_structure("Exposant", steps=TWO_STEPS)), ("tech-bricks", tech_brick("Exposant", steps=TWO_STEPS))):
        response = client.post(f"/api/{kind}", json={**item, "layer_labels": {"²": layer_label("x")}, "scope": "microproject", "microproject": slug})
        assert response.status_code == 422 and response.json()["code"] == "invalid_layer_label", kind


def test_a_structure_published_from_a_study_keeps_its_labels(client):
    slug = signup_with_microproject(client, "lib-labels-publish@example.com")
    study = launch(client, slug, steps=TWO_STEPS, layer_labels={"1": layer_label("p-GaN", "thickness")})
    # ce que fait la page d'évolution : le procédé de la version, publié tel quel
    published = create_item(client, "saved-structures", {**process(client, slug, study["id"]), "name": "Publiée"}, scope="shared")
    assert published["layer_labels"] == {"1": layer_label("p-GaN", "thickness")}
