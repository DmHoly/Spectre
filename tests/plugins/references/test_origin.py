"""L'origine d'une étude (``reference_origin``) : la version de référence dont elle part, donnée au
lancement (experiments n'en vérifie que la forme), reportée aux versions suivantes, gardée par une
fourche et une combinaison ; le plugin references en compte les usages. Une origine inconnue se lit
telle quelle, sans erreur."""

from __future__ import annotations

from support.experiments import combine, evolve, experiments_url, get_experiment, launch, post_launch, tag
from support.microprojects import create_microproject, signup_with_microproject
from support.references import create_reference, get_reference, get_version, origin, post_version, publish, references, version_graph
from support.structures import steps


def _published(client, email):
    slug = signup_with_microproject(client, email, "Epi")
    source = launch(client, slug, title="Base", intent="Depart", steps=steps(20))
    create_reference(client, "Base")
    publish(client, "base", slug, source["id"])
    return slug


def test_the_origin_is_recorded_carried_and_counted(client):
    slug = _published(client, "origin-carried@example.com")
    process = get_version(client, "base", "1.0")["process"]
    study = launch(client, slug, title="Depuis la base", intent="x", steps=process["steps"], reference_origin=origin("base", "1.0"))
    assert study["reference_origin"] == {"reference": "base", "version": "1.0"}

    # reportée : une étiquette, une évolution
    tagged = tag(client, slug, study["id"], ["epi"])
    assert tagged["reference_origin"] == {"reference": "base", "version": "1.0"}
    evolved = evolve(client, slug, study["id"], title="Depuis la base", intent="y", steps=steps(25))
    assert evolved["reference_origin"] == {"reference": "base", "version": "1.0"}

    # gardée par une fourche, sauf si la requête en donne une autre
    fork = launch(client, slug, title="Fourche", intent="z", steps=steps(26), from_version={"experiment_id": study["id"]})
    assert fork["reference_origin"] == {"reference": "base", "version": "1.0"}
    # et par une combinaison (celle de la première étude)
    combined = combine(client, slug, study["id"], launch(client, slug, title="Autre", intent="w", steps=steps(27))["id"])
    assert combined["reference_origin"] == {"reference": "base", "version": "1.0"}

    # une autre µprojet part aussi de cette version
    other = create_microproject(client, "Autre µprojet")["slug"]
    launch(client, other, title="Ailleurs", intent="x", steps=steps(20), reference_origin=origin("base", "1.0"))

    node = version_graph(client, "base")["nodes"][0]
    assert node["usage_count"] == 4  # l'étude, sa fourche, la combinaison, et celle de l'autre µprojet
    assert {(u["microproject"]["slug"], u["title"]) for u in node["usages"]} == {
        (slug, "Depuis la base"),
        (slug, "Fourche"),
        (slug, "Combinée"),
        (other, "Ailleurs"),
    }
    assert references(client)[0]["usage_count"] == 4

    # une étude sans origine n'en a pas
    assert get_experiment(client, slug, "base")["reference_origin"] is None


def test_publishing_from_a_study_derives_from_the_version_it_started_from(client):
    slug = _published(client, "origin-parent@example.com")
    a = launch(client, slug, title="A", intent="x", steps=steps(25))
    assert publish(client, "base", slug, a["id"])["number"] == "1.1"
    # partie de 1.0 (pas de 1.1, la dernière) : sa version dérive de 1.0
    b = launch(client, slug, title="B", intent="x", steps=steps(30), reference_origin=origin("base", "1.0"))
    published = publish(client, "base", slug, b["id"])
    assert (published["number"], published["parent"]) == ("1.2", "1.0")
    # partie d'une autre référence : la dernière version de celle-ci
    create_reference(client, "Autre")
    c = launch(client, slug, title="C", intent="x", steps=steps(35), reference_origin=origin("autre", "1.0"))
    assert publish(client, "base", slug, c["id"])["parent"] == "1.2"


def test_an_unknown_origin_is_shown_as_is(client):
    slug = _published(client, "origin-unknown@example.com")
    study = launch(client, slug, title="Perdue", intent="x", steps=steps(20), reference_origin=origin("nulle-part", "3.2"))
    assert get_experiment(client, slug, study["id"])["reference_origin"] == {"reference": "nulle-part", "version": "3.2"}
    late = launch(client, slug, title="Trop tot", intent="x", steps=steps(20), reference_origin=origin("base", "7.0"))
    assert late["reference_origin"]["version"] == "7.0"
    assert get_reference(client, "base")["usage_count"] == 0
    # publier depuis une étude d'origine inconnue : la dernière version est le parent
    assert post_version(client, "base", slug, study["id"]).status_code == 409  # même structure que 1.0


def test_the_shape_of_an_origin_is_checked(client):
    slug = signup_with_microproject(client, "origin-shape@example.com", "Epi")
    for bad in ({"reference": "Base Majuscule", "version": "1.0"}, {"reference": "base", "version": "1"}, {"reference": "base", "version": "1.0", "x": 1}):
        response = post_launch(client, slug, title="E", intent="x", steps=steps(20), reference_origin=bad)
        assert response.status_code == 422, bad
    assert client.get(experiments_url(slug)).json()["total"] == 0
