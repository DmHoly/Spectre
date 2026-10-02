from __future__ import annotations

import pytest

from support.accounts import signup
from support.experiments import conclude, evolve, get_experience, launch, launch_body, tag, timeline
from support.http import assert_handler_404
from support.microprojects import join_as, signup_with_microproject
from support.structures import campaign_plan, steps, substrate

ISOLATION = [{"name": "Isolation", "metric": "resistivity_ohm_cm", "direction": "target", "target": 1e6}]


def _owner_microproject(client, email="owner@example.com", name="Owner"):
    return signup_with_microproject(client, email, "Salle blanche", name=name)


def _launch_essai(client, slug, title="Essai initial", thickness=20):
    return launch(client, slug, title=title, intent="Verifier l'isolation", objectives=ISOLATION, steps=steps(thickness))


def test_get_experience_detail_has_structure_svg(client):
    slug = _owner_microproject(client)
    launched = _launch_essai(client, slug)

    response = client.get(f"/api/microprojets/{slug}/experiences/{launched['id']}")
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Essai initial"
    assert body["status"] == "draft"
    assert "<svg" in body["structure_svg"]
    assert body["has_editable_process"] is True


def test_mark_running_then_edit_conclusion(client):
    slug = _owner_microproject(client)
    launched = _launch_essai(client, slug)
    assert get_experience(client, slug, launched["id"])["status"] == "draft"

    # brouillon -> en cours
    marked = client.post(f"/api/microprojets/{slug}/experiences/{launched['id']}/statut", json={"status": "running"})
    assert marked.status_code == 201
    running_id = marked.json()["id"]
    assert get_experience(client, slug, running_id)["status"] == "running"

    # conclure
    met = [{"objective": "Isolation", "status": "met"}]
    concluded = conclude(client, slug, running_id, summary="Version initiale", objective_results=met)

    # rouvrir puis re-conclure avec un résumé corrigé
    reopened = client.post(f"/api/microprojets/{slug}/experiences/{concluded['id']}/statut", json={"status": "running"})
    assert reopened.status_code == 201
    reopened_id = reopened.json()["id"]
    reopened_detail = get_experience(client, slug, reopened_id)
    assert reopened_detail["status"] == "running"
    assert reopened_detail["conclusion"]["summary"] == "Version initiale"  # les données de conclusion sont conservées

    fixed = conclude(client, slug, reopened_id, summary="Résumé corrigé", objective_results=met)
    assert get_experience(client, slug, fixed["id"])["conclusion"]["summary"] == "Résumé corrigé"


def test_campaign_from_ref_keeps_lineage(client):
    slug = _owner_microproject(client)
    ref = _launch_essai(client, slug, title="Référence")["id"]

    plan = campaign_plan([10, 20, 30])
    campaign = client.post(
        f"/api/microprojets/{slug}/experiences/campagne",
        json=launch_body(title="Split depuis la ref", intent="faire varier l'épaisseur", plan=plan, entities=[{"sample_id": "C-ref"}], from_ref=ref),
    )
    assert campaign.status_code == 201
    detail = get_experience(client, slug, campaign.json()["id"])
    assert detail["parents"] == [ref]  # rattachée à la version de départ
    assert detail["is_batch"] is True

    bad = client.post(
        f"/api/microprojets/{slug}/experiences/campagne",
        json=launch_body(title="X", intent="y", plan=plan, entities=[{"sample_id": "z"}], from_ref="exp_deadbeef00000000"),
    )
    assert_handler_404(bad, "expérience de départ introuvable")


def test_delete_experience_removes_the_whole_line_and_refuses_when_forked(client):
    slug = _owner_microproject(client)
    a = _launch_essai(client, slug, title="A")["id"]
    b = _launch_essai(client, slug, title="B")["id"]
    b2 = evolve(client, slug, b, title="B", intent="x", steps=steps(40), objectives=[], entities=[])["id"]

    titles = lambda: sorted(x["title"] for x in client.get(f"/api/microprojets/{slug}/experiences?status=all").json()["items"])
    assert titles() == ["A", "B"]

    deleted = client.delete(f"/api/microprojets/{slug}/experiences/{b2}")
    assert deleted.status_code == 200
    assert deleted.json()["count"] == 2  # b and b2
    assert titles() == ["A"]

    # fork A onto its own piste, then A can't be deleted until the fork is gone
    a2 = evolve(client, slug, a, title="A2", intent="x", steps=steps(40), new_branch="piste-a2", objectives=[], entities=[])["id"]
    assert client.delete(f"/api/microprojets/{slug}/experiences/{a}").status_code == 422
    assert client.delete(f"/api/microprojets/{slug}/experiences/{a2}").status_code == 200
    assert client.delete(f"/api/microprojets/{slug}/experiences/{a}").status_code == 200
    assert titles() == []


def test_delete_experience_needs_editor(client):
    slug = _owner_microproject(client)
    exp = _launch_essai(client, slug)["id"]
    signup(client, "viewer@x.c", name="V")
    # the viewer isn't a member at all -> 403 (require_role)
    assert client.delete(f"/api/microprojets/{slug}/experiences/{exp}").status_code == 403


def test_status_endpoint_rejects_concluded_target(client):
    slug = _owner_microproject(client)
    launched = _launch_essai(client, slug)
    bad = client.post(f"/api/microprojets/{slug}/experiences/{launched['id']}/statut", json={"status": "concluded"})
    assert bad.status_code == 422


def test_process_endpoint_returns_editable_recipe(client):
    slug = _owner_microproject(client)
    launched = _launch_essai(client, slug)

    response = client.get(f"/api/microprojets/{slug}/experiences/{launched['id']}/process")
    assert response.status_code == 200
    body = response.json()
    assert body["substrate"]["material"] == "Si"
    assert body["steps"][0]["kind"] == "deposition"


def test_evolve_then_timeline_and_diff(client):
    slug = _owner_microproject(client)
    launched = _launch_essai(client, slug, thickness=20)

    evolve_body = {
        "substrate": substrate(),
        "steps": steps(thickness_nm=10),
        "title": "Essai initial",
        "intent": "Reduire l'epaisseur",
        "objectives": [],
    }
    evolved = client.post(f"/api/microprojets/{slug}/experiences/{launched['id']}/evoluer", json=evolve_body)
    assert evolved.status_code == 201
    evolved_id = evolved.json()["id"]

    history = timeline(client, slug, evolved_id)
    assert [item["id"] for item in history["items"]] == [launched["id"], evolved_id]
    assert history["items"][-1]["is_current"] is True

    diff = client.get(f"/api/microprojets/{slug}/experiences/{evolved_id}/diff").json()
    assert diff["target"] == launched["id"]
    assert len(diff["entries"]) >= 1


def test_timeline_versions_only_lists_process_changes_full_history_lists_everything(client):
    slug = _owner_microproject(client)
    launched = _launch_essai(client, slug, thickness=20)

    # a tag-only commit does not touch the process at all
    tagged_id = tag(client, slug, launched["id"], ["a-suivre"])["id"]
    evolved_id = evolve(client, slug, tagged_id, title="Essai initial", intent="Reduire l'epaisseur", steps=steps(thickness_nm=10), objectives=[])["id"]

    history = timeline(client, slug, evolved_id)

    assert [item["id"] for item in history["items"]] == [launched["id"], tagged_id, evolved_id]
    by_id = {item["id"]: item for item in history["items"]}
    assert by_id[launched["id"]]["change_level"] == "initial"
    assert by_id[launched["id"]]["version"] == "1.0.0"
    assert by_id[tagged_id]["change_level"] == "none"
    assert by_id[tagged_id]["version"] == "1.0.0"  # unchanged - the tag didn't touch the process
    assert by_id[evolved_id]["change_level"] == "minor"  # same step, only the thickness changed
    assert by_id[evolved_id]["version"] == "1.1.0"

    # the tag-only commit is in the full history but not in the version-only view
    assert [item["id"] for item in history["versions"]] == [launched["id"], evolved_id]


def test_conclude_experience(client):
    slug = _owner_microproject(client)
    launched = _launch_essai(client, slug)

    body = {
        "status": "concluded",
        "decision": "promote",
        "summary": "Objectif atteint.",
        "objective_results": [{"objective": "Isolation", "status": "met", "reasoning": "Mesure conforme"}],
    }
    response = client.post(f"/api/microprojets/{slug}/experiences/{launched['id']}/conclure", json=body)
    assert response.status_code == 201
    concluded_id = response.json()["id"]

    detail = get_experience(client, slug, concluded_id)
    assert detail["status"] == "concluded"
    assert detail["conclusion"]["decision"] == "promote"

    concluded_list = client.get(f"/api/microprojets/{slug}/experiences?status=concluded").json()
    assert any(item["id"] == concluded_id for item in concluded_list["items"])


def test_viewer_cannot_evolve_or_conclude(client):
    slug = _owner_microproject(client, "owner4@example.com", "Owner4")
    launched = _launch_essai(client, slug)

    join_as(client, slug, "viewer4@example.com", owner="owner4@example.com", role="viewer", name="Viewer4")

    evolve_response = client.post(
        f"/api/microprojets/{slug}/experiences/{launched['id']}/evoluer",
        json={"substrate": substrate(), "steps": steps(), "title": "X", "intent": "Y"},
    )
    assert evolve_response.status_code == 403

    conclude_response = client.post(f"/api/microprojets/{slug}/experiences/{launched['id']}/conclure", json={"status": "concluded"})
    assert conclude_response.status_code == 403


def test_unknown_experience_is_404_on_every_kind_of_route(client):
    slug = _owner_microproject(client)
    missing = "exp_" + "0" * 16
    for response in (
        client.get(f"/api/microprojets/{slug}/experiences/{missing}"),
        client.get(f"/api/microprojets/{slug}/experiences/{missing}/timeline"),
        client.post(f"/api/microprojets/{slug}/experiences/{missing}/etiquettes", json={"tags": []}),
        client.delete(f"/api/microprojets/{slug}/experiences/{missing}"),
    ):
        assert_handler_404(response)


@pytest.mark.xfail(
    strict=True,
    reason="bug connu : /etiquettes et /conclure dérivent la nouvelle version sans reprendre "
    "l'hypothèse de la précédente (repo.derive(hypothesis=None)) - elle disparaît de la fiche. "
    "À corriger à l'étape plugin experiments.",
)
def test_the_hypothesis_survives_lightweight_evolutions(client):
    slug = _owner_microproject(client)
    launched = launch(client, slug, hypothesis="L'oxyde isole à 20 nm")
    tagged = tag(client, slug, launched["id"], ["a-suivre"])
    concluded = conclude(client, slug, tagged["id"], summary="Fini")

    assert get_experience(client, slug, tagged["id"])["hypothesis"] == "L'oxyde isole à 20 nm"
    assert get_experience(client, slug, concluded["id"])["hypothesis"] == "L'oxyde isole à 20 nm"
