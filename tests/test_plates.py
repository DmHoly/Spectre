"""Index des plaques (spectre.core.plates): finding a wafer by its lasermark from the topbar search,
and its own page - every study that follows it, across microprojects - kept up to date as studies
change, and limited to the microprojects the caller is a member of.
"""

from __future__ import annotations

from spectre.core.plates import compact


def _substrate():
    return {"material": "Si", "domain_width": {"value": 200, "unit": "nm"}, "thickness": {"value": 50, "unit": "nm"}}


def _steps(thickness=20):
    return [{"kind": "deposition", "name": "Oxyde", "material": "SiO2", "recipe": "CVD Conformal", "thickness": {"value": thickness, "unit": "nm"}}]


def _register(client, email):
    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={"email": email, "password": "supersecret", "name": "T"})


def _microproject(client, name):
    return client.post("/api/microprojets", json={"name": name}).json()["slug"]


def _launch(client, slug, entities, title):
    return client.post(
        f"/api/microprojets/{slug}/experiences",
        json={"substrate": _substrate(), "steps": _steps(), "title": title, "intent": "x", "entities": entities},
    ).json()


def test_lasermarks_compare_without_case_or_separators():
    assert compact(" w12-a3 ") == compact("W12 A3") == compact("W12_A3") == "W12A3"


def test_the_topbar_finds_a_plate_and_its_studies(client):
    _register(client, "plates@example.com")
    first = _microproject(client, "Lot A")
    second = _microproject(client, "Lot B")
    _launch(client, first, [{"sample_id": "W12-A3", "location": "boîte 1", "fdl": ["FDL-10"]}], "Dopage")
    _launch(client, second, [{"sample_id": "w12 a3", "location": "boîte 4", "fdl": ["FDL-22"]}], "Recuit")
    _launch(client, first, [{"sample_id": "W12-A30"}], "Autre plaque")

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
    _register(client, "plates-update@example.com")
    slug = _microproject(client, "Lot")
    launched = _launch(client, slug, [{"sample_id": "W1"}], "Essai")
    assert client.get("/api/plaques/recherche?q=W1").json()[0]["count"] == 1  # mis en cache

    # la plaque est renommée sur la fiche : l'index suit au prochain appel
    client.post(f"/api/microprojets/{slug}/experiences/{launched['id']}/entites", json={"entities": [{"sample_id": "W2", "fdl": ["FDL-5"]}]})
    assert client.get("/api/plaques/recherche?q=W1").json() == []
    assert client.get("/api/plaques/recherche?q=W2").json()[0]["sample_id"] == "W2"
    assert client.get("/api/microprojets/recherche-fdl?q=5").json()[0]["sample_id"] == "W2"


def test_a_campaign_lists_each_variant_plate(client):
    _register(client, "plates-campaign@example.com")
    slug = _microproject(client, "Lot")
    client.post(
        f"/api/microprojets/{slug}/experiences/campagne",
        json={
            "substrate": _substrate(),
            "steps": _steps(),
            "plan": {"factors": [{"step_index": 0, "field": "thickness", "values": [10, 30]}]},
            "title": "Split",
            "intent": "Epaisseur",
            "entities": [{"sample_id": "W-S1"}, {"sample_id": "W-S2"}],
        },
    )
    history = client.get("/api/plaques/W-S2").json()
    assert len(history["occurrences"]) == 1
    assert history["occurrences"][0]["entity_index"] == 1 and history["occurrences"][0]["variant"]


def test_plates_of_a_microproject_stay_with_its_members(client):
    _register(client, "owner-plates@example.com")
    slug = _microproject(client, "Secret")
    _launch(client, slug, [{"sample_id": "W-PRIV"}], "Confidentiel")
    _register(client, "stranger-plates@example.com")
    assert client.get("/api/plaques/recherche?q=W-PRIV").json() == []
    assert client.get("/api/plaques/W-PRIV").json()["occurrences"] == []
