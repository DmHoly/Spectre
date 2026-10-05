"""Les pages des références (la liste de toute l'application et l'évolution d'une référence), leur
entrée dans la barre du haut, et ce que le constructeur fait d'une version de référence : il reprend
son procédé tel que ``GET .../versions/{n}`` le donne (étapes avec leur id, étiquettes, briques) et
lance l'étude avec ``reference_origin``."""

from __future__ import annotations

from support.accounts import signup
from support.experiments import launch, post_evolve
from support.microprojects import create_microproject, signup_with_microproject
from support.references import create_reference, get_version, origin, post_version, publish, version_graph
from support.structures import layer_label, steps


def test_the_reference_pages_are_served_with_their_nav_entry(client):
    signup(client, "refs-pages@example.com")
    create_reference(client, "Epitaxie standard")
    listing = client.get("/references")
    assert listing.status_code == 200
    assert '<a href="/references"' in listing.text and ">Références</a>" in listing.text
    assert "/static/references/client.js" in listing.text
    page = client.get("/references/epitaxie-standard")
    assert page.status_code == 200
    # le diagramme est celui de la page d'évolution des structures, partagé
    assert "/static/experiments/evolution-graph.js" in page.text
    assert "/static/experiments/evolution-graph.js" in client.get("/microprojets/x/evolution").text


def test_a_study_started_from_a_version_takes_its_process_as_the_builder_sends_it(client):
    slug = signup_with_microproject(client, "refs-builder@example.com", "Epi")
    source = launch(client, slug, title="Base", intent="Depart", steps=steps(20), layer_labels={"0": layer_label("Oxyde", "thickness")})
    create_reference(client, "Base")
    publish(client, "base", slug, source["id"])

    # dans un autre µprojet, le constructeur charge le procédé de la version 1.0 et le renvoie tel quel
    other = create_microproject(client, "Ailleurs")["slug"]
    process = get_version(client, "base", "1.0")["process"]
    study = launch(
        client,
        other,
        title="Depuis la base",
        intent="x",
        substrate=process["substrate"],
        steps=process["steps"],
        declared_params=process.get("declared_params") or {},
        layer_labels=process["layer_labels"],
        bricks=process["bricks"],
        reference_origin=origin("base", "1.0"),
    )
    assert study["reference_origin"] == origin("base", "1.0")
    assert version_graph(client, "base")["nodes"][0]["usage_count"] == 1

    # la même structure : rien à publier ; les étapes gardent leurs ids, une évolution se compare à 1.0
    assert post_version(client, "base", other, study["id"]).status_code == 409
    renamed = [{**process["steps"][0], "name": "Oxyde de grille"}]
    evolved = post_evolve(
        client, other, study["id"], title="Depuis la base", intent="x", steps=renamed, layer_labels=process["layer_labels"], if_match=study["version_id"]
    )
    assert evolved.status_code == 201
    published = publish(client, "base", other, study["id"])
    assert (published["number"], published["parent"], published["change_level"]) == ("1.1", "1.0", "patch")
