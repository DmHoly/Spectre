"""L'identité stable des étapes d'un procédé (TODO § 3, le préalable) : chaque étape porte un ``id``
(``st_<8 hex>``) exposé par ``GET .../process``, enregistré dès qu'une version est créée, conservé
aux évolutions, et ignoré du versionnage. Une version enregistrée sans ids (avant eux) n'est
jamais réécrite : ses ids se lisent (ceux de son parent tant que les types d'étapes ne changent pas,
sinon dérivés de son id), toujours les mêmes."""

from __future__ import annotations

import hashlib
import re

from support.experiments import (
    evolve,
    evolve_image,
    get_experiment,
    launch,
    launch_campaign,
    post_evolve,
    post_launch,
    process,
    step_ids,
    tag,
    variants,
    versions,
)
from support.microprojects import signup_with_microproject
from support.structures import campaign_plan, deposition, etch, fixed_step_id, identified, simulate, substrate, upload_structure_image

STEP_ID = re.compile(r"^st_[0-9a-f]{8}$")


def _three_steps() -> list[dict]:
    return [deposition("Oxyde", thickness_nm=20), etch("Gravure", depth_nm=10), deposition("Nitrure", "Si3N4", thickness_nm=15)]


def _with_ids(process_steps: list[dict], ids: list[str | None]) -> list[dict]:
    return [{**step, "id": step_id} if step_id else dict(step) for step, step_id in zip(process_steps, ids)]


def _repository(slug: str):
    from spectre.plugins.experiments.repository import get_repository

    return get_repository(slug)


def _legacy_tip(slug: str, line: str, **metadata: object) -> str:
    """Une version de la piste écrite comme avant les ids d'étape - hors de Spectre, sans
    ``process_step_ids`` (``metadata`` remplace des clés de plus) ; renvoie son id."""
    import follow

    from spectre.plugins.experiments import repository

    outside = follow.Repository(repository.follow_repo_path(slug))
    parent = outside.get(outside.branches[line])
    builder = outside.derive(parent.id, title=parent.title, intent=parent.intent, hypothesis=parent.hypothesis)
    builder.metadata = {key: value for key, value in parent.metadata.items() if key != "process_step_ids"}
    builder.metadata.update(metadata)
    builder.form_answers = dict(parent.form_answers)
    builder.tags = ["avant-les-ids"]
    return builder.commit().id


def _objects_checksums(slug: str) -> dict[str, str]:
    from spectre.plugins.experiments import repository

    objects = repository.follow_repo_path(slug) / "objects"
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(objects.iterdir())}


# -- lecture ----------------------------------------------------------------------------------------


def test_a_version_saved_without_ids_reads_the_same_ids_every_time(client):
    from spectre.plugins.experiments import service

    slug = signup_with_microproject(client, "legacy-read@example.com")
    line = launch(client, slug, steps=_three_steps())["id"]
    legacy = _legacy_tip(slug, line)

    first = step_ids(client, slug, line)
    assert all(STEP_ID.fullmatch(step_id) for step_id in first)
    assert len(set(first)) == 3
    assert step_ids(client, slug, line) == first
    assert step_ids(client, slug, line, version=legacy) == first

    version = _repository(slug).get(legacy)
    assert "process_step_ids" not in version.metadata
    # ce qu'un ancien step_index devient (une preuve, un facteur de campagne) : TODO § 3
    repo = _repository(slug)
    assert [service.step_id_at(repo, version, i) for i in range(3)] == first
    assert service.step_id_at(repo, version, 3) is None and service.step_id_at(repo, version, -1) is None



def test_old_versions_of_a_line_read_the_same_ids_as_long_as_the_steps_keep_their_kinds(client):
    """Une version enregistrée sans ids reprend ceux de son premier parent tant que la suite des
    types d'étapes est la même (la règle d'une écriture sans ids) : la même étape a le même id dans
    toutes les anciennes versions d'une piste - un ancien ``step_index`` se traduit donc en un id que
    porte encore la dernière version."""
    from spectre.plugins.experiments import service

    slug = signup_with_microproject(client, "legacy-chain@example.com")
    line = launch(client, slug, steps=_three_steps())["id"]
    recorded = step_ids(client, slug, line)
    first = _legacy_tip(slug, line)
    second = _legacy_tip(slug, line)
    assert step_ids(client, slug, line, version=first) == recorded
    assert step_ids(client, slug, line, version=second) == recorded

    # une étape de moins (d'autres types d'étapes) : de nouveaux ids, que la version d'après reprend
    root_process = _repository(slug).get(second).metadata["structureforge_process"]
    shorter = {**root_process, "steps": root_process["steps"][:2]}
    changed = _legacy_tip(slug, line, structureforge_process=shorter)
    after = _legacy_tip(slug, line)
    changed_ids = step_ids(client, slug, line, version=changed)
    assert len(changed_ids) == 2 and not set(changed_ids) & set(recorded)
    assert step_ids(client, slug, line, version=after) == changed_ids == step_ids(client, slug, line)

    repo = _repository(slug)
    assert [service.step_id_at(repo, repo.get(first), i) for i in range(3)] == recorded
    assert [service.step_id_at(repo, repo.get(after), i) for i in range(2)] == changed_ids

def test_ids_are_recorded_at_launch_and_new_steps_get_one_from_the_server(client):
    slug = signup_with_microproject(client, "launch-ids@example.com")
    launched = launch(client, slug, steps=_three_steps())  # sans id : trois nouvelles étapes

    ids = step_ids(client, slug, launched["id"])
    assert all(STEP_ID.fullmatch(step_id) for step_id in ids) and len(set(ids)) == 3
    assert _repository(slug).get(launched["version_id"]).metadata["process_step_ids"] == ids
    # les étapes restent des étapes StructureForge : l'id est à part du procédé
    assert "id" not in _repository(slug).get(launched["version_id"]).metadata["structureforge_process"]["steps"][0]


def test_the_simulation_hands_out_the_ids_the_builder_sends_back_at_launch(client):
    slug = signup_with_microproject(client, "simulate-ids@example.com")
    simulated = simulate(client, {"substrate": substrate(), "steps": _three_steps()})
    assert simulated.status_code == 200, simulated.text
    handed = simulated.json()["step_ids"]

    launched = launch(client, slug, steps=_with_ids(_three_steps(), handed))
    assert step_ids(client, slug, launched["id"]) == handed


# -- écriture : conservation ------------------------------------------------------------------------


def test_an_evolution_keeps_the_ids_of_the_steps_it_keeps(client):
    slug = signup_with_microproject(client, "keep-ids@example.com")
    line = launch(client, slug, steps=_three_steps())["id"]
    a, b, c = step_ids(client, slug, line)
    oxide, gravure, nitride = _three_steps()

    # un paramètre modifié
    thicker = {**oxide, "thickness": {"value": 40, "unit": "nm"}}
    evolve(client, slug, line, steps=_with_ids([thicker, gravure, nitride], [a, b, c]))
    assert step_ids(client, slug, line) == [a, b, c]
    assert process(client, slug, line)["steps"][0]["thickness"]["value"] == 40

    # une étape déplacée : son id la suit
    evolve(client, slug, line, steps=_with_ids([gravure, thicker, nitride], [b, a, c]))
    assert step_ids(client, slug, line) == [b, a, c]

    # une étape insérée (sans id) : un id neuf, les autres gardent le leur
    inserted = deposition("Alumine", "Al2O3", recipe="ALD Conformal", thickness_nm=5)
    evolve(client, slug, line, steps=_with_ids([gravure, inserted, thicker, nitride], [b, None, a, c]))
    after_insert = step_ids(client, slug, line)
    assert after_insert[0] == b and after_insert[2:] == [a, c]
    assert STEP_ID.fullmatch(after_insert[1]) and after_insert[1] not in (a, b, c)

    # une étape supprimée : les autres gardent le leur
    evolve(client, slug, line, steps=_with_ids([gravure, thicker, nitride], [b, a, c]))
    assert step_ids(client, slug, line) == [b, a, c]


def test_a_duplicated_step_gets_a_new_id(client):
    slug = signup_with_microproject(client, "duplicate-ids@example.com")
    line = launch(client, slug, steps=_three_steps())["id"]
    a, b, c = step_ids(client, slug, line)
    oxide, gravure, nitride = _three_steps()

    evolve(client, slug, line, steps=_with_ids([oxide, oxide, gravure, nitride], [a, a, b, c]))
    ids = step_ids(client, slug, line)
    assert ids[0] == a and ids[2:] == [b, c]
    assert STEP_ID.fullmatch(ids[1]) and ids[1] not in (a, b, c)


def test_malformed_ids_are_replaced_by_the_server(client):
    slug = signup_with_microproject(client, "malformed-ids@example.com")
    launched = launch(client, slug, steps=_with_ids(_three_steps(), ["etape-1", "st_XYZ", fixed_step_id(7)]))
    ids = step_ids(client, slug, launched["id"])
    assert ids[2] == fixed_step_id(7)
    assert all(STEP_ID.fullmatch(step_id) for step_id in ids) and len(set(ids)) == 3


def test_a_client_that_sends_no_id_keeps_them_while_the_kinds_of_steps_stay_the_same(client):
    slug = signup_with_microproject(client, "id-less@example.com")
    line = launch(client, slug, steps=_three_steps())["id"]
    original = step_ids(client, slug, line)
    oxide, gravure, nitride = _three_steps()

    evolve(client, slug, line, steps=[{**oxide, "thickness": {"value": 25, "unit": "nm"}}, gravure, nitride])
    assert step_ids(client, slug, line) == original

    evolve(client, slug, line, steps=[gravure, oxide, nitride])  # la suite des types change
    assert not set(step_ids(client, slug, line)) & set(original)


def test_light_writes_carry_the_ids(client):
    slug = signup_with_microproject(client, "light-ids@example.com")
    line = launch(client, slug, steps=_three_steps())["id"]
    ids = step_ids(client, slug, line)
    tagged = tag(client, slug, line, ["suivi"])
    assert _repository(slug).get(tagged["version_id"]).metadata["process_step_ids"] == ids


def test_a_fork_keeps_the_ids_the_builder_sends_back(client):
    slug = signup_with_microproject(client, "fork-ids@example.com")
    source = launch(client, slug, steps=_three_steps())
    ids = step_ids(client, slug, source["id"])
    forked = launch(
        client,
        slug,
        title="Variante",
        intent="Partir de la ref",
        steps=_with_ids(_three_steps(), ids),
        from_version={"experiment_id": source["id"], "version_id": source["version_id"]},
    )
    assert forked["id"] != source["id"]
    assert step_ids(client, slug, forked["id"]) == ids


# -- versions : les ids ne changent pas la structure ------------------------------------------------


def test_receiving_ids_alone_creates_no_version(client):
    slug = signup_with_microproject(client, "no-op-ids@example.com")
    line = launch(client, slug, title="Essai", intent="Verifier", steps=_three_steps())["id"]
    legacy = _legacy_tip(slug, line)
    derived = step_ids(client, slug, line)

    # le constructeur renvoie les ids lus sur une version qui ne les avait pas écrits : rien de neuf
    response = post_evolve(client, slug, line, title="Essai", intent="Verifier", steps=_with_ids(_three_steps(), derived))
    assert response.status_code == 200, response.text
    assert response.json()["version_id"] == legacy

    # un client qui n'envoie aucun id non plus
    response = post_evolve(client, slug, line, title="Essai", intent="Verifier", steps=_three_steps())
    assert response.status_code == 200, response.text
    assert response.json()["version_id"] == legacy

    # ni une écriture légère sans effet (les ids reportés ne sont pas une différence)
    assert tag(client, slug, line, ["avant-les-ids"])["version_id"] == legacy
    assert len(versions(client, slug, line)) == 2


def test_a_version_that_records_ids_is_no_structural_change(client):
    from spectre.plugins.experiments import versioning

    slug = signup_with_microproject(client, "structural-ids@example.com")
    line = launch(client, slug, title="Essai", intent="Verifier", steps=_three_steps())["id"]
    legacy = _legacy_tip(slug, line)
    derived = step_ids(client, slug, line)

    # une autre intention, le même procédé : la nouvelle version enregistre les ids, rien de structurel
    evolved = evolve(client, slug, line, title="Essai", intent="Autre intention", steps=_with_ids(_three_steps(), derived))
    assert _repository(slug).get(evolved["version_id"]).metadata["process_step_ids"] == derived
    frise = versions(client, slug, line)
    assert [v["change_level"] for v in frise] == ["initial", "none", "none"]
    assert len({v["version"] for v in frise}) == 1

    before = _repository(slug).get(legacy).metadata
    after = _repository(slug).get(evolved["version_id"]).metadata
    assert versioning.structure_signature(before) == versioning.structure_signature(after)
    assert not versioning.changes_structure(before, after)
    assert get_experiment(client, slug, line)["structure_svg"]


def test_a_version_saved_without_ids_is_never_rewritten(client):
    slug = signup_with_microproject(client, "immutable@example.com")
    line = launch(client, slug, steps=_three_steps())["id"]
    _legacy_tip(slug, line)
    derived = step_ids(client, slug, line)
    before = _objects_checksums(slug)

    tag(client, slug, line, ["lu", "relu"])
    evolve(client, slug, line, intent="Une suite", steps=_with_ids(_three_steps(), derived))
    step_ids(client, slug, line)

    after = _objects_checksums(slug)
    assert {name: after.get(name) for name in before} == before  # aucun objet existant n'a changé
    assert len(after) == len(before) + 2
    assert step_ids(client, slug, line) == derived  # les versions suivantes gardent les ids lus


def test_pictures_drop_the_ids_and_a_redrawn_process_gets_new_ones(client):
    slug = signup_with_microproject(client, "images-ids@example.com")
    line = launch(client, slug, steps=_three_steps())["id"]
    before = step_ids(client, slug, line)

    pictured = evolve_image(client, slug, line, [{"image_id": upload_structure_image(client, slug), "kind": "schema"}])
    assert "process_step_ids" not in _repository(slug).get(pictured["version_id"]).metadata

    evolve(client, slug, line, steps=_three_steps())
    redrawn = step_ids(client, slug, line)
    assert all(STEP_ID.fullmatch(step_id) for step_id in redrawn) and not set(redrawn) & set(before)


# -- campagnes --------------------------------------------------------------------------------------


def test_a_campaign_names_its_factors_by_step_id(client):
    slug = signup_with_microproject(client, "campaign-ids@example.com")
    process_steps = identified([deposition("Oxyde"), deposition("Nitrure", "Si3N4", thickness_nm=10)])
    plan = {
        "factors": [
            {"step_id": fixed_step_id(2), "field": "thickness", "values": [5, 15]},
            {"step_id": "substrate", "field": "thickness", "values": [40, 80]},
        ]
    }
    campaign = launch_campaign(client, slug, plan, steps=process_steps, entities=[{"sample_id": "W1"}])

    assert variants(client, slug, campaign["id"])["factor_labels"] == ["Épaisseur — Nitrure", "Épaisseur — Substrat"]
    assert step_ids(client, slug, campaign["id"]) == [fixed_step_id(1), fixed_step_id(2)]
    recorded = _repository(slug).get(campaign["version_id"]).metadata["campaign_plan"]
    assert [factor["step_id"] for factor in recorded["factors"]] == [fixed_step_id(2), "substrate"]
    assert all("step_index" not in factor for factor in recorded["factors"])


def test_a_campaign_factor_on_an_unknown_step_is_refused(client):
    slug = signup_with_microproject(client, "campaign-unknown@example.com")
    response = post_launch(client, slug, kind="campaign", plan=campaign_plan([10, 20], step_id=fixed_step_id(9)), title="Campagne", intent="x")
    assert response.status_code == 422
    assert "étape" in response.json()["detail"]

    old_style = {"factors": [{"step_index": 0, "field": "thickness", "values": [10, 20]}]}
    assert post_launch(client, slug, kind="campaign", plan=old_style, title="Campagne", intent="x").status_code == 422


def test_a_campaign_launched_from_a_version_keeps_the_step_ids_and_records_them_in_its_plan(client):
    slug = signup_with_microproject(client, "campaign-fork@example.com")
    source = launch(client, slug, steps=_three_steps())
    a, b, c = step_ids(client, slug, source["id"])
    campaign = launch_campaign(
        client,
        slug,
        campaign_plan([30, 50], step_id=c),
        steps=_with_ids(_three_steps(), [a, b, c]),
        from_version={"experiment_id": source["id"], "version_id": source["version_id"]},
        entities=[{"sample_id": "W1"}],
    )
    assert step_ids(client, slug, campaign["id"]) == [a, b, c]
    assert _repository(slug).get(campaign["version_id"]).metadata["campaign_plan"]["factors"][0]["step_id"] == c



def test_a_campaign_launched_from_a_version_without_ids_names_its_factors_by_that_versions_ids(client):
    """Comme une fourche sans ids : un client qui n'envoie aucun id vise les étapes par ceux de la
    version de départ (ici une version enregistrée avant eux)."""
    slug = signup_with_microproject(client, "campaign-no-ids@example.com")
    source = launch(client, slug, steps=_three_steps())
    legacy = _legacy_tip(slug, source["id"])
    a, b, c = step_ids(client, slug, source["id"], version=legacy)
    origin = {"experiment_id": source["id"], "version_id": legacy}

    campaign = launch_campaign(
        client, slug, campaign_plan([30, 50], step_id=c), steps=_three_steps(), from_version=origin, entities=[{"sample_id": "W1"}]
    )
    assert step_ids(client, slug, campaign["id"]) == [a, b, c]
    assert _repository(slug).get(campaign["version_id"]).metadata["campaign_plan"]["factors"][0]["step_id"] == c

    # d'autres types d'étapes que la version de départ : ses ids ne s'appliquent pas
    response = post_launch(
        client, slug, kind="campaign", plan=campaign_plan([30, 50], step_id=a), steps=_three_steps()[:2],
        from_version=origin, title="Campagne", intent="x", entities=[{"sample_id": "W1"}],
    )
    assert response.status_code == 422 and "étape" in response.json()["detail"]

def test_a_campaign_recorded_with_step_indexes_still_reads(client):
    from spectre.plugins.experiments import service

    slug = signup_with_microproject(client, "old-campaign@example.com")
    campaign = launch_campaign(client, slug, campaign_plan([10, 20, 30]), entities=[{"sample_id": "W1"}])
    old_plan = {"factors": [{"step_index": 0, "field": "thickness", "values": [10, 20, 30], "scale": "linear", "label": None}]}
    legacy = _legacy_tip(slug, campaign["id"], campaign_plan=old_plan)

    detail = get_experiment(client, slug, campaign["id"])
    assert detail["version_id"] == legacy and detail["is_batch"] is True
    matrix = variants(client, slug, campaign["id"])
    assert matrix["entity_count"] == 3 and matrix["factor_values"] == [[10], [20], [30]]
    ids = step_ids(client, slug, campaign["id"])
    assert len(ids) == 1 and STEP_ID.fullmatch(ids[0])
    # le step_index du plan d'avant se traduit en id d'étape
    version = _repository(slug).get(legacy)
    assert service.step_id_at(_repository(slug), version, version.metadata["campaign_plan"]["factors"][0]["step_index"]) == ids[0]
