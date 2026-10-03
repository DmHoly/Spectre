"""La liste des études et les compteurs d'un µprojet montrent une carte par piste (sa dernière
version), pas chaque version enregistrée - une preuve, une conclusion ou une étiquette en ajoutent
une à chaque fois."""

from __future__ import annotations

from support.experiments import add_evidence, conclude, evolve, launch, list_experiments
from support.microprojects import signup_with_microproject
from support.structures import steps


def test_evidence_then_conclusion_only_shows_the_final_version_once(client):
    slug = signup_with_microproject(client, "tips-a@example.com")
    launched = launch(client, slug, title="Etude", intent="Depart")

    add_evidence(client, slug, launched["id"])
    concluded = conclude(client, slug, launched["id"])

    listed = list_experiments(client, slug, status="all", limit=50)
    assert [(item["id"], item["version_id"], item["status"]) for item in listed["items"]] == [
        (launched["id"], concluded["version_id"], "concluded")
    ]
    # et pas sous « en cours » : seules ses versions dépassées l'étaient
    assert list_experiments(client, slug, status="running", limit=50)["items"] == []


def test_microproject_counts_reflect_one_status_per_branch(client):
    slug = signup_with_microproject(client, "tips-b@example.com")
    launched = launch(client, slug, title="Etude", intent="Depart")
    add_evidence(client, slug, launched["id"])
    conclude(client, slug, launched["id"])

    payload = client.get(f"/api/microprojets/{slug}").json()
    assert payload["running_count"] == 0
    assert payload["concluded_count"] == 1


def test_a_fork_still_shows_both_lines_once_each(client):
    slug = signup_with_microproject(client, "tips-c@example.com")
    launched = launch(client, slug, title="Reference", intent="Depart", steps=steps(20))
    continued = evolve(client, slug, launched["id"], title="Reference", intent="Suite", steps=steps(15))
    forked = launch(
        client,
        slug,
        title="Piste epaisse",
        intent="Variante",
        steps=steps(30),
        branch="piste-epaisse",
        from_version={"experiment_id": launched["id"], "version_id": launched["version_id"]},
    )

    listed = list_experiments(client, slug, status="all", limit=50)
    assert {(item["id"], item["version_id"]) for item in listed["items"]} == {
        (launched["id"], continued["version_id"]),
        (forked["id"], forked["version_id"]),
    }
