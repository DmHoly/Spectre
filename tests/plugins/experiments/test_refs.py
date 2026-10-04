"""Refs (spectre.plugins.experiments.refs): marking a version as a named, reusable starting point -
built on Follow's own tag (an immutable pointer to one version), with a default "ref vX.Y.Z" name
from spectre.plugins.experiments.versioning when no nickname is given. See test_atlas.py for the
same condensed-edges algorithm applied to branch tips instead of refs.
"""

from __future__ import annotations

from support.experiments import (
    conclude,
    create_ref,
    delete_ref,
    evolve,
    get_experiment,
    get_ref,
    launch,
    launch_campaign,
    patch_ref,
    ref_url,
    refs,
    rename_ref,
    structure_history,
    tag,
)
from support.http import assert_handler_404
from support.microprojects import join_as, signup_with_microproject
from support.structures import campaign_plan, etch, steps

REFS = "/api/microprojects/{}/refs"


def _launch_reference(client, slug, title="Reference", thickness=20):
    return launch(client, slug, title=title, intent="Depart", steps=steps(thickness))


def test_default_ref_name_uses_the_computed_version(client):
    slug = signup_with_microproject(client, "refs-default@example.com")
    launched = _launch_reference(client, slug)
    evolved = evolve(client, slug, launched["id"], title="Reference", intent="x", steps=steps(30))

    response = client.post(REFS.format(slug), json={"experiment_id": launched["id"]})
    assert response.status_code == 201
    created = response.json()
    assert created["names"] == ["ref v1.1.0"]  # la pointe de la piste par défaut
    assert (created["experiment_id"], created["version_id"]) == (launched["id"], evolved["version_id"])

    assert get_experiment(client, slug, launched["id"])["ref_names"] == ["ref v1.1.0"]


def test_ref_can_be_given_a_nickname_and_a_past_version(client):
    slug = signup_with_microproject(client, "refs-nickname@example.com")
    launched = _launch_reference(client, slug)
    tag(client, slug, launched["id"], ["x"])

    created = create_ref(client, slug, launched["id"], "  omega  ", version_id=launched["version_id"])
    assert created["names"] == ["omega", "ref v1.0.0"]  # le surnom rejoint la ref automatique de la première version
    assert created["version_id"] == launched["version_id"]


def test_a_nickname_with_a_slash_is_refused(client):
    # a ref is addressed as a single path segment - "a/b" could never be reached again
    slug = signup_with_microproject(client, "refs-slash@example.com")
    launched = _launch_reference(client, slug)

    response = client.post(REFS.format(slug), json={"experiment_id": launched["id"], "name": "omega/2"})
    assert response.status_code == 422
    assert "/" in response.json()["detail"]
    assert get_experiment(client, slug, launched["id"])["ref_names"] == ["ref v1.0.0"]  # only the automatic one


def test_a_nickname_already_used_elsewhere_conflicts(client):
    slug = signup_with_microproject(client, "refs-conflict@example.com")
    a = _launch_reference(client, slug, title="A")
    b = _launch_reference(client, slug, title="B")

    create_ref(client, slug, a["id"], "omega")
    assert client.post(REFS.format(slug), json={"experiment_id": b["id"], "name": "omega"}).status_code == 409
    # a line of study's name is taken too (branches and refs share one namespace)
    assert client.post(REFS.format(slug), json={"experiment_id": b["id"], "name": a["id"]}).status_code == 409


def test_tagging_the_same_version_with_no_nickname_twice_is_idempotent(client):
    slug = signup_with_microproject(client, "refs-idempotent@example.com")
    launched = _launch_reference(client, slug)

    first = create_ref(client, slug, launched["id"])
    second = create_ref(client, slug, launched["id"])
    assert first == second
    assert first["names"] == ["ref v1.0.0"]


def test_a_new_line_can_start_from_a_ref(client):
    slug = signup_with_microproject(client, "refs-evolve@example.com")
    launched = _launch_reference(client, slug)
    omega = create_ref(client, slug, launched["id"], "omega")

    started = launch(
        client, slug, title="Suite", intent="Depuis omega", steps=steps(40),
        from_version={"experiment_id": omega["experiment_id"], "version_id": omega["version_id"]},
    )
    assert started["id"] != launched["id"]
    assert started["parents"] == [launched["version_id"]]


def test_the_microprojects_first_experiment_becomes_a_ref_automatically(client):
    slug = signup_with_microproject(client, "refs-auto-first@example.com")
    launched = _launch_reference(client, slug)

    items = refs(client, slug)["refs"]
    assert len(items) == 1
    assert (items[0]["experiment_id"], items[0]["version_id"]) == (launched["id"], launched["version_id"])
    assert items[0]["names"] == ["ref v1.0.0"]

    # a later experiment in the same microproject does *not* also get auto-tagged
    second = launch(client, slug, title="Autre depart", intent="Depart 2", steps=steps(30), entities=[{"sample_id": "W2"}])
    assert {i["experiment_id"] for i in refs(client, slug)["refs"]} == {launched["id"]}
    assert second["id"] != launched["id"]


def test_the_microprojects_first_campaign_becomes_a_ref_automatically(client):
    slug = signup_with_microproject(client, "refs-auto-first-campaign@example.com")
    campaign = launch_campaign(client, slug, campaign_plan([10, 20]), entities=[{"sample_id": "V0"}])

    items = refs(client, slug)["refs"]
    assert len(items) == 1
    assert items[0]["experiment_id"] == campaign["id"]


def test_refs_and_their_edges_condense_intermediate_versions(client):
    slug = signup_with_microproject(client, "refs-graph@example.com")
    root = _launch_reference(client, slug, thickness=10)
    create_ref(client, slug, root["id"], "omega")

    # a lightweight write that doesn't change the process at all - version stays 1.0.0, collapsed
    # out of the ref graph
    tag(client, slug, root["id"], ["a-suivre"])

    # a real structural change (a step added) - bumps to 2.0.0
    grown = evolve(client, slug, root["id"], title="Suite", intent="Ajout d'une gravure", steps=steps(10) + [etch(depth_nm=5)])
    create_ref(client, slug, root["id"], "banane")

    body = refs(client, slug)
    version_by_name = {entry["names"][0]: entry["version"] for entry in body["refs"]}
    assert version_by_name == {"omega": "1.0.0", "banane": "2.0.0"}
    # the ordinary version ("a-suivre") in between is collapsed out - one edge straight from ref to ref
    assert {(e["from"], e["to"]) for e in body["edges"]} == {(root["version_id"], grown["version_id"])}


def test_ref_list_exposes_the_conclusion_decision(client):
    slug = signup_with_microproject(client, "refs-decision@example.com")
    launched = _launch_reference(client, slug)
    conclude(client, slug, launched["id"], decision="inconclusive")
    create_ref(client, slug, launched["id"], "essai-a")

    items = refs(client, slug)["refs"]
    assert items[0]["decision"] == "inconclusive"  # for the "Non concluante" badge nuance


# -- une ref : la lire, la renommer, la retirer (page « Évolution des structures ») ----------------


def test_creating_a_ref_points_to_it(client):
    slug = signup_with_microproject(client, "refs-location@example.com")
    launched = _launch_reference(client, slug)

    response = client.post(REFS.format(slug), json={"experiment_id": launched["id"], "name": "omega"})
    assert response.status_code == 201
    assert response.headers["location"] == f"/api/microprojects/{slug}/refs/omega"
    assert response.json()["name"] == "omega"
    assert client.get(response.headers["location"]).json() == response.json()

    # un nom par défaut, avec une espace : l'adresse l'encode, la lecture le rend tel quel
    other = evolve(client, slug, launched["id"], title="Reference", intent="x", steps=steps(30))
    default = client.post(REFS.format(slug), json={"experiment_id": launched["id"]})
    assert default.headers["location"] == f"/api/microprojects/{slug}/refs/ref%20v1.1.0"
    ref = get_ref(client, slug, "ref v1.1.0")
    assert (ref["name"], ref["version_id"], ref["experiment_id"], ref["version"]) == ("ref v1.1.0", other["version_id"], launched["id"], "1.1.0")


def test_an_unknown_ref_is_404(client):
    slug = signup_with_microproject(client, "refs-unknown@example.com")
    _launch_reference(client, slug)
    assert_handler_404(client.get(ref_url(slug, "inconnue")))
    assert_handler_404(patch_ref(client, slug, "inconnue", "autre"))
    assert_handler_404(delete_ref(client, slug, "inconnue"))


def test_an_editor_renames_a_ref_and_its_version_stays(client):
    slug = signup_with_microproject(client, "refs-rename@example.com")
    launched = _launch_reference(client, slug)
    create_ref(client, slug, launched["id"], "omega")

    renamed = rename_ref(client, slug, "omega", "  banane  ")
    assert renamed["name"] == "banane"
    assert renamed["names"] == ["banane", "ref v1.0.0"]
    assert renamed["version_id"] == launched["version_id"]
    assert_handler_404(client.get(ref_url(slug, "omega")))
    assert get_experiment(client, slug, launched["id"])["ref_names"] == ["banane", "ref v1.0.0"]
    assert structure_history(client, slug)["nodes"][0]["refs"] == ["banane", "ref v1.0.0"]

    # le même nom : rien ne change ; sans nom : rien non plus
    assert rename_ref(client, slug, "banane", "banane")["name"] == "banane"
    assert patch_ref(client, slug, "banane", None).json()["name"] == "banane"


def test_renaming_a_ref_to_a_taken_or_invalid_name_is_refused(client):
    slug = signup_with_microproject(client, "refs-rename-refused@example.com")
    a = _launch_reference(client, slug, title="A")
    b = _launch_reference(client, slug, title="B")
    create_ref(client, slug, b["id"], "omega")

    assert patch_ref(client, slug, "omega", "ref v1.0.0").status_code == 409  # une autre ref
    assert patch_ref(client, slug, "omega", a["id"]).status_code == 409  # une piste
    for invalid in ("omega/2", "", "  ", "..", "exp_0123456789abcdef"):
        assert patch_ref(client, slug, "omega", invalid).status_code == 422, invalid
    assert get_ref(client, slug, "omega")["version_id"] == b["version_id"]


def test_a_new_ref_cannot_take_the_form_of_a_version_id(client):
    slug = signup_with_microproject(client, "refs-version-form@example.com")
    launched = _launch_reference(client, slug)
    response = client.post(REFS.format(slug), json={"experiment_id": launched["id"], "name": "exp_0123456789abcdef"})
    assert response.status_code == 422


def test_an_editor_removes_a_ref_and_the_version_stays(client):
    slug = signup_with_microproject(client, "refs-delete@example.com")
    launched = _launch_reference(client, slug)
    create_ref(client, slug, launched["id"], "omega")

    response = delete_ref(client, slug, "omega")
    assert response.status_code == 204 and response.content == b""
    assert_handler_404(client.get(ref_url(slug, "omega")))
    assert get_experiment(client, slug, launched["id"])["version_id"] == launched["version_id"]
    assert delete_ref(client, slug, "ref v1.0.0").status_code == 204
    assert refs(client, slug)["refs"] == []
    # la version reste dans l'historique, sans ref
    assert structure_history(client, slug)["nodes"][0]["refs"] == []


def test_a_viewer_reads_refs_but_cannot_rename_or_remove_them(client):
    slug = signup_with_microproject(client, "refs-owner@example.com", name="Owner")
    launched = _launch_reference(client, slug)
    create_ref(client, slug, launched["id"], "omega")

    join_as(client, slug, "refs-viewer@example.com", owner="refs-owner@example.com", role="viewer")
    assert get_ref(client, slug, "omega")["name"] == "omega"
    assert patch_ref(client, slug, "omega", "banane").status_code == 403
    assert delete_ref(client, slug, "omega").status_code == 403
    assert client.post(REFS.format(slug), json={"experiment_id": launched["id"], "name": "x"}).status_code == 403

    join_as(client, slug, "refs-editor@example.com", owner="refs-owner@example.com", role="editor")
    assert rename_ref(client, slug, "omega", "banane")["name"] == "banane"
    assert delete_ref(client, slug, "banane").status_code == 204


def test_the_old_refs_page_redirects_to_the_structure_evolution(client):
    slug = signup_with_microproject(client, "refs-page@example.com")
    response = client.get(f"/microprojets/{slug}/refs", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == f"/microprojets/{slug}/evolution"
    page = client.get(f"/microprojets/{slug}/evolution")
    assert page.status_code == 200 and "Évolution des structures" in page.text
