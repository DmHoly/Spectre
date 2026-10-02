"""list_experiences()/microproject counts show one card per branch (its current tip), not every
version ever committed to it - conclure/preuves/etiquettes each record a new version (experiments
are immutable), so without this a single study kept showing up multiple times, drafts included,
even once concluded.
"""

from __future__ import annotations

from support.experiments import add_evidence, conclude, evolve, launch
from support.microprojects import signup_with_microproject
from support.structures import steps


def test_evidence_then_conclusion_only_shows_the_final_version_once(client):
    slug = signup_with_microproject(client, "tips-a@example.com")
    launched = launch(client, slug, title="Etude", intent="Depart")

    with_evidence = add_evidence(client, slug, launched["id"])
    concluded = conclude(client, slug, with_evidence["id"])

    listed = client.get(f"/api/microprojets/{slug}/experiences?status=all&limit=50").json()
    matching = [item for item in listed["items"] if item["title"] == "Etude"]
    assert len(matching) == 1
    assert matching[0]["id"] == concluded["id"]
    assert matching[0]["status"] == "concluded"

    # and it must not also appear under "running" - only its (now superseded) drafts were ever running
    running = client.get(f"/api/microprojets/{slug}/experiences?status=running&limit=50").json()
    assert launched["id"] not in [item["id"] for item in running["items"]]
    assert with_evidence["id"] not in [item["id"] for item in running["items"]]


def test_microproject_counts_reflect_one_status_per_branch(client):
    slug = signup_with_microproject(client, "tips-b@example.com")
    launched = launch(client, slug, title="Etude", intent="Depart")
    with_evidence = add_evidence(client, slug, launched["id"])
    conclude(client, slug, with_evidence["id"])

    payload = client.get(f"/api/microprojets/{slug}").json()
    assert payload["running_count"] == 0
    assert payload["concluded_count"] == 1


def test_a_fork_still_shows_both_branches_once_each(client):
    slug = signup_with_microproject(client, "tips-c@example.com")
    launched = launch(client, slug, title="Reference", intent="Depart", steps=steps(20))
    continued = evolve(client, slug, launched["id"], title="Reference", intent="Suite", steps=steps(15))
    forked = evolve(client, slug, launched["id"], title="Piste epaisse", intent="Variante", steps=steps(30), new_branch="piste-epaisse")

    listed = client.get(f"/api/microprojets/{slug}/experiences?status=all&limit=50").json()
    ids = {item["id"] for item in listed["items"]}
    assert continued["id"] in ids
    assert forked["id"] in ids
    assert launched["id"] not in ids  # superseded by "continued" on the same branch
