"""Partir de plaques existantes (POST /experiments avec ``wafer_origin``) : une nouvelle étude dont
les plaques (``entities``) viennent d'une étude qui les suit - sa structure est la leur. Dans le même
µprojet, la nouvelle piste descend de cette version ; d'un autre µprojet, l'origine est seulement
notée. Plusieurs plaques sont des réplicats : elles partagent une même structure (une étude simple
en suit autant qu'on veut, une campagne une par variante, et deux variantes ne partent pas
ensemble)."""

from __future__ import annotations

from support.accounts import login, signup
from support.experiments import (
    evolve_image,
    experiment_url,
    from_wafers,
    get_experiment,
    get_process,
    launch,
    launch_campaign,
    launch_image,
    post_from_wafers,
    post_launch,
    process,
    step_ids,
    track_entities,
)
from support.microprojects import create_microproject, signup_with_microproject
from support.structures import deposition, steps, upload_structure_image
from support.wafers import get_wafer


def _replicates(client, slug, **fields):
    return launch(
        client, slug, title="Épitaxie", intent="Faire croître", entities=[{"sample_id": "W1", "location": "boîte 1"}, {"sample_id": "W2"}],
        objectives=[{"name": "EQE", "metric": "max_EQE"}], context="Run 40", **fields,
    )


# -- les réplicats d'une étude simple -------------------------------------------------------------


def test_a_simple_study_tracks_replicates(client):
    slug = signup_with_microproject(client, "replicates@example.com", "Réplicats")
    study = _replicates(client, slug)
    assert [e["sample_id"] for e in study["physical_tracking"]] == ["W1", "W2"]

    # au lancement, une ligne vide est une place à associer plus tard ; la même plaque deux fois est refusée
    blank = launch(client, slug, title="Autre", entities=[{"sample_id": "W3"}, {"sample_id": ""}])
    assert blank["physical_tracking"] == [{"sample_id": "W3", "location": None}, {"sample_id": None, "location": None}]
    twice = post_launch(client, slug, title="Doublon", entities=[{"sample_id": "W4"}, {"sample_id": "w-4"}])
    assert twice.status_code == 422 and twice.json()["code"] == "duplicate_wafer"

    # la carte « Plaques » en ajoute, en vide une : chaque place vide garde sa position, à associer
    updated = track_entities(client, slug, study["id"], [{"sample_id": "W1"}, {"sample_id": None}, {"sample_id": "W5"}, {"sample_id": None}])
    assert [e["sample_id"] for e in updated["physical_tracking"]] == ["W1", None, "W5", None]
    duplicate = client.put(f"{experiment_url(slug, study['id'])}/entities", json={"entities": [{"sample_id": "W1"}, {"sample_id": "W1"}]})
    assert duplicate.status_code == 422 and duplicate.json()["code"] == "duplicate_wafer"
    empty = client.put(f"{experiment_url(slug, study['id'])}/entities", json={"entities": []})
    assert empty.status_code == 422 and empty.json()["code"] == "entity_count"


def test_a_campaign_still_tracks_one_wafer_per_variant(client):
    slug = signup_with_microproject(client, "replicates-campaign@example.com", "Campagnes")
    too_many = post_launch(
        client, slug, kind="campaign", title="Campagne", intent="Balayer",
        plan={"factors": [{"step_id": "st_00000001", "field": "thickness", "values": [10, 20]}]},
        entities=[{"sample_id": "A"}, {"sample_id": "B"}, {"sample_id": "C"}],
    )
    assert too_many.status_code == 422 and too_many.json()["code"] == "too_many_entities"
    campaign = launch_campaign(client, slug, entities=[{"sample_id": "A"}])
    assert [e["sample_id"] for e in campaign["physical_tracking"]] == ["A", None, None]
    wrong = client.put(f"{experiment_url(slug, campaign['id'])}/entities", json={"entities": [{"sample_id": "A"}, {"sample_id": "B"}]})
    assert wrong.status_code == 422 and wrong.json()["code"] == "entity_count"


def test_pictures_keep_their_replicates_when_they_evolve(client):
    slug = signup_with_microproject(client, "replicates-images@example.com", "Images")
    image_id = upload_structure_image(client, slug)
    study = launch_image(client, slug, [{"image_id": image_id}], entities=[{"sample_id": "W1"}, {"sample_id": "W2"}])
    assert [e["sample_id"] for e in study["physical_tracking"]] == ["W1", "W2"]
    evolved = evolve_image(client, slug, study["id"], [{"image_id": image_id, "caption": "Coupe TEM"}])
    assert [e["sample_id"] for e in evolved["physical_tracking"]] == ["W1", "W2"]


# -- partir de plaques, dans le même µprojet ------------------------------------------------------


def test_starting_from_wafers_of_the_same_microproject_descends_from_their_study(client):
    slug = signup_with_microproject(client, "wafers-start@example.com", "Départ")
    origin = _replicates(client, slug, reference_origin={"reference": "oxyde", "version": "1.1"})
    origin_ids = step_ids(client, slug, origin["id"])
    # la structure des plaques, et une étape de plus
    more = [{"id": origin_ids[0], **deposition(thickness_nm=20)}, deposition("Nitrure", "Si3N4", thickness_nm=5)]
    started = from_wafers(client, slug, slug, origin["id"], [{"sample_id": "w1", "location": "boîte 7"}, "W2"], steps=more)

    assert started["parents"] == [origin["version_id"]]  # la filiation : graphe, diff, évolution
    assert started["wafer_origin"] == {"microproject": slug, "experiment_id": origin["id"], "version_id": origin["version_id"], "variant": None}
    assert started["physical_tracking"] == [{"sample_id": "w1", "location": "boîte 7"}, {"sample_id": "W2", "location": None}]
    # une nouvelle étude : ni les objectifs ni le contexte de l'étude des plaques ; sa référence, si
    assert started["objectives"] == [] and started["context"] is None
    assert started["reference_origin"] == {"reference": "oxyde", "version": "1.1"}
    new_ids = step_ids(client, slug, started["id"])
    assert new_ids[0] == origin_ids[0] and len(new_ids) == 2  # l'étape reprise garde son id
    # l'étude des plaques ne bouge pas
    assert get_experiment(client, slug, origin["id"])["version_id"] == origin["version_id"]


def test_starting_from_wafers_checks_them_against_their_study(client):
    slug = signup_with_microproject(client, "wafers-check@example.com", "Contrôles")
    origin = _replicates(client, slug)
    stranger = post_from_wafers(client, slug, slug, origin["id"], ["W1", "W9"])
    assert stranger.status_code == 422 and stranger.json()["code"] == "wafer_not_in_origin"
    none = post_from_wafers(client, slug, slug, origin["id"], [])
    assert none.status_code == 422 and none.json()["code"] == "entity_required"
    twice = post_from_wafers(client, slug, slug, origin["id"], ["W1", "w1"])
    assert twice.status_code == 422 and twice.json()["code"] == "duplicate_wafer"
    unknown = post_from_wafers(client, slug, slug, "inconnue", ["W1"])
    assert unknown.status_code == 404 and unknown.json()["code"] == "source_not_found"
    both = client.post(
        f"/api/microprojects/{slug}/experiments",
        json={
            "title": "x", "intent": "y", "entities": [{"sample_id": "W1"}],
            "structure": {"kind": "process", "substrate": process(client, slug, origin["id"])["substrate"], "steps": steps()},
            "wafer_origin": {"microproject": slug, "experiment_id": origin["id"]},
            "from_version": {"experiment_id": origin["id"]},
        },
    )
    assert both.status_code == 422
    # une version passée de l'étude : ses plaques d'alors
    track_entities(client, slug, origin["id"], [{"sample_id": "W3"}])
    assert post_from_wafers(client, slug, slug, origin["id"], ["W1"]).status_code == 422
    past = from_wafers(client, slug, slug, origin["id"], ["W1"], version_id=origin["version_id"])
    assert past["parents"] == [origin["version_id"]]


def test_starting_from_a_campaign_wafer_takes_its_variant(client):
    slug = signup_with_microproject(client, "wafers-campaign@example.com", "Campagne")
    campaign = launch_campaign(client, slug, entities=[{"sample_id": "A"}, {"sample_id": "B"}, {"sample_id": "C"}])

    variant = process(client, slug, campaign["id"], variant=1)  # 10, 20, 30 nm : la deuxième
    assert variant["steps"][0]["thickness"]["value"] == 20 and variant["steps"][0]["id"] == step_ids(client, slug, campaign["id"])[0]
    assert get_process(client, slug, campaign["id"], variant=3).json()["code"] == "unknown_variant"

    started = from_wafers(client, slug, slug, campaign["id"], ["B"], steps=[{**variant["steps"][0]}])
    assert started["wafer_origin"]["variant"] == 1 and started["parents"] == [campaign["version_id"]]
    assert not started["is_batch"]

    apart = post_from_wafers(client, slug, slug, campaign["id"], ["A", "B"])
    assert apart.status_code == 422 and apart.json()["code"] == "wafers_different_structures"

    simple = launch(client, slug, title="Simple")
    assert get_process(client, slug, simple["id"], variant=0).json()["code"] == "not_a_campaign"


# -- partir de plaques d'un autre µprojet ----------------------------------------------------------


def test_starting_from_wafers_of_another_microproject_records_their_origin(client):
    signup(client, "wafers-cross@example.com")
    epi = create_microproject(client, "Épitaxie")["slug"]
    proc = create_microproject(client, "Procédé")["slug"]
    origin = _replicates(client, epi)
    origin_ids = step_ids(client, epi, origin["id"])

    started = from_wafers(client, proc, epi, origin["id"], ["W2"], steps=[{"id": origin_ids[0], **deposition()}])
    assert started["parents"] == []  # pas de filiation d'un dépôt à l'autre
    assert started["wafer_origin"] == {"microproject": epi, "experiment_id": origin["id"], "version_id": origin["version_id"], "variant": None}
    assert step_ids(client, proc, started["id"]) == origin_ids  # les ids d'étape suivent la structure

    # le passeport de la plaque montre les deux études ; la plus récente d'abord
    passport = get_wafer(client, "W2")
    assert [o["experiment"]["microproject"]["slug"] for o in passport["occurrences"]] == [proc, epi]


def test_starting_from_wafers_of_a_microproject_one_cannot_read_is_refused(client):
    signup(client, "admin-wafers@example.com")  # le premier compte est admin
    private = signup_with_microproject(client, "owner-private@example.com", "Privé")
    origin = launch(client, private, title="Privée", entities=[{"sample_id": "W1"}])
    mine = signup_with_microproject(client, "other-owner@example.com", "Le mien")

    refused = post_from_wafers(client, mine, private, origin["id"], ["W1"])
    assert refused.status_code == 403
    missing = post_from_wafers(client, mine, "inconnu", origin["id"], ["W1"])
    assert missing.status_code == 404
    login(client, "owner-private@example.com")
    assert post_from_wafers(client, private, private, origin["id"], ["W1"]).status_code == 201


# -- l'index des plaques dit d'où partir ------------------------------------------------------------


def test_a_wafer_occurrence_names_its_version_and_when_it_entered(client):
    slug = signup_with_microproject(client, "wafers-index@example.com", "Index")
    origin = launch(client, slug, title="Première", entities=[{"sample_id": "W1"}])
    later = track_entities(client, slug, origin["id"], [{"sample_id": "W1", "location": "boîte 2"}])
    campaign = launch_campaign(client, slug, entities=[{"sample_id": "W1"}])

    occurrences = {o["experiment"]["id"]: o for o in get_wafer(client, "W1")["occurrences"]}
    first = occurrences[origin["id"]]["experiment"]
    assert first["version_id"] == later["version_id"]  # la version qui la suit aujourd'hui
    assert first["tracked_since"] == origin["created_at"] and first["updated_at"] == later["created_at"]
    assert first["campaign"] is False and occurrences[campaign["id"]]["experiment"]["campaign"] is True

    # hors du µprojet : ni version, ni titre ; la date d'entrée, oui
    signup(client, "outsider-index@example.com")
    outsider = get_wafer(client, "W1")["occurrences"][0]["experiment"]
    assert "version_id" not in outsider and "campaign" not in outsider and outsider["tracked_since"]
