"""Index des plaques (spectre.plugins.wafers.service): finding a wafer by its lasermark from the topbar search,
and its own page - every study that follows it, across microprojects - kept up to date as studies
change, and limited to the microprojects the caller is a member of.
"""

from __future__ import annotations

from spectre.plugins.experiments.entities import compact

from support.accounts import signup
from support.experiments import launch, launch_campaign, track_entities
from support.microprojects import create_microproject
from support.structures import campaign_plan


def test_lasermarks_compare_without_case_or_separators():
    assert compact(" w12-a3 ") == compact("W12 A3") == compact("W12_A3") == "W12A3"


def test_the_topbar_finds_a_plate_and_its_studies(client):
    signup(client, "plates@example.com")
    first = create_microproject(client, "Lot A")["slug"]
    second = create_microproject(client, "Lot B")["slug"]
    launch(client, first, title="Dopage", intent="x", entities=[{"sample_id": "W12-A3", "location": "boîte 1", "fdl": ["FDL-10"]}])
    launch(client, second, title="Recuit", intent="x", entities=[{"sample_id": "w12 a3", "location": "boîte 4", "fdl": ["FDL-22"]}])
    launch(client, first, title="Autre plaque", intent="x", entities=[{"sample_id": "W12-A30"}])

    def search(q):
        return client.get(f"/api/plaques/recherche?q={q}").json()

    hits = search("w12a3")
    assert [(h["sample_id"].upper().replace(" ", "-"), h["count"]) for h in hits] == [("W12-A3", 2), ("W12-A30", 1)]
    assert hits[0]["latest"]["title"] == "Recuit"  # la plus récente d'abord
    assert search("A3") and search("x") == []  # 2 caractères minimum

    history = client.get("/api/plaques/W12-A3").json()
    assert [o["experience"]["title"] for o in history["occurrences"]] == ["Recuit", "Dopage"]
    assert history["fdl"] == ["FDL-22", "FDL-10"] and history["last_location"] == "boîte 4"
    assert {m["slug"] for m in history["microprojects"]} == {first, second}
    assert client.get("/api/plaques/inconnue").json()["occurrences"] == []


def test_the_index_follows_new_versions(client):
    signup(client, "plates-update@example.com")
    slug = create_microproject(client, "Lot")["slug"]
    launched = launch(client, slug, title="Essai", intent="x", entities=[{"sample_id": "W1"}])
    assert client.get("/api/plaques/recherche?q=W1").json()[0]["count"] == 1  # mis en cache

    # la plaque est renommée sur la fiche : l'index suit au prochain appel
    track_entities(client, slug, launched["id"], [{"sample_id": "W2", "fdl": ["FDL-5"]}])
    assert client.get("/api/plaques/recherche?q=W1").json() == []
    assert client.get("/api/plaques/recherche?q=W2").json()[0]["sample_id"] == "W2"
    assert client.get("/api/microprojets/recherche-fdl?q=5").json()[0]["sample_id"] == "W2"


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
    history = client.get("/api/plaques/W-S2").json()
    assert len(history["occurrences"]) == 1
    assert history["occurrences"][0]["entity_index"] == 1 and history["occurrences"][0]["variant"]


def test_plates_of_a_microproject_stay_with_its_members(client):
    signup(client, "owner-plates@example.com")
    slug = create_microproject(client, "Secret")["slug"]
    launch(client, slug, title="Confidentiel", intent="x", entities=[{"sample_id": "W-PRIV"}])
    signup(client, "stranger-plates@example.com")
    assert client.get("/api/plaques/recherche?q=W-PRIV").json() == []
    assert client.get("/api/plaques/W-PRIV").json()["occurrences"] == []
