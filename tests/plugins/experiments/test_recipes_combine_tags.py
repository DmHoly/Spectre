from __future__ import annotations

from support.experiments import (
    conclude,
    experiment_url,
    get_experiment,
    launch,
    launch_campaign,
    merge,
    process,
    tag,
)
from support.microprojects import signup_with_microproject
from support.notebook import add_manual, entries_by_id, legacy_evidence, upload_notebook_file, write_legacy
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


def test_merging_keeps_the_notebook_of_both_sides_without_duplicates(client):
    slug = signup_with_microproject(client, "combine-evidence@example.com")
    a = launch(client, slug, title="Piste A", intent="Depart A")
    b = launch(client, slug, title="Piste B", intent="Depart B", entities=[{"sample_id": "W2"}])
    on_a = add_manual(client, slug, a["id"], "Mesure A", measurements=[{"links": [{"url": "https://a.example/1"}]}], interpretation="A")
    image_id = upload_notebook_file(client, slug)
    on_b = add_manual(client, slug, b["id"], "Image B", measurements=[{"links": [{"url": "https://b.example/2"}], "attachments": [image_id]}], interpretation="B")

    merged = merge(client, slug, a["id"], b["id"])
    assert merged["notebook_count"] == 2
    notebook = entries_by_id(client, slug, a["id"])
    assert list(notebook) == [on_a["id"], on_b["id"]]
    assert notebook[on_b["id"]]["interpretation"] == "B" and notebook[on_a["id"]]["interpretation"] == "A"
    assert {key: [link["url"] for link in e["measurements"][0]["links"]] for key, e in notebook.items()} == {
        on_a["id"]: ["https://a.example/1"],
        on_b["id"]: ["https://b.example/2"],
    }
    assert [image["id"] for image in notebook[on_b["id"]]["measurements"][0]["attachments"]] == [image_id]

    # fusionner encore la même piste ne duplique rien
    merge(client, slug, a["id"], b["id"])
    again = entries_by_id(client, slug, a["id"])
    assert list(again) == [on_a["id"], on_b["id"]]
    assert [image["id"] for e in again.values() for image in e["measurements"][0]["attachments"]] == [image_id]


def test_merging_dedupes_entries_whatever_format_each_side_keeps_them_in(client):
    """Deux pistes nées de la même version gardent ses preuves : l'une les a converties dans le cahier
    (une écriture), l'autre pas. Une fusion, dans un sens comme dans l'autre, ne les double pas, et
    la version de cette piste l'emporte."""
    slug = signup_with_microproject(client, "combine-formats@example.com")
    a = launch(client, slug, title="Piste A", intent="Depart A")
    write_legacy(slug, a["id"], lambda builder, parent: legacy_evidence(builder, "ev-commune", "Mesure commune", interpretation="d'origine"))
    b = launch(client, slug, title="Piste B", intent="Depart B", from_version={"experiment_id": a["id"]})
    write_legacy(slug, b["id"], lambda builder, parent: legacy_evidence(builder, "ev-commune", "Mesure commune", interpretation="d'origine"))
    # A écrit dans son cahier : la preuve y est convertie, modifiée ici
    from support.notebook import update_entry

    update_entry(client, slug, a["id"], "ev-commune", interpretation="revue sur A")
    only_b = add_manual(client, slug, b["id"], "Propre à B")

    merge(client, slug, a["id"], b["id"])
    notebook = entries_by_id(client, slug, a["id"])
    assert list(notebook) == ["ev-commune", only_b["id"]]
    assert notebook["ev-commune"]["interpretation"] == "revue sur A"  # celle de cette piste

    # dans l'autre sens : B garde sa preuve d'avant, A n'y ajoute que ce que B n'a pas
    merge(client, slug, b["id"], a["id"])
    notebook = entries_by_id(client, slug, b["id"])
    assert sorted(notebook) == sorted(["ev-commune", only_b["id"]])
    assert notebook["ev-commune"]["interpretation"] == "d'origine"


def test_merging_purges_metadata_that_points_at_a_missing_evidence():
    import follow

    from spectre.plugins.experiments.service import _merge_notebook

    repo = follow.Repository()
    builder = repo.new(branch="a", structure=follow.Structure(), title="A", intent="x")
    builder.evidence = [follow.Evidence(id="ev-a", description="A", source="s")]
    builder.metadata = {
        "evidence_extra": {"ev-a": {"kind": "standard"}, "ev-perdue": {"kind": "image"}},
        "attachments": [{"id": "att", "evidence_id": "ev-perdue"}, {"id": "etude", "evidence_id": None}],
    }
    other = repo.new(branch="b", structure=follow.Structure(), title="B", intent="y").commit()

    _merge_notebook(builder, other)
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


def test_adding_a_notebook_entry_or_concluding_preserves_existing_tags(client):
    slug = signup_with_microproject(client, "tagscarry@example.com")
    launched = launch(client, slug, title="Reference", intent="Depart")
    tag(client, slug, launched["id"], ["important"])

    add_manual(client, slug, launched["id"], measurements=[{"text": "profilometre"}])
    assert get_experiment(client, slug, launched["id"])["tags"] == ["important"]

    concluded = conclude(client, slug, launched["id"], summary="Fini", objective_results=[])
    assert concluded["tags"] == ["important"]
    assert concluded["status"] == "concluded"


def test_concluding_does_not_reset_status_of_a_later_notebook_entry(client):
    # regression: adding evidence used to leave `conclusion` at its fresh default, silently
    # un-concluding an already-concluded experience the moment evidence was attached to it.
    slug = signup_with_microproject(client, "statuscarry@example.com")
    launched = launch(client, slug, title="Reference", intent="Depart")
    assert conclude(client, slug, launched["id"], summary="Fini", objective_results=[])["status"] == "concluded"

    add_manual(client, slug, launched["id"], "Mesure tardive", measurements=[{"text": "profilometre"}])
    assert get_experiment(client, slug, launched["id"])["status"] == "concluded"
