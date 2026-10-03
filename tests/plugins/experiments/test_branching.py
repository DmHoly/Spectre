"""Bifurquer, c'est créer une nouvelle piste à partir d'une version (``from_version``) ; une écriture
sur une piste part toujours de sa pointe, et une page périmée (``If-Match``) est refusée plutôt que
de créer une fourche implicite."""

from __future__ import annotations

from support.experiments import (
    add_evidence,
    conclude,
    evolve,
    experiments_url,
    get_experiment,
    get_version,
    launch,
    launch_body,
    list_experiments,
    post_evolve,
)
from support.microprojects import signup_with_microproject
from support.structures import steps


def test_fork_creates_a_new_line_and_is_visible_as_a_child(client):
    slug = signup_with_microproject(client, "fork@example.com", name="F")

    launched = launch(client, slug, title="Reference", intent="Depart", steps=steps(20))
    assert launched["id"] == "reference"

    # continuer la même piste
    continued = evolve(client, slug, "reference", title="Reference", intent="Reduire un peu", steps=steps(15))
    assert continued["id"] == "reference"

    # bifurquer depuis le même point de départ
    forked = launch(
        client,
        slug,
        title="Piste epaisse",
        intent="Explorer une epaisseur plus grande",
        steps=steps(30),
        branch="piste-epaisse",
        from_version={"experiment_id": "reference", "version_id": launched["version_id"]},
    )
    assert forked["id"] == "piste-epaisse"

    first = get_version(client, slug, "reference", launched["version_id"])
    assert {(c["experiment_id"], c["version_id"]) for c in first["children"]} == {
        ("reference", continued["version_id"]),
        ("piste-epaisse", forked["version_id"]),
    }
    # deux pistes indépendantes, nées du même parent
    assert continued["parents"] == [launched["version_id"]]
    assert forked["parents"] == [launched["version_id"]]


def test_forking_onto_an_existing_line_name_is_refused(client):
    slug = signup_with_microproject(client, "fork2@example.com", name="F2")
    launch(client, slug, title="Reference", intent="Depart")
    launch(
        client, slug, title="Piste", intent="Explorer", steps=steps(25), branch="piste-partagee", from_version={"experiment_id": "reference"}
    )

    body = launch_body(title="Collision", intent="Y", branch="piste-partagee", from_version={"experiment_id": "reference"})
    assert client.post(experiments_url(slug), json=body).status_code == 409


def test_writing_from_a_stale_page_is_refused_instead_of_forking(client):
    # avant : « continuer cette piste » depuis une version dépassée créait en silence une piste
    # « titre-2 » dans le graphe. Désormais la page envoie la version qu'elle affiche : 412, rien
    # n'est écrit.
    slug = signup_with_microproject(client, "stale@example.com", name="S")
    launched = launch(client, slug, title="Reference", intent="Depart")
    evolve(client, slug, "reference", title="Reference v2", intent="Suite", steps=steps(15))

    response = post_evolve(
        client, slug, "reference", if_match=launched["version_id"], title="Autre suite", intent="Depuis le depart", steps=steps(40)
    )
    assert response.status_code == 412
    assert response.json()["code"] == "stale_version"
    assert [item["id"] for item in list_experiments(client, slug)["items"]] == ["reference"]  # aucune fourche
    assert get_experiment(client, slug, "reference")["title"] == "Reference v2"


def test_writes_without_if_match_always_continue_the_tip(client):
    slug = signup_with_microproject(client, "stale2@example.com", name="S2")
    launch(client, slug, title="Reference", intent="Depart")
    evolved = evolve(client, slug, "reference", title="Reference v2", intent="Suite", steps=steps(15))

    concluded = conclude(client, slug, "reference", summary="Conclu", objective_results=[])
    assert concluded["parents"] == [evolved["version_id"]]
    added = add_evidence(client, slug, "reference", "Mesure ajoutee apres coup", source="profilometre")
    assert added["id"] == "reference"
    assert get_experiment(client, slug, "reference")["parents"] == [concluded["version_id"]]
    assert [item["id"] for item in list_experiments(client, slug)["items"]] == ["reference"]
