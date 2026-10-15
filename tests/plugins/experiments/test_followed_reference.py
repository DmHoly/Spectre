"""La référence suivie d'une étude (``reference_followed``, PUT .../reference) : choisie après coup,
séparée de l'origine (qui reste l'histoire), portée par une retouche de la piste, héritée par les
études lancées ensuite, appliquée à toute la branche sur demande, et marquée dans l'évolution des
structures."""

from __future__ import annotations

from support.experiments import evolve, experiment_url, get_experiment, launch, structure_history, versions
from support.http import assert_ok
from support.microprojects import join_as, signup_with_microproject
from support.references import origin
from support.structures import steps


def _follow(client, slug, ref, reference, version, *, scope="study", if_match=None):
    headers = {"If-Match": f'"{if_match}"'} if if_match else {}
    return client.put(f"{experiment_url(slug, ref)}/reference", json={"reference": reference, "version": version, "scope": scope}, headers=headers)


def test_without_a_choice_the_study_follows_its_origin(client):
    slug = signup_with_microproject(client, "followed-default@example.com", "Epi")
    study = launch(client, slug, title="Base", intent="x", steps=steps(20), reference_origin=origin("base", "1.0"))
    assert study["reference_followed"] == {"reference": "base", "version": "1.0"}
    alone = launch(client, slug, title="Seule", intent="x", steps=steps(21))
    assert alone["reference_origin"] is None and alone["reference_followed"] is None


def test_following_another_reference_is_a_patch_that_keeps_the_origin(client):
    slug = signup_with_microproject(client, "followed-set@example.com", "Epi")
    study = launch(client, slug, title="Depuis la base", intent="x", steps=steps(20), reference_origin=origin("base", "1.0"))

    after = assert_ok(_follow(client, slug, study["id"], "autre", "2.1", if_match=study["version_id"]))
    assert after["reference_followed"] == {"reference": "autre", "version": "2.1"}
    assert after["reference_origin"] == {"reference": "base", "version": "1.0"}
    assert after["version_id"] != study["version_id"] and after["is_tip"]
    # une retouche : pas de nouveau numéro
    numbers = [v["version"] for v in versions(client, slug, study["id"])]
    assert numbers[-1] == numbers[0]

    # reportée aux versions suivantes, et aux études lancées depuis la piste
    evolved = evolve(client, slug, study["id"], steps=steps(25))
    assert evolved["reference_followed"] == {"reference": "autre", "version": "2.1"}
    fork = launch(client, slug, title="Fourche", intent="y", steps=steps(26), from_version={"experiment_id": study["id"]})
    assert fork["reference_origin"] == {"reference": "base", "version": "1.0"}
    assert fork["reference_followed"] == {"reference": "autre", "version": "2.1"}
    # mais pas à une étude lancée depuis une référence chargée dans le constructeur
    loaded = launch(client, slug, title="Chargée", intent="y", steps=steps(27), from_version={"experiment_id": study["id"]}, reference_origin=origin("tierce", "1.0"))
    assert loaded["reference_followed"] == {"reference": "tierce", "version": "1.0"}

    # revenir à l'origine : l'étude la suit de nouveau, sans trace de l'autre
    back = assert_ok(_follow(client, slug, study["id"], "base", "1.0"))
    assert back["reference_followed"] == {"reference": "base", "version": "1.0"}
    # la même référence à nouveau : rien n'est écrit
    again = assert_ok(_follow(client, slug, study["id"], "base", "1.0"))
    assert again["version_id"] == back["version_id"]


def test_the_write_is_guarded(client):
    slug = signup_with_microproject(client, "followed-guard@example.com", "Epi")
    study = launch(client, slug, title="Depuis la base", intent="x", steps=steps(20), reference_origin=origin("base", "1.0"))
    stale = _follow(client, slug, study["id"], "autre", "1.0", if_match="exp_0000000000000000")
    assert stale.status_code == 412 and stale.json()["code"] == "stale_version"
    assert _follow(client, slug, study["id"], "Pas un slug", "1.0").status_code == 422
    assert _follow(client, slug, study["id"], "autre", "1.0", scope="all").status_code == 422
    assert _follow(client, slug, "inconnue", "autre", "1.0").status_code == 404
    assert get_experiment(client, slug, study["id"])["reference_followed"] == {"reference": "base", "version": "1.0"}

    join_as(client, slug, "followed-viewer@example.com", owner="followed-guard@example.com", role="viewer")
    assert _follow(client, slug, study["id"], "autre", "1.0").status_code == 403


def test_the_branch_scope_reaches_the_lines_that_descend_from_the_study(client):
    slug = signup_with_microproject(client, "followed-branch@example.com", "Epi")
    root = launch(client, slug, title="Racine", intent="x", steps=steps(20), reference_origin=origin("base", "1.0"))
    child = launch(client, slug, title="Fille", intent="y", steps=steps(22), from_version={"experiment_id": root["id"]})
    grandchild = launch(client, slug, title="Petite-fille", intent="z", steps=steps(23), from_version={"experiment_id": child["id"]})
    evolve(client, slug, root["id"], steps=steps(21))  # la racine avance après la fourche
    other = launch(client, slug, title="Ailleurs", intent="w", steps=steps(30), reference_origin=origin("base", "1.0"))

    assert_ok(_follow(client, slug, root["id"], "autre", "1.0", scope="branch"))
    for ref in (root["id"], child["id"], grandchild["id"]):
        detail = get_experiment(client, slug, ref)
        assert detail["reference_followed"] == {"reference": "autre", "version": "1.0"}, ref
        assert detail["reference_origin"] == {"reference": "base", "version": "1.0"}
    assert get_experiment(client, slug, other["id"])["reference_followed"] == {"reference": "base", "version": "1.0"}

    # l'étude seule : sa branche ne bouge pas
    assert_ok(_follow(client, slug, child["id"], "tierce", "3.0", scope="study"))
    assert get_experiment(client, slug, grandchild["id"])["reference_followed"] == {"reference": "autre", "version": "1.0"}


def test_the_evolution_marks_the_version_where_the_reference_changed(client):
    slug = signup_with_microproject(client, "followed-history@example.com", "Epi")
    study = launch(client, slug, title="Depuis la base", intent="x", steps=steps(20), reference_origin=origin("base", "1.0"))
    changed = assert_ok(_follow(client, slug, study["id"], "autre", "1.0"))

    history = structure_history(client, slug)  # la retouche est légère, mais se montre
    by_id = {node["version_id"]: node for node in history["nodes"]}
    assert by_id[study["version_id"]]["reference_followed"] == {"reference": "base", "version": "1.0"}
    assert not by_id[study["version_id"]]["reference_changed"]
    assert by_id[changed["version_id"]]["reference_followed"] == {"reference": "autre", "version": "1.0"}
    assert by_id[changed["version_id"]]["reference_changed"]
    assert by_id[changed["version_id"]]["change_level"] not in ("initial", "major", "minor")
