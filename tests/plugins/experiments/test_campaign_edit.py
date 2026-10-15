"""Un split modifiable dans l'éditeur, à deux niveaux : la campagne évoluée sur sa piste (procédé de
base et plan reconstitués, nouvelle version X.Y), et une seule variante retouchée à la main
(``PUT .../variant-overrides/{n}``, sans nouveau numéro - lue partout où la variante se lit)."""

from __future__ import annotations

from support.experiments import evolve, experiment_url, get_experiment, launch_campaign, post_evolve, process, variants, versions
from support.http import assert_ok
from support.microprojects import signup_with_microproject
from support.notebook import add_manual
from support.structures import campaign_plan, deposition, fixed_step_id, identified, steps

STACK = identified([deposition("Oxyde", thickness_nm=20), deposition("Nitrure", "Si3N4", thickness_nm=10)])


def _slug(client) -> str:
    return signup_with_microproject(client, "split-editeur@example.com", "Salle blanche")


def _numbers(client, slug, ref) -> list[tuple[str, str]]:
    return [(v["version"], v["change_level"]) for v in versions(client, slug, ref)]


def _override(client, slug, ref, variant, body, if_match=None, expect=200):
    headers = {"If-Match": f'"{if_match}"'} if if_match else {}
    response = client.put(f"{experiment_url(slug, ref)}/variant-overrides/{variant}", json=body, headers=headers)
    assert response.status_code == expect, response.text
    return response.json()


# -- 1. évoluer un split sur sa piste --------------------------------------------------------------


def test_the_detail_of_a_campaign_carries_its_plan(client):
    slug = _slug(client)
    detail = launch_campaign(client, slug, plan=campaign_plan([10, 20, 30], scale="list", label="Oxyde fin"))
    assert detail["campaign_plan"] == {"factors": [{"step_id": fixed_step_id(1), "field": "thickness", "values": [10, 20, 30], "scale": "list", "label": "Oxyde fin"}]}
    assert detail["variant_overrides"] == []


def test_evolving_a_campaign_stays_on_its_line_and_recomputes_the_split(client):
    slug = _slug(client)
    campaign = launch_campaign(
        client, slug, entities=[{"sample_id": "W1", "location": "A"}, {"sample_id": "W2"}, {"sample_id": "W3"}], fdl=["FDL-1"], reference_place=0
    )
    note = add_manual(client, slug, campaign["id"], "Mesure")
    evolved = evolve(client, slug, campaign["id"], kind="campaign", plan=campaign_plan([10, 20, 30, 40]), reference_place=0)
    assert evolved["id"] == campaign["id"] and evolved["is_batch"] is True
    assert evolved["campaign_plan"]["factors"][0]["values"] == [10, 20, 30, 40]
    # les plaques à leur place, une place de plus à associer ; la FDL et le cahier reportés
    assert evolved["physical_tracking"] == [
        {"sample_id": "W1", "location": "A"},
        {"sample_id": "W2", "location": None},
        {"sample_id": "W3", "location": None},
        {"sample_id": None, "location": None},
    ]
    assert evolved["fdl"] == ["FDL-1"] and evolved["notebook_count"] == 1 and evolved["reference_place"] == 0
    matrix = variants(client, slug, campaign["id"])
    assert matrix["entity_count"] == 4 and matrix["factor_values"] == [[10], [20], [30], [40]]
    # une valeur de plus au split : un changement mineur, sur la même piste
    assert _numbers(client, slug, campaign["id"]) == [("1.0", "initial"), ("1.0", "none"), ("1.1", "minor")]
    assert note is not None


def test_evolving_a_campaign_with_new_wafers_puts_them_at_their_place(client):
    slug = _slug(client)
    campaign = launch_campaign(client, slug, entities=[{"sample_id": "W1"}])
    evolved = evolve(
        client, slug, campaign["id"], kind="campaign", plan=campaign_plan([10, 20]), entities=[{"sample_id": "W7"}, {"sample_id": "W8"}], reference_place=1
    )
    assert evolved["physical_tracking"] == [{"sample_id": "W7", "location": None}, {"sample_id": "W8", "location": None}]
    assert evolved["reference_place"] == 1


def test_evolving_a_campaign_with_a_witness_keeps_it_last(client):
    slug = _slug(client)
    campaign = launch_campaign(
        client,
        slug,
        plan=campaign_plan([10, 20]),
        entities=[{"sample_id": "W1"}, {"sample_id": "W2"}, {"sample_id": "T1"}],
        reference_repeat={"reference": "ref-a", "version": "1.0"},
    )
    assert campaign["reference_repeat"]["place"] == 2
    # trois variantes, aucune plaque donnée : celles en place, le témoin toujours dernier
    evolved = evolve(client, slug, campaign["id"], kind="campaign", plan=campaign_plan([10, 20, 30]))
    assert [e["sample_id"] for e in evolved["physical_tracking"]] == ["W1", "W2", None, "T1"]
    assert evolved["reference_repeat"] == {"reference": "ref-a", "version": "1.0", "place": 3}
    # les plaques données, le témoin en dernier comme le constructeur l'envoie
    again = evolve(
        client, slug, campaign["id"], kind="campaign", plan=campaign_plan([10, 20]), entities=[{"sample_id": "W1"}, {"sample_id": "W9"}, {"sample_id": "T1"}]
    )
    assert [e["sample_id"] for e in again["physical_tracking"]] == ["W1", "W9", "T1"]
    assert again["reference_repeat"]["place"] == 2


def test_a_changed_base_process_of_a_campaign_bumps_the_version(client):
    slug = _slug(client)
    campaign = launch_campaign(client, slug, steps=STACK, plan=campaign_plan([10, 20]))
    thicker = [STACK[0], {**STACK[1], "thickness": {"value": 30, "unit": "nm"}}]
    evolve(client, slug, campaign["id"], kind="campaign", steps=thicker, plan=campaign_plan([10, 20]))
    assert _numbers(client, slug, campaign["id"])[-1] == ("1.1", "minor")
    metal = {"id": fixed_step_id(3), **deposition("Métal", "Al", thickness_nm=5)}
    evolve(client, slug, campaign["id"], kind="campaign", steps=[*thicker, metal], plan=campaign_plan([10, 20]))
    assert _numbers(client, slug, campaign["id"])[-1] == ("2.0", "major")
    # rien n'a changé : pas de nouvelle version (200, la pointe telle quelle)
    same = post_evolve(client, slug, campaign["id"], kind="campaign", steps=[*thicker, metal], plan=campaign_plan([10, 20]), title="Essai", intent="Suite")
    assert same.status_code == 200
    assert same.json()["version_id"] == get_experiment(client, slug, campaign["id"])["version_id"]
    assert _numbers(client, slug, campaign["id"])[-1] == ("2.0", "major")


def test_too_many_wafers_for_the_new_split_is_refused(client):
    slug = _slug(client)
    campaign = launch_campaign(client, slug, entities=[{"sample_id": "W1"}, {"sample_id": "W2"}, {"sample_id": "W3"}])
    response = post_evolve(client, slug, campaign["id"], kind="campaign", plan=campaign_plan([10, 20]), title="Campagne", intent="Moins")
    assert response.status_code == 422
    assert response.json()["code"] == "too_many_entities"


# -- 2. retoucher une seule variante ---------------------------------------------------------------


def _fixed_body(thickness_nm: float = 55) -> dict:
    """Le procédé corrigé de la variante : la même étape (même id), une autre épaisseur."""
    return {"substrate": {"material": "Si", "domain_width": {"value": 200, "unit": "nm"}, "thickness": {"value": 50, "unit": "nm"}}, "steps": steps(thickness_nm)}


def test_a_variant_override_replaces_its_process_and_drawing_without_a_new_number(client):
    slug = _slug(client)
    campaign = launch_campaign(client, slug)
    before = variants(client, slug, campaign["id"])
    fixed = _override(client, slug, campaign["id"], 1, _fixed_body(55), if_match=campaign["version_id"])
    assert fixed["variant_overrides"] == [1]
    assert fixed["version_id"] != campaign["version_id"]
    after = variants(client, slug, campaign["id"])
    assert after["overridden"] == [1]
    assert after["svgs"][0] == before["svgs"][0] and after["svgs"][2] == before["svgs"][2]
    assert after["svgs"][1] != before["svgs"][1]
    # le procédé de la variante est la retouche ; les autres, le calcul du plan
    corrected = process(client, slug, campaign["id"], variant=1)
    assert corrected["steps"][0]["thickness"]["value"] == 55 and corrected["steps"][0]["id"] == fixed_step_id(1)
    assert process(client, slug, campaign["id"], variant=2)["steps"][0]["thickness"]["value"] == 30
    # une retouche : le numéro ne bouge pas
    assert _numbers(client, slug, campaign["id"]) == [("1.0", "initial"), ("1.0", "patch")]


def test_a_variant_override_is_read_by_the_promotion_and_the_comparator(client):
    from spectre.plugins.experiments import service as experiments
    from spectre.plugins.experiments.repository import get_repository
    from spectre.plugins.references.service import snapshot_of
    from spectre.plugins.structures import kinds

    slug = _slug(client)
    campaign = launch_campaign(client, slug)
    _override(client, slug, campaign["id"], 2, _fixed_body(70))
    repo = get_repository(slug)
    tip = experiments.tip_of(repo, campaign["id"])
    snapshot = snapshot_of(repo, tip, 2)
    assert snapshot["metadata"]["structureforge_process"]["steps"][0]["thickness"]["value"] == 70
    # la structure simulée de la variante est celle de la retouche
    layers = kinds.ProcessLot.model_validate(tip.structure).entries[2].layers
    top = max(point[1] for ring in layers[-1].rings for point in ring["exterior"])
    assert abs(top - 70) < 1e-6  # 70 nm d'oxyde au-dessus du substrat (y = 0 à sa surface)
    assert kinds.variant_process(tip.metadata, experiments.step_ids_of(repo, tip), 2)["steps"][0]["thickness"]["value"] == 70


def test_clearing_a_variant_override_puts_the_computed_variant_back(client):
    slug = _slug(client)
    campaign = launch_campaign(client, slug)
    before = variants(client, slug, campaign["id"])
    _override(client, slug, campaign["id"], 1, _fixed_body(55))
    response = client.delete(f"{experiment_url(slug, campaign['id'])}/variant-overrides/1")
    restored = assert_ok(response)
    assert restored["variant_overrides"] == []
    after = variants(client, slug, campaign["id"])
    assert after["svgs"] == before["svgs"] and after["overridden"] == []
    assert process(client, slug, campaign["id"], variant=1)["steps"][0]["thickness"]["value"] == 20
    # sans retouche, rien à retirer : la pointe telle quelle
    again = assert_ok(client.delete(f"{experiment_url(slug, campaign['id'])}/variant-overrides/1"))
    assert again["version_id"] == restored["version_id"]


def test_a_variant_override_may_add_a_step(client):
    slug = _slug(client)
    campaign = launch_campaign(client, slug)
    body = _fixed_body(20)
    body["steps"] = [*body["steps"], deposition("Métal", "Al", thickness_nm=5)]
    fixed = _override(client, slug, campaign["id"], 0, body)
    corrected = process(client, slug, campaign["id"], variant=0)
    assert [s["name"] for s in corrected["steps"]] == ["Oxyde", "Métal"]
    assert corrected["steps"][0]["id"] == fixed_step_id(1) and corrected["steps"][1]["id"].startswith("st_")
    assert fixed["variant_overrides"] == [0]


def test_a_variant_override_is_refused_outside_a_campaign_or_its_variants(client):
    slug = _slug(client)
    campaign = launch_campaign(client, slug)
    assert _override(client, slug, campaign["id"], 3, _fixed_body(), expect=422)["code"] == "unknown_variant"
    from support.experiments import launch

    simple = launch(client, slug, title="Simple")
    assert _override(client, slug, simple["id"], 0, _fixed_body(), expect=422)["code"] == "not_a_campaign"


def test_an_evolution_drops_the_variant_overrides(client):
    slug = _slug(client)
    campaign = launch_campaign(client, slug)
    _override(client, slug, campaign["id"], 1, _fixed_body(55))
    evolved = evolve(client, slug, campaign["id"], kind="campaign", plan=campaign_plan([10, 20, 30, 40]))
    assert evolved["variant_overrides"] == []
    assert process(client, slug, campaign["id"], variant=1)["steps"][0]["thickness"]["value"] == 20
