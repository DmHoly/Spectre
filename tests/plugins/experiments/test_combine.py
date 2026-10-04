"""Combiner deux études crée une nouvelle étude (POST /experiments avec ``merge_of``) : une nouvelle
piste C dont A et B sont les deux parents, avec la structure combinée (celle de A), son titre, son
intention et une nouvelle plaque ; son cahier démarre vide, sans étiquettes ni conclusion ; A et B
ne bougent pas."""

from __future__ import annotations

from support.accounts import login, signup
from support.experiments import (
    combine,
    conclude,
    experiment_url,
    get_experiment,
    launch,
    launch_campaign,
    lineage,
    list_experiments,
    post_combine,
    process,
    step_ids,
    structure_history,
    tag,
    versions,
)
from support.http import assert_handler_404
from support.microprojects import add_member, signup_with_microproject
from support.notebook import add_manual, entries, entries_by_id, objects_checksums
from support.structures import steps


def _two_studies(client, email="combine@example.com"):
    slug = signup_with_microproject(client, email, "Combinaisons")
    a = launch(
        client, slug, title="Piste A", intent="Depart A", steps=steps(20), hypothesis="A tient", context="Run W40",
        objectives=[{"name": "EQE", "metric": "max_EQE", "verification_method": "Banc EQE"}],
    )
    b = launch(client, slug, title="Piste B", intent="Depart B", steps=steps(40), entities=[{"sample_id": "W2"}])
    return slug, a, b


def test_combining_two_studies_creates_a_new_line_with_both_as_parents(client):
    slug, a, b = _two_studies(client)
    before = objects_checksums(slug)
    a_versions, b_versions = versions(client, slug, a["id"]), versions(client, slug, b["id"])

    response = post_combine(client, slug, a["id"], b["id"], title="Piste C", intent="Réunir A et B", hypothesis="C tient", entities=[{"sample_id": "W9", "location": "boîte 3"}])
    assert response.status_code == 201
    c = response.json()
    assert response.headers["Location"] == experiment_url(slug, c["id"])
    assert response.headers["ETag"] == f'"{c["version_id"]}"'
    assert c["id"] not in (a["id"], b["id"]) and c["id"] == "piste-c"
    assert c["parents"] == [a["version_id"], b["version_id"]]
    assert {r["role"]: r["experiment_id"] for r in c["references"]} == {"baseline": a["version_id"], "merge_source": b["version_id"]}
    assert (c["title"], c["intent"], c["hypothesis"]) == ("Piste C", "Réunir A et B", "C tient")
    assert c["physical_tracking"] == [{"sample_id": "W9", "location": "boîte 3"}]
    # la structure combinée : celle de A, ses étapes gardant leurs ids
    assert process(client, slug, c["id"])["steps"][0]["thickness"]["value"] == 20
    assert step_ids(client, slug, c["id"]) == step_ids(client, slug, a["id"])
    assert c["structure_svg"] == get_experiment(client, slug, a["id"])["structure_svg"]
    # faute de mieux dans la requête, les objectifs et le contexte de A
    assert [o["name"] for o in c["objectives"]] == ["EQE"] and c["objective_verification"] == {"EQE": "Banc EQE"}
    assert c["context"] == "Run W40"
    # une nouvelle étude : rien de commencé
    assert (c["notebook_count"], c["tags"], c["status"], c["conclusion"]["summary"]) == (0, [], "draft", None)
    # son numéro de version : la règle d'une nouvelle piste (celui de la version de départ, A)
    assert versions(client, slug, c["id"])[-1]["version"] == a_versions[-1]["version"]

    # A et B n'ont pas bougé : même pointe, mêmes versions, aucun objet réécrit
    assert get_experiment(client, slug, a["id"])["version_id"] == a["version_id"]
    assert get_experiment(client, slug, b["id"])["version_id"] == b["version_id"]
    assert versions(client, slug, a["id"]) == a_versions and versions(client, slug, b["id"]) == b_versions
    after = objects_checksums(slug)
    assert {name: after[name] for name in before} == before and len(after) == len(before) + 1
    # chacune voit la nouvelle étude parmi ses suites
    assert {child["experiment_id"] for child in get_experiment(client, slug, a["id"])["children"]} == {c["id"]}
    assert {child["experiment_id"] for child in get_experiment(client, slug, b["id"])["children"]} == {c["id"]}


def test_the_new_study_starts_with_an_empty_notebook(client):
    slug, a, b = _two_studies(client, "combine-notebook@example.com")
    on_a = add_manual(client, slug, a["id"], "Mesure A", measurements=[{"text": "A"}])
    on_b = add_manual(client, slug, b["id"], "Mesure B", measurements=[{"text": "B"}])
    a_tip = tag(client, slug, a["id"], ["a-garder"])
    b_tip = conclude(client, slug, b["id"], summary="B fini")

    c = combine(client, slug, a["id"], b["id"])
    assert entries(client, slug, c["id"]) == []
    assert (c["notebook_count"], c["tags"], c["conclusion"]["status"]) == (0, [], "draft")
    # les données restent sur A et B
    assert list(entries_by_id(client, slug, a["id"])) == [on_a["id"]]
    assert list(entries_by_id(client, slug, b["id"])) == [on_b["id"]]
    assert get_experiment(client, slug, a["id"])["version_id"] == a_tip["version_id"]
    assert get_experiment(client, slug, b["id"])["version_id"] == b_tip["version_id"]


def test_a_version_of_each_study_can_be_chosen(client):
    slug, a, b = _two_studies(client, "combine-versions@example.com")
    later = tag(client, slug, a["id"], ["plus-tard"])
    c = combine(client, slug, {"experiment_id": a["id"], "version_id": a["version_id"]}, {"experiment_id": b["id"]}, branch="depuis-v1")
    assert c["id"] == "depuis-v1"
    assert c["parents"] == [a["version_id"], b["version_id"]]  # la pointe de B par défaut
    assert get_experiment(client, slug, a["id"])["version_id"] == later["version_id"]


def test_a_combination_asks_what_a_launch_asks(client):
    slug, a, b = _two_studies(client, "combine-fields@example.com")
    count = list_experiments(client, slug)["total"]

    def refused(**fields):
        response = post_combine(client, slug, a["id"], b["id"], **fields)
        return response.status_code, response.json().get("code")

    assert refused(title=" ") == (422, "title_and_intent_required")
    assert refused(intent="") == (422, "title_and_intent_required")
    assert refused(entities=[]) == (422, "entity_required")
    assert refused(entities=[{"sample_id": " "}]) == (422, "entity_required")
    # exactement deux études, et pas de structure ni de version de départ à côté
    url = f"/api/microprojects/{slug}/experiments"
    base = {"title": "C", "intent": "x", "entities": [{"sample_id": "W9"}]}
    for body in (
        {**base, "merge_of": [{"experiment_id": a["id"]}]},
        {**base, "merge_of": [{"experiment_id": a["id"]}, {"experiment_id": b["id"]}, {"experiment_id": b["id"]}]},
        {**base, "merge_of": [{"experiment_id": a["id"]}, {"experiment_id": b["id"]}], "structure": {"kind": "images", "images": []}},
        {**base, "merge_of": [{"experiment_id": a["id"]}, {"experiment_id": b["id"]}], "from_version": {"experiment_id": a["id"]}},
        base,  # ni structure ni combinaison
    ):
        assert client.post(url, json=body).status_code == 422
    assert list_experiments(client, slug)["total"] == count


def test_two_studies_of_the_same_line_or_of_different_kinds_are_refused(client):
    slug, a, b = _two_studies(client, "combine-refused@example.com")
    campaign = launch_campaign(client, slug, entities=[{"sample_id": "W5"}])
    count = list_experiments(client, slug)["total"]
    same = post_combine(client, slug, a["id"], {"experiment_id": a["id"], "version_id": a["version_id"]})
    assert same.status_code == 422 and same.json()["code"] == "same_experiment"
    kinds = post_combine(client, slug, a["id"], campaign["id"])
    assert kinds.status_code == 422 and kinds.json()["code"] == "different_structure_kinds"
    assert list_experiments(client, slug)["total"] == count


def test_unknown_studies_and_versions_are_404(client):
    slug, a, b = _two_studies(client, "combine-unknown@example.com")
    assert_handler_404(post_combine(client, slug, a["id"], "inconnue"), "introuvable")
    unknown_version = post_combine(client, slug, a["id"], {"experiment_id": b["id"], "version_id": "exp_0000000000000000"})
    assert_handler_404(unknown_version, "introuvable")
    assert unknown_version.json()["code"] == "source_not_found"
    # une version d'une autre piste n'est pas une version de celle-ci
    assert_handler_404(post_combine(client, slug, a["id"], {"experiment_id": b["id"], "version_id": a["version_id"]}))


def test_studies_of_two_microprojects_are_not_combined(client):
    slug, a, _ = _two_studies(client, "combine-two-mp@example.com")
    other_slug = signup_with_microproject(client, "combine-two-mp@example.com".replace("@", "+2@"), "Ailleurs")
    elsewhere = launch(client, other_slug, title="Ailleurs", intent="x")
    add_member(client, other_slug, "combine-two-mp@example.com", "owner")
    login(client, "combine-two-mp@example.com")
    count = list_experiments(client, slug)["total"]
    # une étude d'un autre µprojet n'existe pas dans celui-ci
    assert_handler_404(post_combine(client, slug, a["id"], elsewhere["id"]))
    # et une étude ne se désigne pas dans un autre µprojet
    response = post_combine(client, slug, a["id"], {"experiment_id": elsewhere["id"], "microproject": other_slug})
    assert response.status_code == 422
    assert list_experiments(client, slug)["total"] == count


def test_a_viewer_cannot_combine(client):
    signup(client, "admin-combine@example.com")  # le premier compte est admin
    signup(client, "viewer-combine@example.com", name="V")
    slug, a, b = _two_studies(client, "owner-combine@example.com")
    add_member(client, slug, "viewer-combine@example.com", "viewer")
    login(client, "viewer-combine@example.com")
    assert post_combine(client, slug, a["id"], b["id"]).status_code == 403


def test_combining_two_campaigns_tracks_one_wafer_per_variant(client):
    slug = signup_with_microproject(client, "combine-campaigns@example.com")
    first = launch_campaign(client, slug, title="Campagne 1", entities=[{"sample_id": "W1"}])
    second = launch_campaign(client, slug, title="Campagne 2", entities=[{"sample_id": "W2"}])
    c = combine(client, slug, first["id"], second["id"], entities=[{"sample_id": "W9"}])
    assert [e["sample_id"] for e in c["physical_tracking"]] == ["W9", None, None]
    assert c["is_batch"] is True


def test_the_lineage_and_the_structure_history_show_both_parents(client):
    slug, a, b = _two_studies(client, "combine-graphs@example.com")
    c = combine(client, slug, a["id"], b["id"], title="Piste C")

    body = lineage(client, slug)
    node = next(n for n in body["nodes"] if n["id"] == c["version_id"])
    assert node["is_merge"] is True and node["experiment_id"] == c["id"]
    assert {e["parent"] for e in body["edges"] if e["child"] == c["version_id"]} == {a["version_id"], b["version_id"]}

    history = structure_history(client, slug)
    assert [lane["experiment_id"] for lane in history["lanes"]] == [a["id"], b["id"], c["id"]]
    start = next(n for n in history["nodes"] if n["version_id"] == c["version_id"])
    assert (start["lane"], start["experiment_id"], start["is_merge"], start["is_tip"]) == (2, c["id"], True, True)
    assert {(e["parent"], e["kind"]) for e in history["edges"] if e["child"] == c["version_id"]} == {
        (a["version_id"], "merge"),
        (b["version_id"], "merge"),
    }


def test_the_lineage_shows_both_parents_of_two_forks_of_the_same_point(client):
    """Deux pistes parties d'une même version sans changer sa structure sont deux nœuds de la
    filiation (deux pointes au même point structurel) : leur combinaison part de chacune."""
    slug = signup_with_microproject(client, "combine-forks@example.com", "Fourches")
    root = launch(client, slug, title="Racine", intent="Depart", steps=steps(20))
    fork = {"experiment_id": root["id"], "version_id": root["version_id"]}
    a = launch(client, slug, title="Rouge", intent="Rouge", steps=steps(20), from_version=fork)
    b = launch(client, slug, title="Verte", intent="Verte", steps=steps(20), from_version=fork)
    c = combine(client, slug, a["id"], b["id"], title="Rouge + Verte")

    body = lineage(client, slug)
    ids = {n["id"] for n in body["nodes"]}
    assert {a["version_id"], b["version_id"], c["version_id"]} <= ids
    assert {e["parent"] for e in body["edges"] if e["child"] == c["version_id"]} == {a["version_id"], b["version_id"]}
    assert all(e["parent"] in ids and e["child"] in ids for e in body["edges"])
