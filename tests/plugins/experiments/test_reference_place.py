"""La plaque de référence d'une campagne (``reference_place``) et, sans elle, la plaque d'une étude
proche citée pour comparaison (``comparison_reference``)."""

from __future__ import annotations

from support.experiments import combine, evolve, get_experiment, launch, launch_campaign, post_launch, variants
from support.microprojects import signup_with_microproject
from support.structures import campaign_plan


def _slug(client) -> str:
    return signup_with_microproject(client, "owner@example.com", "Salle blanche")


def test_reference_place_chosen_at_launch(client):
    slug = _slug(client)
    detail = launch_campaign(client, slug, reference_place=2)
    assert detail["reference_place"] == 2
    assert detail["comparison_reference"] is None
    assert get_experiment(client, slug, detail["id"])["reference_place"] == 2
    assert variants(client, slug, detail["id"])["reference_index"] == 2


def test_no_reference_in_the_split_with_a_comparison_wafer(client):
    slug = _slug(client)
    before = launch(client, slug, title="Etude precedente", entities=[{"sample_id": "W9"}])
    cited = {"experiment_id": before["id"], "version_id": before["version_id"], "sample_id": "W9"}
    detail = launch_campaign(client, slug, reference_place=None, comparison_reference=cited)
    assert detail["reference_place"] is None
    assert detail["comparison_reference"] == cited
    assert variants(client, slug, detail["id"])["reference_index"] is None


def test_no_reference_and_nothing_cited(client):
    slug = _slug(client)
    detail = launch_campaign(client, slug, reference_place=None)
    assert detail["reference_place"] is None
    assert detail["comparison_reference"] is None


def test_a_reference_place_drops_the_comparison(client):
    slug = _slug(client)
    detail = launch_campaign(client, slug, reference_place=1, comparison_reference={"experiment_id": "ailleurs", "sample_id": "W9"})
    assert detail["reference_place"] == 1
    assert detail["comparison_reference"] is None


def test_campaign_without_the_key_keeps_its_first_variant_as_reference(client):
    # une campagne lancée sans rien dire (comme avant ce choix) : la première variante
    slug = _slug(client)
    detail = launch_campaign(client, slug)
    assert detail["reference_place"] == 0
    assert variants(client, slug, detail["id"])["reference_index"] == 0


def test_reference_place_out_of_range_is_refused(client):
    slug = _slug(client)
    for place in (3, -1):
        response = post_launch(client, slug, kind="campaign", plan=campaign_plan([10, 20, 30]), title="Campagne", intent="Balayer", reference_place=place)
        assert response.status_code == 422
        assert response.json()["code"] == "reference_place_out_of_range"


def test_simple_study_has_no_reference_place(client):
    slug = _slug(client)
    detail = launch(client, slug, reference_place=0, comparison_reference={"experiment_id": "ailleurs"})
    assert detail["reference_place"] is None
    assert detail["comparison_reference"] is None


def test_fork_of_a_campaign_into_a_simple_study_drops_its_reference(client):
    slug = _slug(client)
    campaign = launch_campaign(client, slug, reference_place=None, comparison_reference={"experiment_id": "ailleurs"})
    forked = launch(client, slug, title="Suite", from_version={"experiment_id": campaign["id"]})
    assert forked["reference_place"] is None
    assert forked["comparison_reference"] is None


def test_evolving_a_campaign_into_a_process_drops_its_reference_keys(client):
    slug = _slug(client)
    campaign = launch_campaign(client, slug, reference_place=1)
    evolved = evolve(client, slug, campaign["id"], if_match=campaign["version_id"])
    assert evolved["is_batch"] is False
    assert evolved["reference_place"] is None


def test_combining_two_campaigns_keeps_the_reference_of_the_first(client):
    slug = _slug(client)
    first = launch_campaign(client, slug, title="Campagne 1", entities=[{"sample_id": "W1"}], reference_place=2)
    second = launch_campaign(client, slug, title="Campagne 2", entities=[{"sample_id": "W2"}], reference_place=None)
    combined = combine(client, slug, first["id"], second["id"], entities=[{"sample_id": "W9"}])
    assert combined["reference_place"] == 2
