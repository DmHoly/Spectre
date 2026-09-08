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
    assert {"Datacom (VLC)", "Nova (PT1)", "Native (PT2)"} <= names


def test_admin_creates_an_area_and_moves_a_microprojet_into_it(client):
    _register(client, "boss@example.com")
    client.post("/api/microprojets", json={"name": "Contact ohmique"})

    created = client.post("/api/management", json={"name": "Fiabilité", "strategy": "Réduire les retours"})
    assert created.status_code == 201
    slug = created.json()["slug"]
    assert slug == "fiabilite"

    moved = client.post(f"/api/management/{slug}/microprojets", json={"project_slug": "contact-ohmique"})
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
    client.post(f"/api/management/{slug}/microprojets", json={"project_slug": "p1"})

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
