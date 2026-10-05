"""Index des plaques (spectre.plugins.wafers.service): finding a wafer by its lasermark or its FDL,
the wafers already noted in a µprojet, and a wafer's own page - every study that follows it, across
microprojects - kept up to date as studies change, and seen through one visibility rule: everything
for the members of a study's µprojet, its µprojet, status and dates only for the others.
"""

from __future__ import annotations

from spectre.plugins.experiments.entities import compact

from support.accounts import signup
from support.experiments import launch, launch_campaign, track_entities
from support.http import assert_handler_404
from support.microprojects import create_microproject, signup_with_microproject
from support.structures import campaign_plan
from support.wafers import get_wafer, list_wafers


def test_lasermarks_compare_without_case_or_separators():
    assert compact(" w12-a3 ") == compact("W12 A3") == compact("W12_A3") == "W12A3"


def test_wafers_are_found_by_lasermark_and_have_a_passport(client):
    signup(client, "plates@example.com")
    first = create_microproject(client, "Lot A")["slug"]
    second = create_microproject(client, "Lot B")["slug"]
    launch(client, first, title="Dopage", intent="x", entities=[{"sample_id": "W12-A3", "location": "boîte 1", "fdl": ["FDL-10"]}])
    recuit = launch(client, second, title="Recuit", intent="x", entities=[{"sample_id": "w12 a3", "location": "boîte 4", "fdl": ["FDL-22"]}])
    launch(client, first, title="Autre plaque", intent="x", entities=[{"sample_id": "W12-A30"}])

    hits = list_wafers(client, q="w12a3")
    assert [(h["key"], h["count"]) for h in hits] == [("W12A3", 2), ("W12A30", 1)]  # exact first
    assert hits[0]["lasermark"] == "w12 a3" and hits[0]["latest"]["experiment"]["title"] == "Recuit"  # la plus récente d'abord
    assert hits[0]["fdl"] == ["FDL-22", "FDL-10"] and hits[0]["locations"] == ["boîte 4", "boîte 1"]
    assert [h["key"] for h in list_wafers(client, q="A3")] == ["W12A3", "W12A30"]  # contained
    assert list_wafers(client, q="zz") == []

    passport = get_wafer(client, "W12-A3")
    assert passport["key"] == "W12A3" and get_wafer(client, "W12A3") == passport  # by its key or as written
    assert [o["experiment"]["title"] for o in passport["occurrences"]] == ["Recuit", "Dopage"]
    assert passport["occurrences"][0]["experiment"]["id"] == recuit["id"] and passport["occurrences"][0]["location"] == "boîte 4"
    assert passport["fdl"] == ["FDL-22", "FDL-10"] and passport["last_location"] == "boîte 4"
    assert {m["slug"] for m in passport["microprojects"]} == {first, second}
    assert "lots" not in passport  # the lots of a wafer: GET /api/lots?wafer=
    unknown = get_wafer(client, "inconnue")
    assert unknown["occurrences"] == [] and unknown["lasermark"] == "inconnue"


def test_wafers_are_found_by_fdl(client):
    slug = signup_with_microproject(client, "fdl-wafers@example.com", "Lots")
    launch(client, slug, title="Dopage", intent="x", entities=[{"sample_id": "W7", "fdl": ["FDL-1201", "FDL-1350"]}])
    launch(client, slug, title="Autre", intent="x", entities=[{"sample_id": "W9", "fdl": ["FDL-12010"]}])
    assert [w["key"] for w in list_wafers(client, fdl="1201")] == ["W7", "W9"]  # the exact number first
    assert [w["key"] for w in list_wafers(client, fdl="fdl 1350")] == ["W7"]
    assert list_wafers(client, fdl="dopage") == []  # an FDL is a number
    assert [w["key"] for w in list_wafers(client, fdl="1201", q="W9")] == ["W9"]  # filters add up


def test_the_index_follows_new_versions(client):
    signup(client, "plates-update@example.com")
    slug = create_microproject(client, "Lot")["slug"]
    launched = launch(client, slug, title="Essai", intent="x", entities=[{"sample_id": "W1"}])
    assert list_wafers(client, q="W1")[0]["count"] == 1  # mis en cache

    # la plaque est renommée sur la fiche : l'index suit au prochain appel
    track_entities(client, slug, launched["id"], [{"sample_id": "W2", "fdl": ["FDL-5"]}])
    assert list_wafers(client, q="W1") == []
    assert list_wafers(client, q="W2")[0]["lasermark"] == "W2"
    assert list_wafers(client, fdl="5")[0]["lasermark"] == "W2"


def test_a_campaign_lists_each_variant_plate(client):
    signup(client, "plates-campaign@example.com")
    slug = create_microproject(client, "Lot")["slug"]
    launch_campaign(
        client,
        slug,
        campaign_plan([10, 30]),
        title="Split",
        intent="Epaisseur",
        entities=[{"sample_id": "W-S1"}, {"sample_id": "W-S2"}],
    )
    passport = get_wafer(client, "W-S2")
    assert len(passport["occurrences"]) == 1
    assert passport["occurrences"][0]["entity_index"] == 1 and passport["occurrences"][0]["variant"]


def test_the_wafers_of_a_microproject_feed_the_autocomplete(client):
    slug = signup_with_microproject(client, "hist@example.com", name="Owner")
    assert list_wafers(client, microproject=slug) == []

    launch(client, slug, title="A", intent="x", entities=[{"sample_id": "W1-A1", "location": "congélateur B"}])
    second = launch(client, slug, title="B", intent="x", entities=[{"sample_id": "W1-A2", "location": "congélateur B"}])
    # a repeated value (même emplacement) reste unique
    track_entities(client, slug, second["id"], [{"sample_id": "W1-A2", "location": "congélateur B", "fdl": ["FDL-3"]}])
    other = create_microproject(client, "Ailleurs")["slug"]
    launch(client, other, title="C", intent="x", entities=[{"sample_id": "W-ELSEWHERE"}])

    wafers = list_wafers(client, microproject=slug)
    assert sorted(w["lasermark"] for w in wafers) == ["W1-A1", "W1-A2"]
    assert {w["key"]: (w["locations"], w["fdl"]) for w in wafers} == {"W1A1": (["congélateur B"], []), "W1A2": (["congélateur B"], ["FDL-3"])}
    assert_handler_404(client.get("/api/wafers", params={"microproject": "inconnu"}))


def test_a_study_shows_what_it_is_to_its_microprojects_members_only(client):
    signup(client, "owner-plates@example.com")
    slug = create_microproject(client, "Secret")["slug"]
    launch(client, slug, title="Confidentiel", intent="x", entities=[{"sample_id": "W-PRIV", "location": "armoire", "fdl": ["FDL-77"]}])
    signup(client, "stranger-plates@example.com")

    (occurrence,) = get_wafer(client, "W-PRIV")["occurrences"]
    assert occurrence == {
        "lasermark": "W-PRIV",
        "entity_index": 0,
        "experiment": {
            "microproject": {"slug": slug, "code": occurrence["experiment"]["microproject"]["code"], "name": "Secret"},
            "member": False,
            "status": "draft",
            "updated_at": occurrence["experiment"]["updated_at"],
            "tracked_since": occurrence["experiment"]["tracked_since"],  # des dates, pas de version ni de titre
        },
    }
    passport = get_wafer(client, "W-PRIV")
    assert passport["fdl"] == [] and passport["last_location"] is None
    (found,) = list_wafers(client, q="W-PRIV")
    assert found["fdl"] == [] and found["locations"] == [] and "title" not in found["latest"]["experiment"]
    assert list_wafers(client, fdl="77") == []  # an FDL is only read by the members
    refused = client.get("/api/wafers", params={"microproject": slug})
    assert refused.status_code == 403
