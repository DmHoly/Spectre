from __future__ import annotations

from support.accounts import signup
from support.experiments import combine, conclude, evolve, get_experience, launch, lineage, set_status, tag
from support.microprojects import signup_with_microproject
from support.structures import steps


def _owner_microproject(client):
    return signup_with_microproject(client, "owner@example.com", "Salle blanche", name="Owner")


def test_lineage_on_empty_microproject(client):
    slug = _owner_microproject(client)
    response = client.get(f"/api/microprojets/{slug}/filiation")
    assert response.status_code == 200
    assert response.json() == {"nodes": [], "edges": []}


def test_lineage_single_experience_is_a_root_and_a_tip(client):
    slug = _owner_microproject(client)
    launched = launch(client, slug)

    body = lineage(client, slug)
    assert body["edges"] == []
    assert len(body["nodes"]) == 1
    node = body["nodes"][0]
    assert node["id"] == launched["id"]
    assert node["title"] == "Essai"
    assert node["status"] == "draft"
    assert node["is_tip"] is True
    assert node["is_merge"] is False


def test_lineage_collapses_a_tag_only_commit_but_keeps_the_edge(client):
    slug = _owner_microproject(client)
    launched = launch(client, slug)
    tagged = tag(client, slug, launched["id"], ["a-suivre"])
    evolved = evolve(client, slug, tagged["id"], intent="Doubler l'epaisseur", steps=steps(40), objectives=[])

    body = lineage(client, slug)
    ids = {n["id"] for n in body["nodes"]}
    # the tag-only commit moved nothing structural forward - collapsed out of the graph entirely.
    assert tagged["id"] not in ids
    assert ids == {launched["id"], evolved["id"]}
    assert {"parent": launched["id"], "child": evolved["id"]} in body["edges"]

    evolved_node = next(n for n in body["nodes"] if n["id"] == evolved["id"])
    assert evolved_node["is_tip"] is True
    launched_node = next(n for n in body["nodes"] if n["id"] == launched["id"])
    assert launched_node["is_tip"] is False


def test_lineage_marks_a_combined_experience_as_a_merge(client):
    slug = _owner_microproject(client)
    a = launch(client, slug, title="A", intent="Piste A")
    b = launch(client, slug, title="B", intent="Piste B", steps=steps(30), entities=[{"sample_id": "W2"}])
    combined = combine(client, slug, a["id"], b["id"], title="Synthese A+B", intent="Regrouper les deux pistes")

    body = lineage(client, slug)
    combined_node = next(n for n in body["nodes"] if n["id"] == combined["id"])
    assert combined_node["is_merge"] is True
    parents = {e["parent"] for e in body["edges"] if e["child"] == combined["id"]}
    assert parents == {a["id"], b["id"]}


def test_lineage_does_not_spawn_a_node_for_a_pure_status_change(client):
    # the bug report: changing only the status (no structural edit) must update the existing
    # node in place, not add a new one.
    slug = _owner_microproject(client)
    launched = launch(client, slug)

    assert len(lineage(client, slug)["nodes"]) == 1

    changed = set_status(client, slug, launched["id"], "running")
    assert changed["id"] != launched["id"]  # a genuinely new Follow commit, just not a new lineage node

    after = lineage(client, slug)
    assert len(after["nodes"]) == 1
    assert after["edges"] == []
    node = after["nodes"][0]
    assert node["id"] == changed["id"]
    assert node["status"] == "running"
    assert node["is_tip"] is True


def test_lineage_edges_point_at_the_overridden_tip_id_not_the_stale_structural_id(client):
    # regression: a structural node that is *not* a leaf (it has a structural child, so it shows
    # up as a parent in an edge) must still get that edge rewritten to the tip that now displays
    # in its place - the bug only a single-node microproject's empty edge list couldn't catch.
    slug = _owner_microproject(client)
    root = launch(client, slug, title="Racine", intent="Depart")
    child = evolve(client, slug, root["id"], title="Enfant", intent="Epaissir", steps=steps(40), objectives=[])
    changed = set_status(client, slug, child["id"], "running")
    assert changed["id"] != child["id"]

    body = lineage(client, slug)
    ids = {n["id"] for n in body["nodes"]}
    assert ids == {root["id"], changed["id"]}
    assert child["id"] not in ids
    assert {"parent": root["id"], "child": changed["id"]} in body["edges"]
    for edge in body["edges"]:
        assert edge["parent"] in ids and edge["child"] in ids


def test_lineage_does_not_spawn_a_node_for_tags_then_a_status_change(client):
    # several non-structural commits in a row (tag, then status) still collapse onto one node.
    slug = _owner_microproject(client)
    launched = launch(client, slug)
    tagged = tag(client, slug, launched["id"], ["a-suivre"])
    changed = set_status(client, slug, tagged["id"], "running")

    body = lineage(client, slug)
    assert len(body["nodes"]) == 1
    assert body["nodes"][0]["id"] == changed["id"]
    assert body["nodes"][0]["status"] == "running"


def test_lineage_updates_the_existing_node_after_evolving_with_the_same_structure(client):
    # evolve_experience can itself carry no structural change (same substrate/steps) - still no
    # new node, same rule as a plain status/tag edit.
    slug = _owner_microproject(client)
    launched = launch(client, slug)
    evolved = evolve(client, slug, launched["id"], intent="Reverifier", objectives=[])

    body = lineage(client, slug)
    assert len(body["nodes"]) == 1
    assert body["nodes"][0]["id"] == evolved["id"]
    assert body["edges"] == []


def test_non_member_cannot_see_lineage(client):
    slug = _owner_microproject(client)
    signup(client, "stranger@example.com", name="S")
    response = client.get(f"/api/microprojets/{slug}/filiation")
    assert response.status_code == 403


def test_lineage_nodes_carry_when_the_experiment_started_and_ended(client):
    # the elapsed time shown under each node: from the experiment's creation to its conclusion,
    # or no end yet (« depuis… ») while it is still a draft or running.
    slug = _owner_microproject(client)
    launched = launch(client, slug)
    node = lineage(client, slug)["nodes"][0]
    assert node["started_at"] == node["created_at"]
    assert node["ended_at"] is None

    concluded = conclude(client, slug, launched["id"], decision="promote", summary="OK")
    node = lineage(client, slug)["nodes"][0]
    assert node["id"] == concluded["id"]
    assert node["started_at"] < node["created_at"]  # still the launch, not the conclusion commit
    assert node["ended_at"] is not None and node["ended_at"] >= node["started_at"]


def test_lineage_node_records_when_its_work_was_continued(client):
    # a draft never concluded but evolved into a new structure stops counting time at its suite.
    slug = _owner_microproject(client)
    root = launch(client, slug)
    child = evolve(client, slug, root["id"], title="Essai 2", intent="Plus epais", steps=steps(thickness_nm=40), objectives=[])

    nodes = {n["id"]: n for n in lineage(client, slug)["nodes"]}
    assert nodes[root["id"]]["continued_at"] == nodes[child["id"]]["started_at"]
    assert nodes[child["id"]]["continued_at"] is None


def test_a_study_can_be_paused_and_resumed(client):
    # « hold » is Spectre's own status: Follow keeps the study running, the pause rides in metadata.
    slug = _owner_microproject(client)
    launched = launch(client, slug)
    running = set_status(client, slug, launched["id"], "running")
    held = set_status(client, slug, running["id"], "hold", reason="Bâti MOCVD en maintenance")

    detail = get_experience(client, slug, held["id"])
    assert detail["status"] == "hold"
    assert detail["hold"]["reason"] == "Bâti MOCVD en maintenance" and detail["hold"]["by"] == "Owner"
    node = lineage(client, slug)["nodes"][0]
    assert node["status"] == "hold" and node["hold"]["since"] and node["ended_at"] is None
    listed = client.get(f"/api/microprojets/{slug}/experiences?status=running").json()["items"]
    assert [e["status"] for e in listed] == ["hold"]  # still among the studies in progress

    resumed = set_status(client, slug, held["id"], "running")
    detail = get_experience(client, slug, resumed["id"])
    assert detail["status"] == "running" and detail["hold"] is None


def test_a_concluded_study_cannot_be_paused_and_concluding_lifts_the_pause(client):
    slug = _owner_microproject(client)
    launched = launch(client, slug)
    held = set_status(client, slug, launched["id"], "hold")
    concluded = conclude(client, slug, held["id"], decision="promote")
    detail = get_experience(client, slug, concluded["id"])
    assert detail["status"] == "concluded" and detail["hold"] is None
    refused = client.post(f"/api/microprojets/{slug}/experiences/{concluded['id']}/statut", json={"status": "hold"})
    assert refused.status_code == 422


def test_a_draft_taken_up_by_a_new_version_is_continued(client):
    slug = _owner_microproject(client)
    root = launch(client, slug)
    child = evolve(client, slug, root["id"], title="Essai 2", intent="Plus epais", steps=steps(thickness_nm=40), objectives=[])

    nodes = {n["id"]: n for n in lineage(client, slug)["nodes"]}
    assert nodes[root["id"]]["status"] == "continued"
    assert nodes[child["id"]]["status"] == "draft"
    assert get_experience(client, slug, root["id"])["status"] == "continued"


def test_lineage_nodes_list_the_wafers_they_track(client):
    # the « N wafers » badge left of each node: its tracked lasermarks, without duplicates
    slug = _owner_microproject(client)
    launch(client, slug)
    assert lineage(client, slug)["nodes"][0]["wafers"] == ["W1"]

