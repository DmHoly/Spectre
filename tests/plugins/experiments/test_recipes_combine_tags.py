from __future__ import annotations

from support.experiments import (
    add_evidence,
    conclude,
    experiment_url,
    get_experiment,
    launch,
    launch_campaign,
    merge,
    process,
    tag,
    upload_image,
)
from support.microprojects import signup_with_microproject
from support.structures import steps


def test_merging_two_lines_keeps_the_base_structure_and_links_the_other(client):
    slug = signup_with_microproject(client, "combine@example.com")
    a = launch(client, slug, title="Piste A", intent="Depart A", steps=steps(20), hypothesis="A tient")
    b = launch(client, slug, title="Piste B", intent="Depart B", steps=steps(40), entities=[{"sample_id": "W2"}])

    response = client.post(f"{experiment_url(slug, a['id'])}/merges", json={"other_experiment_id": b["id"]})
    assert response.status_code == 201
    merged = response.json()
    assert response.headers["Location"] == f"{experiment_url(slug, a['id'])}/versions/{merged['version_id']}"
    assert merged["id"] == a["id"]
    assert merged["parents"] == [a["version_id"], b["version_id"]]
    assert (merged["title"], merged["hypothesis"]) == ("Piste A", "A tient")  # tout le parent reporté
    assert {r["role"]: r["experiment_id"] for r in merged["references"]} == {"baseline": a["version_id"], "merge_source": b["version_id"]}
    # kept A's structure/steps (the default, conflict-free behaviour)
    assert process(client, slug, a["id"])["steps"][0]["thickness"]["value"] == 20
    assert get_experiment(client, slug, b["id"])["version_id"] == b["version_id"]  # B continue d'exister


def test_merging_keeps_the_evidence_of_both_sides_without_orphans(client):
    slug = signup_with_microproject(client, "combine-evidence@example.com")
    a = launch(client, slug, title="Piste A", intent="Depart A")
    b = launch(client, slug, title="Piste B", intent="Depart B", entities=[{"sample_id": "W2"}])
    on_a = add_evidence(client, slug, a["id"], "Mesure A", links=["https://a.example/1"], interpretation="A")
    image_id = upload_image(client, slug)
    on_b = add_evidence(client, slug, b["id"], "Image B", links=["https://b.example/2"], images=[{"image_id": image_id}], interpretation="B")

    merged = merge(client, slug, a["id"], b["id"])
    evidence = {e["id"]: e for e in merged["evidence"]}
    assert list(evidence) == [on_a["evidence_id"], on_b["evidence_id"]]
    assert evidence[on_b["evidence_id"]]["kind"] == "image" and evidence[on_b["evidence_id"]]["interpretation"] == "B"
    assert evidence[on_a["evidence_id"]]["interpretation"] == "A"
    assert merged["evidence_links"] == {on_a["evidence_id"]: ["https://a.example/1"], on_b["evidence_id"]: ["https://b.example/2"]}
    assert [(att["id"], att["evidence_id"]) for att in merged["attachments"]] == [(image_id, on_b["evidence_id"])]

    # fusionner encore la même piste ne duplique rien
    again = merge(client, slug, a["id"], b["id"])
    assert [e["id"] for e in again["evidence"]] == [on_a["evidence_id"], on_b["evidence_id"]]
    assert len(again["attachments"]) == 1


def test_merging_purges_metadata_that_points_at_a_missing_evidence():
    import follow

    from spectre.plugins.experiments.service import _merge_evidence

    repo = follow.Repository()
    builder = repo.new(branch="a", structure=follow.Structure(), title="A", intent="x")
    builder.evidence = [follow.Evidence(id="ev-a", description="A", source="s")]
    builder.metadata = {
        "evidence_extra": {"ev-a": {"kind": "standard"}, "ev-perdue": {"kind": "image"}},
        "attachments": [{"id": "att", "evidence_id": "ev-perdue"}, {"id": "etude", "evidence_id": None}],
    }
    other = repo.new(branch="b", structure=follow.Structure(), title="B", intent="y").commit()

    _merge_evidence(builder, other)
    assert builder.metadata == {"evidence_extra": {"ev-a": {"kind": "standard"}}, "attachments": [{"id": "etude", "evidence_id": None}]}


def test_merging_rejects_merging_a_line_with_itself(client):
    slug = signup_with_microproject(client, "combineself@example.com")
    a = launch(client, slug, title="Solo", intent="Depart")
    response = client.post(f"{experiment_url(slug, a['id'])}/merges", json={"other_experiment_id": a["id"]})
    assert response.status_code == 422
    assert response.json()["code"] == "same_experiment"


def test_merging_rejects_a_single_experiment_with_a_campaign(client):
    slug = signup_with_microproject(client, "combinetypes@example.com")
    single = launch(client, slug, title="Solo", intent="Depart")
    campaign = launch_campaign(client, slug, intent="Balayage", entities=[{"sample_id": "placeholder"}])
    response = client.post(f"{experiment_url(slug, single['id'])}/merges", json={"other_experiment_id": campaign["id"]})
    assert response.status_code == 422
    assert get_experiment(client, slug, single["id"])["version_id"] == single["version_id"]


def test_setting_and_removing_tags_records_a_new_version_and_preserves_status(client):
    slug = signup_with_microproject(client, "tags@example.com")
    launched = launch(client, slug, title="Reference", intent="Depart")

    response = client.put(f"{experiment_url(slug, launched['id'])}/tags", json={"tags": ["a valider", "prioritaire", "a valider", " "]})
    assert response.status_code == 200
    tagged = response.json()
    assert tagged["tags"] == ["a valider", "prioritaire"]
    assert tagged["version_id"] != launched["version_id"]
    assert tagged["status"] == "draft"  # tagging must not change the status

    assert tag(client, slug, launched["id"], ["prioritaire"])["tags"] == ["prioritaire"]


def test_adding_evidence_or_concluding_preserves_existing_tags(client):
    slug = signup_with_microproject(client, "tagscarry@example.com")
    launched = launch(client, slug, title="Reference", intent="Depart")
    tag(client, slug, launched["id"], ["important"])

    add_evidence(client, slug, launched["id"], source="profilometre")
    assert get_experiment(client, slug, launched["id"])["tags"] == ["important"]

    concluded = conclude(client, slug, launched["id"], summary="Fini", objective_results=[])
    assert concluded["tags"] == ["important"]
    assert concluded["status"] == "concluded"


def test_concluding_does_not_reset_status_of_a_later_evidence_addition(client):
    # regression: add_evidence used to leave `conclusion` at its fresh default, silently
    # un-concluding an already-concluded experience the moment evidence was attached to it.
    slug = signup_with_microproject(client, "statuscarry@example.com")
    launched = launch(client, slug, title="Reference", intent="Depart")
    assert conclude(client, slug, launched["id"], summary="Fini", objective_results=[])["status"] == "concluded"

    add_evidence(client, slug, launched["id"], "Mesure tardive", source="profilometre")
    assert get_experiment(client, slug, launched["id"])["status"] == "concluded"
