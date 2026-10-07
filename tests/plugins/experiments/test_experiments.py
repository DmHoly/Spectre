from __future__ import annotations

from support.accounts import signup
from support.experiments import (
    conclude,
    delete_experiment,
    evolve,
    experiment_url,
    experiments_url,
    get_experiment,
    launch,
    launch_body,
    launch_campaign,
    list_experiments,
    post_evolve,
    process,
    set_status,
    structure_diff,
    tag,
    versions,
)
from support.http import assert_handler_404
from support.microprojects import join_as, signup_with_microproject
from support.structures import campaign_plan, steps

ISOLATION = [{"name": "Isolation", "metric": "resistivity_ohm_cm", "direction": "target", "target": 1e6}]


def _owner_microproject(client, email="owner@example.com", name="Owner"):
    return signup_with_microproject(client, email, "Salle blanche", name=name)


def _launch_essai(client, slug, title="Essai initial", thickness=20, **fields):
    return launch(client, slug, title=title, intent="Verifier l'isolation", objectives=ISOLATION, steps=steps(thickness), **fields)


def test_launch_creates_a_line_of_study_with_location_and_etag(client):
    slug = _owner_microproject(client)
    response = client.post(experiments_url(slug), json=launch_body(title="Essai initial", intent="Verifier"))
    assert response.status_code == 201
    created = response.json()
    assert created["id"] == "essai-initial"  # la piste : un nom de branche tiré du titre
    assert created["version_id"].startswith("exp_")
    assert created["is_tip"] is True
    assert response.headers["Location"] == experiment_url(slug, "essai-initial")
    assert response.headers["ETag"] == f'"{created["version_id"]}"'

    fetched = client.get(experiment_url(slug, "essai-initial"))
    assert fetched.headers["ETag"] == f'"{created["version_id"]}"'
    body = fetched.json()
    assert body["title"] == "Essai initial"
    assert body["status"] == "draft"
    assert "<svg" in body["structure_svg"]
    assert body["has_editable_process"] is True


def test_title_and_intent_are_required_for_every_kind(client):
    slug = _owner_microproject(client)
    for kind_fields in ({}, {"kind": "campaign", "plan": campaign_plan([10, 20])}):
        response = client.post(experiments_url(slug), json=launch_body(title="  ", intent="x", **kind_fields))
        assert response.status_code == 422
        assert response.json()["code"] == "title_and_intent_required"


def test_a_requested_branch_name_must_be_one_free_segment(client):
    slug = _owner_microproject(client)
    named = launch(client, slug, title="Essai", branch="piste-alpha")
    assert named["id"] == "piste-alpha"

    assert client.post(experiments_url(slug), json=launch_body(branch="a/b")).status_code == 422
    taken = client.post(experiments_url(slug), json=launch_body(branch="piste-alpha"))
    assert taken.status_code == 409
    assert taken.json()["code"] == "branch_name_taken"


def test_the_same_title_twice_makes_two_lines(client):
    slug = _owner_microproject(client)
    assert launch(client, slug, title="Essai")["id"] == "essai"
    assert launch(client, slug, title="Essai")["id"] == "essai-2"


def test_mark_running_then_edit_conclusion_on_the_same_line(client):
    slug = _owner_microproject(client)
    launched = _launch_essai(client, slug)
    line = launched["id"]

    running = set_status(client, slug, line, "running")
    assert running["id"] == line
    assert running["status"] == "running"
    assert running["version_id"] != launched["version_id"]

    met = [{"objective": "Isolation", "status": "met"}]
    conclude(client, slug, line, summary="Version initiale", objective_results=met)

    reopened = set_status(client, slug, line, "running")
    assert reopened["status"] == "running"
    assert reopened["conclusion"]["summary"] == "Version initiale"  # les données de conclusion sont conservées

    conclude(client, slug, line, summary="Résumé corrigé", objective_results=met)
    assert get_experiment(client, slug, line)["conclusion"]["summary"] == "Résumé corrigé"


def test_campaign_from_a_version_keeps_lineage(client):
    slug = _owner_microproject(client)
    ref = _launch_essai(client, slug, title="Référence")

    campaign = launch_campaign(
        client,
        slug,
        title="Split depuis la ref",
        intent="faire varier l'épaisseur",
        entities=[{"sample_id": "C-ref"}],
        from_version={"experiment_id": ref["id"], "version_id": ref["version_id"]},
    )
    assert campaign["parents"] == [ref["version_id"]]  # rattachée à la version de départ
    assert campaign["id"] != ref["id"]  # une nouvelle piste
    assert campaign["is_batch"] is True

    bad = client.post(
        experiments_url(slug),
        json=launch_body(title="X", intent="y", from_version={"experiment_id": ref["id"], "version_id": "exp_deadbeef00000000"}),
    )
    assert_handler_404(bad, "Version de départ introuvable")
    unknown_line = client.post(experiments_url(slug), json=launch_body(from_version={"experiment_id": "inconnue"}))
    assert_handler_404(unknown_line, "Version de départ introuvable")


def test_a_line_from_a_version_starts_afresh_but_keeps_its_defaults(client):
    slug = _owner_microproject(client)
    source = _launch_essai(client, slug, title="Source", context="Le contexte")
    tag(client, slug, source["id"], ["a-suivre"])
    conclude(client, slug, source["id"], summary="Fini")

    fork = launch(
        client, slug, title="Fourche", intent="Explorer", steps=steps(40), entities=[{"sample_id": "W5"}], branch="fourche",
        from_version={"experiment_id": source["id"]},
    )
    assert fork["id"] == "fourche"
    assert fork["objectives"][0]["name"] == "Isolation"  # repris faute d'autres
    assert fork["context"] == "Le contexte"
    assert fork["physical_tracking"] == [{"sample_id": "W5", "location": None}]  # ses plaques, jamais celles de la source en silence
    assert fork["tags"] == [] and fork["status"] == "draft"  # une nouvelle étude
    assert get_experiment(client, slug, source["id"])["status"] == "concluded"  # la source est intacte


def test_delete_removes_the_whole_line_and_refuses_when_something_derives_from_it(client):
    slug = _owner_microproject(client)
    a = _launch_essai(client, slug, title="A")["id"]
    b = _launch_essai(client, slug, title="B")["id"]
    evolve(client, slug, b, title="B", intent="x", steps=steps(40))

    titles = lambda: sorted(item["title"] for item in list_experiments(client, slug)["items"])  # noqa: E731
    assert titles() == ["A", "B"]

    deleted = delete_experiment(client, slug, b)
    assert deleted.status_code == 204
    assert deleted.content == b""
    assert titles() == ["A"]
    assert_handler_404(client.get(experiment_url(slug, b)))

    # une piste partie de A : A ne peut plus être supprimée tant qu'elle existe
    a2 = launch(client, slug, title="A2", intent="x", steps=steps(40), entities=[{"sample_id": "W2"}], from_version={"experiment_id": a})["id"]
    refused = delete_experiment(client, slug, a)
    assert refused.status_code == 409
    assert refused.json()["code"] == "has_descendants"
    assert delete_experiment(client, slug, a2).status_code == 204
    assert delete_experiment(client, slug, a).status_code == 204
    assert titles() == []


def test_delete_with_a_stale_if_match_is_refused(client):
    slug = _owner_microproject(client)
    launched = _launch_essai(client, slug)
    tag(client, slug, launched["id"], ["x"])
    assert delete_experiment(client, slug, launched["id"], if_match=launched["version_id"]).status_code == 412
    assert get_experiment(client, slug, launched["id"])["tags"] == ["x"]


def test_delete_needs_editor(client):
    slug = _owner_microproject(client)
    exp = _launch_essai(client, slug)["id"]
    signup(client, "viewer@x.c", name="V")
    # the new account isn't a member at all -> 403 (require_role)
    assert delete_experiment(client, slug, exp).status_code == 403


def test_status_endpoint_rejects_concluded_target(client):
    slug = _owner_microproject(client)
    launched = _launch_essai(client, slug)
    bad = client.put(f"{experiment_url(slug, launched['id'])}/status", json={"status": "concluded"})
    assert bad.status_code == 422


def test_a_conclusion_is_typed(client):
    slug = _owner_microproject(client)
    launched = _launch_essai(client, slug)
    url = f"{experiment_url(slug, launched['id'])}/conclusion"
    assert client.put(url, json={"status": "concluded", "objective_results": [{"objective": "Isolation", "status": "great"}]}).status_code == 422
    assert client.put(url, json={"status": "concluded", "decision": "maybe"}).status_code == 422
    observed = [{"objective": "Isolation", "status": "met", "observed": {"oops": 1}}]
    assert client.put(url, json={"status": "concluded", "objective_results": observed}).status_code == 422

    observed = [{"objective": "Isolation", "status": "met", "observed": {"value": 2e6, "unit": "ohm.cm"}}]
    concluded = conclude(client, slug, launched["id"], objective_results=observed)
    assert concluded["conclusion"]["objective_results"][0]["observed"]["value"] == 2e6


def test_process_endpoint_returns_editable_recipe_of_any_version(client):
    slug = _owner_microproject(client)
    launched = _launch_essai(client, slug)
    evolve(client, slug, launched["id"], title="Essai initial", intent="x", steps=steps(10))

    body = process(client, slug, launched["id"])
    assert body["substrate"]["material"] == "Si"
    assert body["steps"][0]["thickness"]["value"] == 10
    assert process(client, slug, launched["id"], version=launched["version_id"])["steps"][0]["thickness"]["value"] == 20


def test_evolve_then_versions_and_diff(client):
    slug = _owner_microproject(client)
    launched = _launch_essai(client, slug, thickness=20)

    response = post_evolve(client, slug, launched["id"], title="Essai initial", intent="Reduire l'epaisseur", steps=steps(10))
    assert response.status_code == 201
    evolved = response.json()
    assert evolved["id"] == launched["id"]  # la même piste
    assert response.headers["Location"] == f"{experiment_url(slug, launched['id'])}/versions/{evolved['version_id']}"
    assert response.headers["ETag"] == f'"{evolved["version_id"]}"'

    history = versions(client, slug, launched["id"])
    assert [item["version_id"] for item in history] == [launched["version_id"], evolved["version_id"]]
    assert [item["is_tip"] for item in history] == [False, True]

    diff = structure_diff(client, slug, launched["id"])
    assert diff["target"]["version_id"] == launched["version_id"]
    assert len(diff["entries"]) >= 1


def test_a_past_version_is_readable_but_never_shown_as_the_tip(client):
    slug = _owner_microproject(client)
    launched = _launch_essai(client, slug)
    tag(client, slug, launched["id"], ["a-suivre"])

    response = client.get(f"{experiment_url(slug, launched['id'])}/versions/{launched['version_id']}")
    assert response.status_code == 200
    assert response.headers["ETag"] == f'"{launched["version_id"]}"'
    past = response.json()
    assert past["is_tip"] is False
    assert past["tags"] == []
    assert_handler_404(client.get(f"{experiment_url(slug, launched['id'])}/versions/exp_0000000000000000"))


def test_versions_list_marks_process_changes_and_keeps_everything(client):
    slug = _owner_microproject(client)
    launched = _launch_essai(client, slug, thickness=20)

    # a tag-only commit does not touch the process at all
    tagged = tag(client, slug, launched["id"], ["a-suivre"])
    evolved = evolve(client, slug, launched["id"], title="Essai initial", intent="Reduire l'epaisseur", steps=steps(thickness_nm=10))

    by_id = {item["version_id"]: item for item in versions(client, slug, launched["id"])}
    assert list(by_id) == [launched["version_id"], tagged["version_id"], evolved["version_id"]]
    assert by_id[launched["version_id"]]["change_level"] == "initial"
    assert by_id[launched["version_id"]]["version"] == "1.0.0"
    assert by_id[tagged["version_id"]]["change_level"] == "none"
    assert by_id[tagged["version_id"]]["version"] == "1.0.0"  # unchanged - the tag didn't touch the process
    assert by_id[evolved["version_id"]]["change_level"] == "minor"  # same step, only the thickness changed
    assert by_id[evolved["version_id"]]["version"] == "1.1.0"


def test_conclude_experience(client):
    slug = _owner_microproject(client)
    launched = _launch_essai(client, slug)

    body = {
        "status": "concluded",
        "decision": "promote",
        "summary": "Objectif atteint.",
        "objective_results": [{"objective": "Isolation", "status": "met", "reasoning": "Mesure conforme"}],
    }
    response = client.put(f"{experiment_url(slug, launched['id'])}/conclusion", json=body)
    assert response.status_code == 200
    detail = response.json()
    assert detail["status"] == "concluded"
    assert detail["conclusion"]["decision"] == "promote"
    assert response.headers["ETag"] == f'"{detail["version_id"]}"'

    concluded_list = list_experiments(client, slug, status="concluded")
    assert [item["id"] for item in concluded_list["items"]] == [launched["id"]]
    assert list_experiments(client, slug, status="running") == {"items": [], "total": 0}


def test_the_list_searches_and_rejects_bad_filters(client):
    slug = _owner_microproject(client)
    launch(client, slug, title="Oxyde mince", intent="isoler")
    launch(client, slug, title="Nitrure", intent="passiver")
    assert [item["title"] for item in list_experiments(client, slug, q="OXYDE")["items"]] == ["Oxyde mince"]
    assert list_experiments(client, slug, q="passiv")["total"] == 1
    for params in ({"status": "tous"}, {"offset": -1}, {"limit": 0}, {"limit": 201}):
        assert client.get(experiments_url(slug), params=params).status_code == 422


def test_viewer_cannot_evolve_or_conclude(client):
    slug = _owner_microproject(client, "owner4@example.com", "Owner4")
    launched = _launch_essai(client, slug)

    join_as(client, slug, "viewer4@example.com", owner="owner4@example.com", role="viewer", name="Viewer4")

    assert post_evolve(client, slug, launched["id"], title="X", intent="Y").status_code == 403
    assert client.put(f"{experiment_url(slug, launched['id'])}/conclusion", json={"status": "concluded"}).status_code == 403
    assert get_experiment(client, slug, launched["id"])["id"] == launched["id"]  # mais elle lit


def test_unknown_experiment_is_404_on_every_kind_of_route(client):
    slug = _owner_microproject(client)
    url = experiment_url(slug, "inconnue")
    for response in (
        client.get(url),
        client.get(f"{url}/versions"),
        client.get(f"{url}/structure-diff"),
        client.put(f"{url}/tags", json={"tags": []}),
        client.post(f"{url}/versions", json=launch_body()),
        client.delete(url),
    ):
        assert_handler_404(response)


def test_a_version_id_is_not_an_experiment_id(client):
    slug = _owner_microproject(client)
    launched = _launch_essai(client, slug)
    assert_handler_404(client.get(experiment_url(slug, launched["version_id"])))


def test_the_hypothesis_survives_lightweight_writes(client):
    slug = _owner_microproject(client)
    launched = launch(client, slug, hypothesis="L'oxyde isole à 20 nm")
    tag(client, slug, launched["id"], ["a-suivre"])
    concluded = conclude(client, slug, launched["id"], summary="Fini")

    assert concluded["hypothesis"] == "L'oxyde isole à 20 nm"
    assert get_experiment(client, slug, launched["id"])["hypothesis"] == "L'oxyde isole à 20 nm"
