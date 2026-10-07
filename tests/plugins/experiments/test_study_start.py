"""« D'où part-elle ? » : une nouvelle étude part de la référence, de la meilleure plaque d'une étude
(``from_version`` avec ``place`` : sa variante, sur de nouvelles plaques), ou de plusieurs études
combinées au marché (``composition`` : la structure assemblée brique par brique, les sources
retenues, reliées dans l'arbre) ; dans tous les cas, une plaque témoin peut répéter exactement la
dernière version connue de la référence (``reference_repeat`` : une place de plus, à la fin)."""

from __future__ import annotations

from support.experiments import (
    evolve,
    experiments_url,
    from_wafers,
    get_experiment,
    launch,
    launch_campaign,
    launch_declared,
    launch_body,
    lineage,
    post_from_wafers,
    track_entities,
    variants,
)
from support.microprojects import signup_with_microproject
from support.structures import deposition, fixed_step_id

REF = {"reference": "led-bleue", "version": "1.3"}


def _post(client, slug, **fields):
    return client.post(experiments_url(slug), json=launch_body(**fields))


# -- depuis une plaque ------------------------------------------------------------------------------


def test_starting_from_the_best_wafer_of_a_campaign_records_it_and_descends_from_its_study(client):
    slug = signup_with_microproject(client, "start-wafer@example.com", "Départ")
    campaign = launch_campaign(client, slug, entities=[{"sample_id": "W1"}, {"sample_id": "W2"}, {"sample_id": "W3"}])
    study = launch(
        client, slug, title="Suite W2", entities=[{"sample_id": "N1"}],
        from_version={"experiment_id": campaign["id"], "version_id": campaign["version_id"], "place": 1},
    )
    detail = get_experiment(client, slug, study["id"])
    assert detail["start_wafer"] == {
        "experiment_id": campaign["id"], "version_id": campaign["version_id"], "place": 1, "sample_id": "W2", "variant": 1,
    }
    assert detail["parents"] == [campaign["version_id"]]
    assert [e["sample_id"] for e in detail["physical_tracking"]] == ["N1"]  # de nouvelles plaques
    # la même structure que la campagne (sa variante 20 nm est sa base) : un nœud relié à elle
    assert {"parent": campaign["version_id"], "child": study["version_id"]} in lineage(client, slug)["edges"]


def test_a_start_place_outside_the_split_is_refused(client):
    slug = signup_with_microproject(client, "start-wafer-out@example.com", "Départ")
    simple = launch(client, slug)
    response = _post(client, slug, from_version={"experiment_id": simple["id"], "place": 4})
    assert response.status_code == 422 and response.json()["code"] == "place_out_of_range"


# -- la plaque témoin -------------------------------------------------------------------------------


def test_a_campaign_gets_its_witness_wafer_after_its_variants(client):
    slug = signup_with_microproject(client, "witness-campaign@example.com", "Témoin")
    campaign = launch_campaign(
        client, slug, entities=[{"sample_id": "W1"}, {}, {}, {"sample_id": "T1"}], reference_repeat=REF, reference_place=None,
    )
    detail = get_experiment(client, slug, campaign["id"])
    assert detail["reference_repeat"] == {**REF, "place": 3}
    assert [e.get("sample_id") for e in detail["physical_tracking"]] == ["W1", None, None, "T1"]
    assert len(variants(client, slug, campaign["id"])["labels"]) == 3  # la témoin n'est pas une variante
    # les places se modifient avec elle : une par variante, plus la témoin
    entries = [{"sample_id": "W1"}, {"sample_id": "W2"}, {}, {"sample_id": "T1"}]
    after = track_entities(client, slug, campaign["id"], entries, if_match=detail["version_id"])
    assert get_experiment(client, slug, campaign["id"])["reference_repeat"]["place"] == 3
    refused = client.put(
        f"{experiments_url(slug)}/{campaign['id']}/entities", json={"entities": entries[:3]}, headers={"If-Match": f'"{after["version_id"]}"'}
    )
    assert refused.status_code == 422 and refused.json()["code"] == "entity_count"


def test_a_simple_study_with_a_witness_and_repeats(client):
    slug = signup_with_microproject(client, "witness-simple@example.com", "Témoin")
    study = launch(client, slug, entities=[{"sample_id": "A"}, {"sample_id": "B"}, {"sample_id": "T"}], repeats=True, reference_repeat=REF)
    detail = get_experiment(client, slug, study["id"])
    assert detail["repeats"] is True and detail["reference_repeat"] == {**REF, "place": 2}
    # sans autre plaque nommée : une place de la structure, puis la témoin
    alone = get_experiment(client, slug, launch(client, slug, title="Seule", entities=[], reference_repeat=REF)["id"])
    assert len(alone["physical_tracking"]) == 2 and alone["reference_repeat"]["place"] == 1 and alone["repeats"] is False
    # une place ajoutée se met avant elle : la témoin reste la dernière
    track_entities(client, slug, study["id"], [{"sample_id": "A"}, {"sample_id": "B"}, {"sample_id": "C"}, {"sample_id": "T"}], if_match=detail["version_id"])
    detail = get_experiment(client, slug, study["id"])
    assert detail["reference_repeat"]["place"] == 3
    # une évolution de la structure la garde, en dernière place ; une structure en images, non
    evolved = evolve(client, slug, study["id"], entities=[{"sample_id": "A"}, {"sample_id": "T"}], if_match=detail["version_id"])
    assert get_experiment(client, slug, study["id"])["reference_repeat"]["place"] == 1
    detail = get_experiment(client, slug, study["id"])
    assert detail["version_id"] == evolved["version_id"]
    # la témoin ne se retire pas
    refused = client.put(
        f"{experiments_url(slug)}/{study['id']}/entities", json={"entities": [{"sample_id": "A"}]}, headers={"If-Match": f'"{detail["version_id"]}"'}
    )
    assert refused.status_code == 422 and refused.json()["code"] == "entity_count"


def test_the_witness_is_not_a_starting_wafer(client):
    slug = signup_with_microproject(client, "witness-start@example.com", "Témoin")
    study = launch(client, slug, entities=[{"sample_id": "A"}, {"sample_id": "T"}], reference_repeat=REF)
    response = _post(client, slug, from_version={"experiment_id": study["id"], "place": 1})
    assert response.status_code == 422 and response.json()["code"] == "place_is_reference_repeat"
    response = post_from_wafers(client, slug, slug, study["id"], ["T"])
    assert response.status_code == 422 and response.json()["code"] == "place_is_reference_repeat"
    assert from_wafers(client, slug, slug, study["id"], ["A"])["id"]


def test_a_witness_needs_a_drawn_structure_and_no_duplicate_wafer(client):
    slug = signup_with_microproject(client, "witness-refused@example.com", "Témoin")
    response = client.post(
        experiments_url(slug),
        json={**launch_body(kind="declared", entities=[], description="d", factors=["x"], wafers=[{"values": ["1"]}]), "reference_repeat": REF},
    )
    assert response.status_code == 422 and response.json()["code"] == "reference_repeat_kind"
    response = _post(client, slug, entities=[{"sample_id": "A"}, {"sample_id": "A"}], reference_repeat=REF)
    assert response.status_code == 422
    assert launch_declared(client, slug)["id"]


# -- combiner au marché -----------------------------------------------------------------------------


def _bricked(name: str, ebl_nm: float) -> dict:
    return {
        "steps": [{"id": fixed_step_id(1), **deposition("Zone active", "InGaN", thickness_nm=3)}, {"id": fixed_step_id(2), **deposition("EBL", "AlGaN", thickness_nm=ebl_nm)}],
        "bricks": [
            {"group_id": "brick-za", "name": "Zone active", "source": None, "step_indexes": [0]},
            {"group_id": "brick-ebl", "name": "EBL", "source": None, "step_indexes": [1]},
        ],
        "title": name,
    }


def test_a_composed_study_descends_from_its_main_source_and_links_the_others(client):
    slug = signup_with_microproject(client, "compose-launch@example.com", "Marché")
    a = launch(client, slug, entities=[{"sample_id": "A1"}, {"sample_id": "A2"}], repeats=True, **_bricked("A", 20))
    b = launch(client, slug, entities=[{"sample_id": "B1"}], reference_origin=REF, **_bricked("B", 15))
    composition = {
        "sources": [
            {"kind": "study", "label": "A · A2", "experiment_id": a["id"], "place": 1},
            {"kind": "study", "label": "B · B1", "experiment_id": b["id"], "version_id": b["version_id"], "place": 0},
            {"kind": "reference", "label": "LED bleue 1.3", **REF},
        ],
        "bricks": [{"name": "Substrat", "source": 0}, {"name": "Zone active", "source": 0}, {"name": "EBL", "source": 1}],
    }
    composed = launch(client, slug, title="A + EBL de B", entities=[{"sample_id": "C1"}], composition=composition, **{k: v for k, v in _bricked("C", 15).items() if k != "title"})
    detail = get_experiment(client, slug, composed["id"])
    assert detail["parents"] == [a["version_id"]]
    sources = detail["composition"]["sources"]
    assert sources[0]["version_id"] == a["version_id"] and sources[0]["sample_id"] == "A2"
    assert sources[1]["sample_id"] == "B1" and sources[2] == {"kind": "reference", "label": "LED bleue 1.3", **REF}
    assert detail["composition"]["bricks"][2] == {"name": "EBL", "source": 1}
    # A n'a pas d'origine de référence : celle citée dans la combinaison
    assert detail["reference_origin"] == REF
    edges = lineage(client, slug)["edges"]
    assert {"parent": b["version_id"], "child": composed["version_id"], "composed": True} in edges
    assert {"parent": a["version_id"], "child": composed["version_id"]} in edges


def test_a_composition_from_a_reference_first_is_a_root_linked_to_its_studies(client):
    slug = signup_with_microproject(client, "compose-root@example.com", "Marché")
    a = launch(client, slug, **_bricked("A", 20))
    composition = {
        "sources": [{"kind": "reference", "label": "LED bleue 1.3", **REF}, {"kind": "study", "label": "A", "experiment_id": a["id"]}],
        "bricks": [{"name": "EBL", "source": 1}],
    }
    composed = launch(client, slug, title="Réf + EBL de A", composition=composition)
    detail = get_experiment(client, slug, composed["id"])
    assert detail["parents"] == [] and detail["reference_origin"] == REF
    assert {"parent": a["version_id"], "child": composed["version_id"], "composed": True} in lineage(client, slug)["edges"]


def test_composition_refusals(client):
    slug = signup_with_microproject(client, "compose-refused@example.com", "Marché")
    a = launch(client, slug)
    two = [{"kind": "study", "label": "A", "experiment_id": a["id"]}, {"kind": "reference", "label": "R", **REF}]
    response = _post(client, slug, composition={"sources": two, "bricks": [{"name": "EBL", "source": 3}]})
    assert response.status_code == 422 and response.json()["code"] == "bad_composition"
    response = _post(client, slug, composition={"sources": [two[0], {"kind": "study", "label": "?", "experiment_id": "inconnue"}]})
    assert response.status_code == 404
    response = _post(client, slug, composition={"sources": two}, from_version={"experiment_id": a["id"]})
    assert response.status_code == 422
