"""Les rattachements (``PUT/DELETE .../experiments/{id}/attachment``) : une étude partie de rien,
accrochée après coup sous une version d'une autre étude du µprojet. L'arbre (``GET .../lineage``)
la montre sous elle, par une arête marquée ``attached`` - un lien posé à la main, pas une filiation."""

from __future__ import annotations

from support.experiments import delete_experiment, launch, lineage
from support.http import assert_ok
from support.microprojects import join_as, signup_with_microproject
from support.structures import steps


def _url(slug: str, experiment_id: str) -> str:
    return f"/api/microprojects/{slug}/experiments/{experiment_id}/attachment"


def _attach(client, slug, study, target):
    """Rattache la piste ``study`` sous la pointe de la piste ``target``."""
    return client.put(_url(slug, study), json={"experiment_id": target})


def test_a_floating_study_hangs_under_another_by_an_explicit_link(client):
    slug = signup_with_microproject(client, "attach@example.com", "Rattachements")
    running = launch(client, slug, title="Épitaxie")
    floating = launch(client, slug, title="Recuit", steps=steps(25))

    attached = assert_ok(_attach(client, slug, floating["id"], running["id"]))
    assert attached["parent"] == {"experiment_id": running["id"], "version_id": running["version_id"]}
    assert attached["author"] == "T"

    graph = lineage(client, slug)
    edges = [e for e in graph["edges"] if e["child"] == floating["version_id"]]
    assert len(edges) == 1 and edges[0]["parent"] == running["version_id"] and edges[0]["attached"]["author"] == "T"

    response = client.delete(_url(slug, floating["id"]))
    assert response.status_code == 204
    assert lineage(client, slug)["edges"] == []
    assert client.delete(_url(slug, floating["id"])).json()["code"] == "attachment_not_found"


def test_only_a_study_started_from_nothing_attaches_and_never_below_itself(client):
    slug = signup_with_microproject(client, "attach-rules@example.com", "Rattachements")
    root = launch(client, slug, title="Racine")
    fork = launch(client, slug, title="Suite", steps=steps(25), from_version={"experiment_id": root["id"]})
    other = launch(client, slug, title="Autre", steps=steps(30))

    not_floating = _attach(client, slug, fork["id"], other["id"])
    assert not_floating.status_code == 422 and not_floating.json()["code"] == "not_floating"
    below = _attach(client, slug, root["id"], fork["id"])
    assert below.status_code == 422 and below.json()["code"] == "attachment_cycle"
    itself = _attach(client, slug, root["id"], root["id"])
    assert itself.json()["code"] == "attachment_cycle"
    # à travers un autre rattachement : Autre sous Suite, puis Racine sous Autre ferait une boucle
    assert_ok(_attach(client, slug, other["id"], fork["id"]))
    loop = _attach(client, slug, root["id"], other["id"])
    assert loop.json()["code"] == "attachment_cycle"
    lost = _attach(client, slug, root["id"], "nope")
    assert lost.status_code == 404 and lost.json()["code"] == "source_not_found"


def test_an_attachment_to_a_deleted_study_is_no_longer_drawn(client):
    slug = signup_with_microproject(client, "attach-gone@example.com", "Rattachements")
    parent = launch(client, slug, title="Parent")
    floating = launch(client, slug, title="Flottante", steps=steps(25))
    assert_ok(_attach(client, slug, floating["id"], parent["id"]))

    delete_experiment(client, slug, parent["id"])
    graph = lineage(client, slug)
    assert [n["title"] for n in graph["nodes"]] == ["Flottante"] and graph["edges"] == []


def test_a_viewer_cannot_attach(client):
    slug = signup_with_microproject(client, "attach-owner@example.com", "Rattachements")
    parent = launch(client, slug, title="Parent")
    floating = launch(client, slug, title="Flottante", steps=steps(25))
    join_as(client, slug, "attach-viewer@example.com", owner="attach-owner@example.com")
    assert _attach(client, slug, floating["id"], parent["id"]).status_code == 403
