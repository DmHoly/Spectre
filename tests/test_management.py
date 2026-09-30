from __future__ import annotations


def _register(client, email, name="T"):
    client.post("/api/auth/register", json={"email": email, "password": "supersecret", "name": name})


def test_first_account_is_admin_and_others_are_not(client):
    _register(client, "boss@example.com")
    assert client.get("/api/auth/me").json()["is_admin"] is True
    _register(client, "hand@example.com")
    assert client.get("/api/auth/me").json()["is_admin"] is False


def test_new_microprojet_lands_in_the_unclassified_area(client):
    _register(client, "boss@example.com")
    client.post("/api/microprojets", json={"name": "Contact ohmique"})

    listing = client.get("/api/management").json()
    slugs = {a["slug"] for a in listing["areas"]}
    assert "non-classe" in slugs and {"datacom-vlc", "nova-pt1", "native-pt2"} <= slugs  # 3 thèmes phares seedés
    unclassified = next(a for a in listing["areas"] if a["slug"] == "non-classe")
    assert unclassified["stats"]["microprojets"] == 1
    assert listing["totals"]["microprojets"] == 1


def test_flagship_themes_are_seeded_on_a_fresh_instance(client):
    _register(client, "boss@example.com")
    names = {a["name"] for a in client.get("/api/management").json()["areas"]}
    assert {"VLC (microlink)", "Nova (PT1)", "Native (PT2)"} <= names


def test_admin_creates_an_area_and_moves_a_microprojet_into_it(client):
    _register(client, "boss@example.com")
    client.post("/api/microprojets", json={"name": "Contact ohmique"})

    created = client.post("/api/management", json={"name": "Fiabilité", "strategy": "Réduire les retours"})
    assert created.status_code == 201
    slug = created.json()["slug"]
    assert slug == "fiabilite"

    moved = client.post(f"/api/management/{slug}/microprojets", json={"microproject_slug": "contact-ohmique"})
    assert moved.status_code == 200
    assert [p["slug"] for p in moved.json()["microprojets"]] == ["contact-ohmique"]

    unclassified = next(a for a in client.get("/api/management").json()["areas"] if a["slug"] == "non-classe")
    assert unclassified["stats"]["microprojets"] == 0


def test_non_admin_reads_but_cannot_write_the_strategy_layer(client):
    _register(client, "boss@example.com")
    client.post("/api/management", json={"name": "Thème A"})
    _register(client, "hand@example.com")

    assert client.get("/api/management").status_code == 200
    assert client.post("/api/management", json={"name": "Thème B"}).status_code == 403
    assert client.put("/api/management/theme-a", json={"name": "x", "description": "", "strategy": ""}).status_code == 403
    assert client.delete("/api/management/theme-a").status_code == 403


def test_deleting_an_area_returns_its_microprojets_to_unclassified(client):
    _register(client, "boss@example.com")
    client.post("/api/microprojets", json={"name": "P1"})
    slug = client.post("/api/management", json={"name": "Temporaire"}).json()["slug"]
    client.post(f"/api/management/{slug}/microprojets", json={"microproject_slug": "p1"})

    assert client.delete(f"/api/management/{slug}").status_code == 200
    unclassified = next(a for a in client.get("/api/management").json()["areas"] if a["slug"] == "non-classe")
    assert unclassified["stats"]["microprojets"] == 1


def test_unclassified_area_cannot_be_deleted(client):
    _register(client, "boss@example.com")
    assert client.delete("/api/management/non-classe").status_code == 422


def test_creating_a_microprojet_directly_in_a_theme(client):
    _register(client, "boss@example.com")
    slug = client.post("/api/management", json={"name": "Contacts"}).json()["slug"]

    created = client.post("/api/microprojets", json={"name": "PGaN", "management_area_slug": slug})
    assert created.status_code == 201
    assert created.json()["management_area"]["slug"] == slug
    assert client.get("/api/microprojets/pgan").json()["management_area"]["name"] == "Contacts"

    bad = client.post("/api/microprojets", json={"name": "X", "management_area_slug": "inexistant"})
    assert bad.status_code == 404


def test_list_all_microprojets_is_admin_only(client):
    _register(client, "boss@example.com")
    client.post("/api/microprojets", json={"name": "A"})
    assert [p["slug"] for p in client.get("/api/microprojets/tous").json()] == ["a"]

    _register(client, "hand@example.com")
    assert client.get("/api/microprojets/tous").status_code == 403


def test_thematiques_group_microprojets_inside_a_corporate_project(client):
    _register(client, "boss@example.com")
    area = client.post("/api/management/native-pt2/thematiques", json={"name": "Dopage PGaN"})
    assert area.status_code == 201
    client.post("/api/management/native-pt2/thematiques", json={"name": "Double EBL"})
    assert [t["slug"] for t in area.json()["thematiques"]] == ["dopage-pgan"]

    created = client.post(
        "/api/microprojets",
        json={"name": "Recuit Mg", "management_area_slug": "native-pt2", "thematique_slug": "dopage-pgan"},
    )
    assert created.status_code == 201
    assert created.json()["thematique"] == {"slug": "dopage-pgan", "name": "Dopage PGaN"}

    client.post("/api/microprojets", json={"name": "Orphelin"})
    moved = client.post(
        "/api/management/native-pt2/microprojets", json={"microproject_slug": "orphelin", "thematique_slug": "double-ebl"}
    ).json()
    by_slug = {p["slug"]: p["thematique_slug"] for p in moved["microprojets"]}
    assert by_slug == {"recuit-mg": "dopage-pgan", "orphelin": "double-ebl"}
    stats = {t["slug"]: t["stats"]["microprojets"] for t in moved["thematiques"]}
    assert stats == {"dopage-pgan": 1, "double-ebl": 1}

    # A thématique of another project is rejected.
    bad = client.post("/api/microprojets", json={"name": "X", "management_area_slug": "nova-pt1", "thematique_slug": "dopage-pgan"})
    assert bad.status_code == 404

    # Deleting a thématique keeps its µprojets in the project, without thématique.
    after = client.delete("/api/management/native-pt2/thematiques/dopage-pgan").json()
    assert {p["slug"]: p["thematique_slug"] for p in after["microprojets"]}["recuit-mg"] is None


def test_corporate_objectives_are_ranked_and_editable(client):
    _register(client, "boss@example.com")
    base = "/api/management/nova-pt1/objectifs"
    client.post(base, json={"title": "Qualifier le procédé", "target": "T1 2027"})
    client.post(base, json={"title": "Transférer en prod"})
    area = client.post(base, json={"title": "Réduire le coût"}).json()
    ids = [o["id"] for o in area["objectifs"]]
    assert [o["title"] for o in area["objectifs"]] == ["Qualifier le procédé", "Transférer en prod", "Réduire le coût"]
    assert area["objectives_period"] == "6 prochains mois"

    reordered = client.put(base, json={"ids": [ids[2], ids[0], ids[1]]}).json()
    assert [o["title"] for o in reordered["objectifs"]] == ["Réduire le coût", "Qualifier le procédé", "Transférer en prod"]
    assert client.put(base, json={"ids": ids[:2]}).status_code == 422

    edited = client.put(f"{base}/{ids[1]}", json={"title": "Transférer en production", "detail": "Ligne 200 mm"}).json()
    assert edited["objectifs"][2]["title"] == "Transférer en production"
    assert client.delete(f"{base}/{ids[0]}").json()["objectifs"][0]["title"] == "Réduire le coût"

    renamed = client.put(
        "/api/management/nova-pt1", json={"name": "Nova (PT1)", "objectives_period": "S1 2027"}
    ).json()
    assert renamed["objectives_period"] == "S1 2027"

    _register(client, "hand@example.com")
    assert client.get("/api/management/nova-pt1").json()["objectifs"]
    assert client.post(base, json={"title": "x"}).status_code == 403
    assert client.post("/api/management/nova-pt1/thematiques", json={"name": "x"}).status_code == 403


def test_trend_kpis_are_listed_and_served_lazily(client):
    _register(client, "boss@example.com")
    kpis = client.get("/api/management/native-pt2/tendances").json()["kpis"]
    by_key = {k["key"]: k for k in kpis}
    assert by_key["activite"]["status"] == "live" and by_key["eqe"]["status"] == "placeholder"

    live = client.get("/api/management/native-pt2/tendances/activite?mois=6").json()
    assert live["status"] == "live" and len(live["points"]) == 6 and len(live["periods"]) == 6
    assert all(p["value"] == 0 for p in live["points"])

    placeholder = client.get("/api/management/native-pt2/tendances/eqe").json()
    assert placeholder["status"] == "placeholder" and placeholder["points"] == [] and len(placeholder["periods"]) == 12

    assert client.get("/api/management/native-pt2/tendances/inconnu").status_code == 404
    assert client.get("/api/management/inconnu/tendances").status_code == 404


def test_month_periods_cross_the_year_boundary():
    from datetime import date

    from spectre.core.trends import month_periods

    assert month_periods(3, today=date(2027, 2, 10)) == ["2026-12", "2027-01", "2027-02"]
