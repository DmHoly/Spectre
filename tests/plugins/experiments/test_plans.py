"""Les expériences prévisionnelles (``/experiment-plans``) : prévues depuis l'arbre d'un µprojet - un
titre, une intention et ce qu'elles continuent (des plaques de la version de départ, ou un nombre
estimé de nouvelles plaques) -, sans structure ni split. L'arbre (``GET .../lineage``) les montre,
accrochées au nœud de leur version de départ ; lancées (``plan_id``), elles cessent d'être prévues."""

from __future__ import annotations

from support.experiments import evolve, launch, launch_body, launch_campaign, lineage, tag
from support.http import assert_created, assert_ok
from support.microprojects import join_as, signup_with_microproject
from support.structures import steps


def _plans_url(slug: str) -> str:
    return f"/api/microprojects/{slug}/experiment-plans"


def _plan(client, slug, **body):
    return assert_created(client.post(_plans_url(slug), json={"title": "Suite", "intent": "Voir", **body}))


def test_a_root_plan_forecasts_new_wafers(client):
    slug = signup_with_microproject(client, "plans-root@example.com", "Prévisions")
    plan = _plan(client, slug, title="Premier run", wafer_count=6)
    assert plan["mode"] == "new_wafers" and plan["wafer_count"] == 6 and plan["parent"] is None and plan["wafers"] == []

    graph = lineage(client, slug)
    assert graph["nodes"] == [] and [(p["id"], p["parent_node"]) for p in graph["plans"]] == [(plan["id"], None)]

    missing = client.post(_plans_url(slug), json={"title": "Sans nombre"})
    assert missing.status_code == 422 and missing.json()["code"] == "wafer_count_required"
    no_parent = client.post(_plans_url(slug), json={"title": "Mêmes plaques ?", "mode": "same_wafers", "wafers": ["W1"]})
    assert no_parent.status_code == 422 and no_parent.json()["code"] == "parent_required"
    blank = client.post(_plans_url(slug), json={"title": "  ", "wafer_count": 2})
    assert blank.status_code == 422 and blank.json()["code"] == "title_required"


def test_a_plan_on_the_same_wafers_takes_some_of_the_parents(client):
    slug = signup_with_microproject(client, "plans-same@example.com", "Prévisions")
    study = launch(client, slug, title="Épitaxie", entities=[{"sample_id": "W1"}, {"sample_id": "W2"}, {"sample_id": "W3"}])
    plan = _plan(client, slug, parent={"experiment_id": study["id"]}, mode="same_wafers", wafers=["w-2", "W3", "W2"])
    assert plan["wafers"] == ["w-2", "W3"] and plan["wafer_count"] is None
    assert plan["parent"] == {"experiment_id": study["id"], "version_id": study["version_id"]}

    unknown = client.post(_plans_url(slug), json={"title": "x", "parent": {"experiment_id": study["id"]}, "mode": "same_wafers", "wafers": ["W9"]})
    assert unknown.status_code == 422 and unknown.json()["code"] == "wafer_not_in_origin"
    none = client.post(_plans_url(slug), json={"title": "x", "parent": {"experiment_id": study["id"]}, "mode": "same_wafers", "wafers": []})
    assert none.status_code == 422 and none.json()["code"] == "entity_required"
    lost = client.post(_plans_url(slug), json={"title": "x", "parent": {"experiment_id": "nope"}, "wafer_count": 2})
    assert lost.status_code == 404 and lost.json()["code"] == "source_not_found"


def test_a_plan_hangs_from_the_node_of_its_version(client):
    slug = signup_with_microproject(client, "plans-node@example.com", "Prévisions")
    study = launch(client, slug, title="Épitaxie")
    first = study["version_id"]
    plan = _plan(client, slug, parent={"experiment_id": study["id"], "version_id": first}, wafer_count=4)
    # une version sans changement de structure : le même nœud, qui montre la pointe
    tagged = tag(client, slug, study["id"], ["run"])
    graph = lineage(client, slug)
    assert [n["id"] for n in graph["nodes"]] == [tagged["version_id"]]
    assert graph["plans"][0]["parent_node"] == tagged["version_id"] and graph["plans"][0]["parent"]["version_id"] == first

    # la structure avance : la version de départ reste son propre nœud
    moved = evolve(client, slug, study["id"], steps=steps(thickness_nm=50))
    graph = lineage(client, slug)
    assert {n["id"] for n in graph["nodes"]} == {first, moved["version_id"]}
    assert graph["plans"][0]["parent_node"] == first
    assert plan["id"] == graph["plans"][0]["id"]


def test_a_campaign_plan_keeps_to_one_variant(client):
    slug = signup_with_microproject(client, "plans-campaign@example.com", "Prévisions")
    campaign = launch_campaign(client, slug, entities=[{"sample_id": "A"}, {"sample_id": "B"}, {"sample_id": "C"}])
    ok = _plan(client, slug, parent={"experiment_id": campaign["id"]}, mode="same_wafers", wafers=["B"])
    assert ok["wafers"] == ["B"]
    mixed = client.post(_plans_url(slug), json={"title": "x", "parent": {"experiment_id": campaign["id"]}, "mode": "same_wafers", "wafers": ["A", "B"]})
    assert mixed.status_code == 422 and mixed.json()["code"] == "wafers_different_structures"


def test_a_plan_is_edited_and_removed(client):
    slug = signup_with_microproject(client, "plans-edit@example.com", "Prévisions")
    study = launch(client, slug, entities=[{"sample_id": "W1"}, {"sample_id": "W2"}])
    plan = _plan(client, slug, parent={"experiment_id": study["id"]}, wafer_count=3)
    url = f"{_plans_url(slug)}/{plan['id']}"

    renamed = assert_ok(client.patch(url, json={"title": "Recuit", "intent": "Activer le Mg", "wafer_count": 5}))
    assert (renamed["title"], renamed["intent"], renamed["wafer_count"]) == ("Recuit", "Activer le Mg", 5)
    same = assert_ok(client.patch(url, json={"mode": "same_wafers", "wafers": ["W2"]}))
    assert same["mode"] == "same_wafers" and same["wafers"] == ["W2"] and same["wafer_count"] is None
    back = client.patch(url, json={"mode": "new_wafers"})
    assert back.status_code == 422 and back.json()["code"] == "wafer_count_required"
    assert assert_ok(client.patch(url, json={"mode": "new_wafers", "wafer_count": 2}))["wafers"] == []

    assert client.delete(url).status_code == 204
    assert client.get(url).status_code == 404
    assert lineage(client, slug)["plans"] == []


def test_launching_a_plan_ends_it(client):
    slug = signup_with_microproject(client, "plans-launch@example.com", "Prévisions")
    study = launch(client, slug, entities=[{"sample_id": "W1"}])
    plan = _plan(client, slug, parent={"experiment_id": study["id"]}, wafer_count=2)
    body = launch_body(title="Suite", entities=[{"sample_id": "W7"}, {"sample_id": "W8"}], from_version={"experiment_id": study["id"]}, plan_id=plan["id"])
    started = assert_created(client.post(f"/api/microprojects/{slug}/experiments", json=body))
    assert started["parents"] == [study["version_id"]]
    assert [e["sample_id"] for e in started["physical_tracking"]] == ["W7", "W8"]  # ses vraies plaques, sans la prévision
    assert lineage(client, slug)["plans"] == []


def test_a_viewer_sees_plans_but_does_not_plan(client):
    slug = signup_with_microproject(client, "plans-owner@example.com", "Prévisions")
    _plan(client, slug, wafer_count=2)
    join_as(client, slug, "plans-viewer@example.com", owner="plans-owner@example.com")
    assert len(assert_ok(client.get(_plans_url(slug)))["items"]) == 1
    assert client.post(_plans_url(slug), json={"title": "x", "wafer_count": 1}).status_code == 403


def test_a_study_continued_without_changing_the_structure_hangs_from_its_parent(client):
    # des tests supplémentaires sur les mêmes plaques, puis une suite de cette étude : chacune reste
    # sous celle dont elle part, et non sous le dernier changement de structure
    slug = signup_with_microproject(client, "plans-chain@example.com", "Prévisions")
    root = launch(client, slug, title="Épitaxie", entities=[{"sample_id": "W1"}, {"sample_id": "W2"}])
    tests = launch(client, slug, title="Mesures", entities=[{"sample_id": "W2"}], from_version={"experiment_id": root["id"]})
    again = launch(client, slug, title="Mesures bis", entities=[{"sample_id": "W3"}], from_version={"experiment_id": tests["id"]})
    graph = lineage(client, slug)
    edges = {(e["parent"], e["child"]) for e in graph["edges"]}
    assert (root["version_id"], tests["version_id"]) in edges
    assert (tests["version_id"], again["version_id"]) in edges
    assert (root["version_id"], again["version_id"]) not in edges
