from __future__ import annotations

from support.accounts import signup
from support.experiments import (
    conclude,
    evolve,
    experiment_url,
    get_experiment,
    get_version,
    launch,
    lineage,
    list_experiments,
    set_status,
    tag,
    write_old_merge,
)
from support.microprojects import signup_with_microproject
from support.structures import steps


def _owner_microproject(client):
    return signup_with_microproject(client, "owner@example.com", "Salle blanche", name="Owner")


def test_lineage_on_empty_microproject(client):
    slug = _owner_microproject(client)
    assert lineage(client, slug) == {"nodes": [], "edges": [], "plans": []}


def test_lineage_single_experiment_is_a_root_and_a_tip(client):
    slug = _owner_microproject(client)
    launched = launch(client, slug)

    body = lineage(client, slug)
    assert body["edges"] == []
    assert len(body["nodes"]) == 1
    node = body["nodes"][0]
    assert node["id"] == node["version_id"] == launched["version_id"]
    assert node["experiment_id"] == launched["id"]
    assert node["title"] == "Essai"
    assert node["status"] == "draft"
    assert node["is_tip"] is True
    assert node["is_merge"] is False


def test_lineage_collapses_a_tag_only_commit_but_keeps_the_edge(client):
    slug = _owner_microproject(client)
    launched = launch(client, slug)
    tagged = tag(client, slug, launched["id"], ["a-suivre"])
    evolved = evolve(client, slug, launched["id"], intent="Doubler l'epaisseur", steps=steps(40))

    body = lineage(client, slug)
    ids = {n["id"] for n in body["nodes"]}
    # the tag-only commit moved nothing structural forward - collapsed out of the graph entirely.
    assert tagged["version_id"] not in ids
    assert ids == {launched["version_id"], evolved["version_id"]}
    assert {"parent": launched["version_id"], "child": evolved["version_id"]} in body["edges"]

    nodes = {n["id"]: n for n in body["nodes"]}
    assert nodes[evolved["version_id"]]["is_tip"] is True
    assert nodes[launched["version_id"]]["is_tip"] is False
    assert {n["experiment_id"] for n in body["nodes"]} == {launched["id"]}  # une seule piste


def test_lineage_marks_an_old_merge_as_a_merge(client):
    # une fusion d'avant (une version de la piste à deux parents) ; une combinaison d'aujourd'hui,
    # une nouvelle piste : test_combine.py
    slug = _owner_microproject(client)
    a = launch(client, slug, title="A", intent="Piste A")
    b = launch(client, slug, title="B", intent="Piste B", steps=steps(30), entities=[{"sample_id": "W2"}])
    merged_id = write_old_merge(slug, a["id"], b["id"])
    merged = get_experiment(client, slug, a["id"])
    assert merged["version_id"] == merged_id
    assert merged["parents"] == [a["version_id"], b["version_id"]]

    body = lineage(client, slug)
    merged_node = next(n for n in body["nodes"] if n["id"] == merged_id)
    assert merged_node["is_merge"] is True
    parents = {e["parent"] for e in body["edges"] if e["child"] == merged_id}
    assert parents == {a["version_id"], b["version_id"]}


def test_lineage_does_not_spawn_a_node_for_a_pure_status_change(client):
    # the bug report: changing only the status (no structural edit) must update the existing
    # node in place, not add a new one.
    slug = _owner_microproject(client)
    launched = launch(client, slug)

    assert len(lineage(client, slug)["nodes"]) == 1

    changed = set_status(client, slug, launched["id"], "running")
    assert changed["version_id"] != launched["version_id"]  # a genuinely new Follow commit, just not a new lineage node

    after = lineage(client, slug)
    assert len(after["nodes"]) == 1
    assert after["edges"] == []
    node = after["nodes"][0]
    assert node["id"] == changed["version_id"]
    assert node["status"] == "running"
    assert node["is_tip"] is True


def test_lineage_edges_point_at_the_overridden_tip_id_not_the_stale_structural_id(client):
    # regression: a structural node that is *not* a leaf (it has a structural child, so it shows
    # up as a parent in an edge) must still get that edge rewritten to the tip that now displays
    # in its place.
    slug = _owner_microproject(client)
    root = launch(client, slug, title="Racine", intent="Depart")
    child = evolve(client, slug, root["id"], title="Enfant", intent="Epaissir", steps=steps(40))
    changed = set_status(client, slug, root["id"], "running")
    assert changed["version_id"] != child["version_id"]

    body = lineage(client, slug)
    ids = {n["id"] for n in body["nodes"]}
    assert ids == {root["version_id"], changed["version_id"]}
    assert {"parent": root["version_id"], "child": changed["version_id"]} in body["edges"]
    for edge in body["edges"]:
        assert edge["parent"] in ids and edge["child"] in ids


def test_lineage_does_not_spawn_a_node_for_tags_then_a_status_change(client):
    # several non-structural commits in a row (tag, then status) still collapse onto one node.
    slug = _owner_microproject(client)
    launched = launch(client, slug)
    tag(client, slug, launched["id"], ["a-suivre"])
    changed = set_status(client, slug, launched["id"], "running")

    body = lineage(client, slug)
    assert len(body["nodes"]) == 1
    assert body["nodes"][0]["id"] == changed["version_id"]
    assert body["nodes"][0]["status"] == "running"


def test_lineage_updates_the_existing_node_after_evolving_with_the_same_structure(client):
    # an evolution can itself carry no structural change (same substrate/steps) - still no new
    # node, same rule as a plain status/tag edit.
    slug = _owner_microproject(client)
    launched = launch(client, slug)
    evolved = evolve(client, slug, launched["id"], intent="Reverifier")

    body = lineage(client, slug)
    assert len(body["nodes"]) == 1
    assert body["nodes"][0]["id"] == evolved["version_id"]
    assert body["edges"] == []


def test_non_member_cannot_see_lineage(client):
    slug = _owner_microproject(client)
    signup(client, "stranger@example.com", name="S")
    assert client.get(f"/api/microprojects/{slug}/lineage").status_code == 403


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
    assert node["id"] == concluded["version_id"]
    assert node["started_at"] < node["created_at"]  # still the launch, not the conclusion commit
    assert node["ended_at"] is not None and node["ended_at"] >= node["started_at"]


def test_lineage_node_records_when_its_work_was_continued(client):
    # a draft never concluded but evolved into a new structure stops counting time at its suite.
    slug = _owner_microproject(client)
    root = launch(client, slug)
    child = evolve(client, slug, root["id"], title="Essai 2", intent="Plus epais", steps=steps(thickness_nm=40))

    nodes = {n["id"]: n for n in lineage(client, slug)["nodes"]}
    assert nodes[root["version_id"]]["continued_at"] == nodes[child["version_id"]]["started_at"]
    assert nodes[child["version_id"]]["continued_at"] is None


def test_a_study_can_be_paused_and_resumed(client):
    # « hold » is Spectre's own status: Follow keeps the study running, the pause rides in metadata.
    slug = _owner_microproject(client)
    launched = launch(client, slug)
    set_status(client, slug, launched["id"], "running")
    held = set_status(client, slug, launched["id"], "hold", hold_reason="Bâti MOCVD en maintenance")

    assert held["status"] == "hold"
    assert held["hold"]["reason"] == "Bâti MOCVD en maintenance" and held["hold"]["by"] == "Owner"
    node = lineage(client, slug)["nodes"][0]
    assert node["status"] == "hold" and node["hold"]["since"] and node["ended_at"] is None
    listed = list_experiments(client, slug, status="running")["items"]
    assert [e["status"] for e in listed] == ["hold"]  # still among the studies in progress

    resumed = set_status(client, slug, launched["id"], "running")
    assert resumed["status"] == "running" and resumed["hold"] is None


def test_a_concluded_study_cannot_be_paused_and_concluding_lifts_the_pause(client):
    slug = _owner_microproject(client)
    launched = launch(client, slug)
    set_status(client, slug, launched["id"], "hold")
    concluded = conclude(client, slug, launched["id"], decision="promote")
    assert concluded["status"] == "concluded" and concluded["hold"] is None
    refused = client.put(f"{experiment_url(slug, launched['id'])}/status", json={"status": "hold"})
    assert refused.status_code == 422


def test_a_draft_taken_up_by_a_new_version_is_continued(client):
    slug = _owner_microproject(client)
    root = launch(client, slug)
    child = evolve(client, slug, root["id"], title="Essai 2", intent="Plus epais", steps=steps(thickness_nm=40))

    nodes = {n["id"]: n for n in lineage(client, slug)["nodes"]}
    assert nodes[root["version_id"]]["status"] == "continued"
    assert nodes[child["version_id"]]["status"] == "draft"
    assert get_version(client, slug, root["id"], root["version_id"])["status"] == "continued"
    assert get_experiment(client, slug, root["id"])["status"] == "draft"  # la pointe, elle, ne l'est pas


def test_a_tag_does_not_make_a_draft_continued(client):
    slug = _owner_microproject(client)
    root = launch(client, slug)
    tag(client, slug, root["id"], ["x"])
    assert get_version(client, slug, root["id"], root["version_id"])["continued_at"] is None


def test_lineage_nodes_list_the_wafers_they_track(client):
    # the « N wafers » badge left of each node: its tracked lasermarks, without duplicates
    slug = _owner_microproject(client)
    launch(client, slug)
    assert lineage(client, slug)["nodes"][0]["wafers"] == ["W1"]


def test_lineage_nodes_count_their_places_for_the_plate_badge(client):
    # the plate badge: every place (blank ones included), how many are named, and whether the study
    # has its FDL - red (to associate, no FDL), orange (FDL given), green (all associated)
    slug = _owner_microproject(client)
    launch(client, slug, entities=[{"sample_id": "W1"}, {"sample_id": None}, {"sample_id": None}])
    assert lineage(client, slug)["nodes"][0]["plates"] == {"total": 3, "named": 1, "has_fdl": False}

    other = signup_with_microproject(client, "other@example.com", "Autre salle", name="Other")
    launch(client, other, entities=[{"sample_id": None}], fdl=["1234"])
    assert lineage(client, other)["nodes"][0]["plates"] == {"total": 1, "named": 0, "has_fdl": True}


def test_a_concluded_reference_continued_by_a_study_with_the_same_structure_is_one_node(client):
    # la référence conclue (une version sans changement de structure), puis une étude qui en part
    # sans changer la structure (ses variations sont dans son plan) : la référence ne s'affiche
    # qu'une fois - son bout conclu - et la nouvelle étude en part
    slug = _owner_microproject(client)
    root = launch(client, slug, title="Référence")
    concluded = conclude(client, slug, root["id"], decision="promote")
    study = launch(client, slug, title="Variation", from_version={"experiment_id": root["id"]})

    body = lineage(client, slug)
    nodes = {n["id"]: n for n in body["nodes"]}
    assert set(nodes) == {concluded["version_id"], study["version_id"]}
    assert nodes[concluded["version_id"]]["status"] == "concluded"
    assert body["edges"] == [{"parent": concluded["version_id"], "child": study["version_id"]}]
