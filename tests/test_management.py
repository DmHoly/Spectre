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
    assert by_key["activite"]["status"] == "live" and by_key["eqe"]["status"] == "demo"
    assert by_key["pl"]["status"] == "placeholder"
    assert [v["key"] for v in by_key["activite"]["variants"]] == ["running", "wafers"]

    live = client.get("/api/management/native-pt2/tendances/activite?mois=6").json()
    assert live["status"] == "live" and len(live["points"]) == 6 and len(live["periods"]) == 6
    assert live["variant"] == "running" and live["unit"] == "expériences"
    assert all(p["value"] == 0 for p in live["points"])

    placeholder = client.get("/api/management/native-pt2/tendances/pl").json()
    assert placeholder["status"] == "placeholder" and placeholder["points"] == [] and len(placeholder["periods"]) == 12

    assert client.get("/api/management/native-pt2/tendances/inconnu").status_code == 404
    assert client.get("/api/management/inconnu/tendances").status_code == 404


def test_month_periods_cross_the_year_boundary():
    from datetime import date

    from spectre.core.trends import month_periods

    assert month_periods(3, today=date(2027, 2, 10)) == ["2026-12", "2027-01", "2027-02"]


def test_objectives_record_a_bonus_percentage_and_the_microproject_that_validated_them(client):
    _register(client, "boss@example.com")
    nova = "/api/management/nova-pt1/objectifs"
    client.post(nova, json={"title": "Réduire le coût", "weight": 5})
    client.post(nova, json={"title": "Sans pourcentage"})
    area = client.post(nova, json={"title": "Qualifier le procédé", "weight": 60}).json()
    assert [(o["title"], o["weight"]) for o in area["objectifs"]] == [
        ("Qualifier le procédé", 60),
        ("Réduire le coût", 5),
        ("Sans pourcentage", None),
    ]
    assert "effort" not in area and "effort_total" not in area  # un simple chiffre, rien de calculé
    assert all(o["achieved"] is False and o["validated_by"] is None for o in area["objectifs"])

    microproject = client.post("/api/microprojets", json={"name": "Pilote procédé", "management_area_slug": "nova-pt1"}).json()
    objective_id = area["objectifs"][0]["id"]
    done = client.put(
        f"{nova}/{objective_id}",
        json={"title": "Qualifier le procédé", "weight": 60, "achieved": True, "validated_by": microproject["slug"]},
    ).json()
    first = done["objectifs"][0]
    assert first["achieved"] is True
    assert first["validated_by"] == {"slug": microproject["slug"], "code": "Nov_0001", "name": "Pilote procédé"}

    assert client.post(nova, json={"title": "Trop", "weight": 120}).status_code == 422
    assert client.post(nova, json={"title": "Zéro", "weight": 0}).status_code == 201
    assert client.post(nova, json={"title": "Fantôme", "validated_by": "inconnu"}).status_code == 422


def test_microprojets_get_an_auto_incremented_number_from_their_corporate_project(client):
    _register(client, "boss@example.com")

    def create(name, area=None):
        body = {"name": name, **({"management_area_slug": area} if area else {})}
        return client.post("/api/microprojets", json=body).json()

    nat1, nat2 = create("Dopage A", "native-pt2"), create("Dopage B", "native-pt2")
    nov1 = create("Pilote", "nova-pt1")
    loose = create("Pas encore classé")
    assert [nat1["code"], nat2["code"], nov1["code"], loose["code"]] == ["Nat_0001", "Nat_0002", "Nov_0001", None]

    # rattaché plus tard : numéroté à ce moment-là ; déplacé ensuite : garde son numéro
    client.post("/api/management/datacom-vlc/microprojets", json={"microproject_slug": loose["slug"]})
    client.post("/api/management/nova-pt1/microprojets", json={"microproject_slug": nat1["slug"]})
    codes = {p["slug"]: p["code"] for p in client.get("/api/microprojets/tous").json()}
    assert codes[loose["slug"]] == "VLC_0001" and codes[nat1["slug"]] == "Nat_0001"
    assert create("Dopage C", "native-pt2")["code"] == "Nat_0003"  # jamais de numéro réutilisé

    for typed in ("Nat_0002", "nat 2", "NAT2", "Nat-02"):
        found = client.get(f"/api/microprojets/code/{typed}")
        assert found.status_code == 200 and found.json()["slug"] == nat2["slug"], typed
    assert client.get("/api/microprojets/code/Nat_0099").status_code == 404
    redirect = client.get("/p/Nat_0002", follow_redirects=False)
    assert redirect.status_code == 302 and redirect.headers["location"] == f"/microprojets/{nat2['slug']}"

    area = client.post("/api/management", json={"name": "Fiabilité"}).json()
    assert area["code_prefix"] == "Fia"
    assert client.put(f"/api/management/{area['slug']}", json={"name": "Fiabilité", "code_prefix": "Nat"}).status_code == 422
    assert client.put(f"/api/management/{area['slug']}", json={"name": "Fiabilité", "code_prefix": "N4t"}).status_code == 422
    renamed = client.put("/api/management/native-pt2", json={"name": "Native (PT2)", "code_prefix": "Ntv"}).json()
    assert renamed["code_prefix"] == "Ntv"
    assert create("Dopage D", "native-pt2")["code"] == "Ntv_0001"
    assert client.get(f"/api/microprojets/{nat2['slug']}").json()["code"] == "Nat_0002"


def test_activity_trend_counts_experiments_in_progress_and_their_wafers(client):
    _register(client, "boss@example.com")
    microproject = client.post(
        "/api/microprojets", json={"name": "Suivi activite", "management_area_slug": "native-pt2"}
    ).json()
    substrate = {"material": "Si", "domain_width": {"value": 200, "unit": "nm"}, "thickness": {"value": 50, "unit": "nm"}}
    steps = [{"kind": "deposition", "name": "Oxyde", "material": "SiO2", "recipe": "CVD Conformal", "thickness": {"value": 20, "unit": "nm"}}]
    for title, wafers in (("Essai A", ["W1", "W2"]), ("Essai B", ["W3"])):
        response = client.post(
            f"/api/microprojets/{microproject['slug']}/experiences",
            json={"substrate": substrate, "steps": steps, "title": title, "intent": "x", "entities": [{"sample_id": w} for w in wafers]},
        )
        assert response.status_code == 201, response.text

    running = client.get("/api/management/native-pt2/tendances/activite?mois=3").json()
    assert [p["value"] for p in running["points"]][-1] == 2  # two studies in progress this month
    wafers = client.get("/api/management/native-pt2/tendances/activite?mois=3&variante=wafers").json()
    assert wafers["variant"] == "wafers" and wafers["unit"] == "wafers"
    assert [p["value"] for p in wafers["points"]][-1] == 3
    assert client.get("/api/management/native-pt2/tendances/activite?variante=inconnue").status_code == 404


def test_eqe_demo_trend_rises_and_opens_a_mock_study_fiche(client):
    _register(client, "boss@example.com")
    eqe = client.get("/api/management/native-pt2/tendances/eqe?mois=12").json()
    assert eqe["status"] == "demo" and "fictives" in eqe["message"]
    values = [p["value"] for p in eqe["points"]]
    assert values[-1] > values[0] + 4  # clearly rising
    studies = [p for p in eqe["points"] if p.get("study")]
    assert studies and all(p["label"] for p in studies)

    fiche = client.get(f"/api/management/native-pt2/tendances/eqe/etudes/{studies[-1]['study']}").json()
    assert fiche["demo"] is True
    assert "<svg" in fiche["structure_svg"] and "InGaN" in fiche["materials"]
    assert fiche["objective"]["target"] == 10.0 and fiche["conclusion"]["summary"]
    assert any(node["state"] == "current" for node in fiche["tree"]["nodes"]) and fiche["tree"]["edges"]

    assert client.get("/api/management/native-pt2/tendances/eqe/etudes/inconnue").status_code == 404
    assert client.get("/api/management/native-pt2/tendances/activite/etudes/eqe-ref").status_code == 404


def test_activity_counts_a_study_in_every_month_it_was_in_progress():
    from datetime import datetime, timezone
    from types import SimpleNamespace

    from spectre.core.trends import _running_intervals

    def version(day, status):
        return SimpleNamespace(created_at=datetime(2026, *day, tzinfo=timezone.utc), conclusion=SimpleNamespace(status=status))

    # lancée fin janvier, conclue début mars, rouverte en mai (évolution) et toujours en cours
    versions = [version((1, 28), "draft"), version((2, 10), "running"), version((3, 2), "concluded"), version((5, 5), "draft")]
    intervals = _running_intervals(versions)
    assert intervals == [(versions[0].created_at, versions[2].created_at), (versions[3].created_at, None)]


def test_topbar_search_finds_microprojets_by_number_or_name(client):
    _register(client, "boss@example.com")
    for name in ("Dopage PGaN", "Amélioration IQE", "Double EBL"):
        client.post("/api/microprojets", json={"name": name, "management_area_slug": "native-pt2"})

    def names(q):
        return [p["name"] for p in client.get(f"/api/microprojets/recherche?q={q}").json()]

    assert names("nat 2") == ["Amélioration IQE"]  # le numéro exact d'abord
    assert names("nat") == ["Dopage PGaN", "Amélioration IQE", "Double EBL"]  # Nat_0001, 0002, 0003
    assert names("amelio") == ["Amélioration IQE"]  # sans accent, début du nom
    assert names("ebl double") == ["Double EBL"]  # tous les mots, dans le désordre
    assert names("") == [] and names("introuvable") == []
    hit = client.get("/api/microprojets/recherche?q=Nat_0003").json()[0]
    assert hit["code"] == "Nat_0003" and hit["management_area"]["slug"] == "native-pt2"


def test_microprojet_payloads_name_their_owner(client):
    _register(client, "boss@example.com", name="Alice Martin")
    client.post("/api/microprojets", json={"name": "Recuit Mg", "management_area_slug": "native-pt2"})

    assert client.get("/api/microprojets/recuit-mg").json()["owners"] == [{"id": 1, "name": "Alice Martin"}]
    assert client.get("/api/microprojets").json()[0]["owners"][0]["name"] == "Alice Martin"
    row = client.get("/api/management/native-pt2").json()["microprojets"][0]
    assert row["owners"] == [{"id": 1, "name": "Alice Martin"}]


def _launch(client, slug, title):
    substrate = {"material": "Si", "domain_width": {"value": 200, "unit": "nm"}, "thickness": {"value": 50, "unit": "nm"}}
    steps = [{"kind": "deposition", "name": "Oxyde", "material": "SiO2", "recipe": "CVD Conformal", "thickness": {"value": 20, "unit": "nm"}}]
    return client.post(
        f"/api/microprojets/{slug}/experiences",
        json={"substrate": substrate, "steps": steps, "title": title, "intent": "Verifier", "entities": [{"sample_id": "W1"}]},
    ).json()


def test_thematique_page_lists_its_microprojets_on_a_frise(client):
    _register(client, "boss@example.com", name="Alice Martin")
    client.post("/api/management/native-pt2/thematiques", json={"name": "Dopage PGaN", "description": "Mg"})
    client.post("/api/management/native-pt2/thematiques", json={"name": "Double EBL"})
    client.post("/api/microprojets", json={"name": "Recuit Mg", "management_area_slug": "native-pt2", "thematique_slug": "dopage-pgan"})
    client.post("/api/microprojets", json={"name": "Ailleurs", "management_area_slug": "native-pt2", "thematique_slug": "double-ebl"})
    launched = _launch(client, "recuit-mg", "Recuit 700 C")

    page = client.get("/api/management/native-pt2/thematiques/dopage-pgan")
    assert page.status_code == 200
    body = page.json()
    assert body["name"] == "Dopage PGaN" and body["area"]["slug"] == "native-pt2"
    assert [p["slug"] for p in body["microprojets"]] == ["recuit-mg"]
    assert body["stats"]["microprojets"] == 1 and body["stats"]["experiences"] == 1
    row = body["microprojets"][0]
    assert row["owners"][0]["name"] == "Alice Martin" and row["created_at"].endswith("Z")
    assert [(n["id"], n["title"], n["status"], n["ended_at"]) for n in row["frise"]] == [(launched["id"], "Recuit 700 C", "draft", None)]
    assert {t["slug"]: t["microprojets"] for t in body["thematiques"]} == {"dopage-pgan": 1, "double-ebl": 1}

    # Someone outside the µprojet sees its counts and dates, not what its experiments are.
    _register(client, "hand@example.com")
    point = client.get("/api/management/native-pt2/thematiques/dopage-pgan").json()["microprojets"][0]["frise"][0]
    assert "title" not in point and "id" not in point and point["status"] == "draft"

    assert client.get("/api/management/native-pt2/thematiques/inconnue").status_code == 404
    assert client.get("/management/native-pt2/thematiques/dopage-pgan").status_code == 200  # the page itself
