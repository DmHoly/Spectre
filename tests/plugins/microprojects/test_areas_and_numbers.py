"""Un µprojet dans la couche stratégique : son projet corporate et sa thématique (à la création, puis
par PATCH /api/microprojects/{microproject_slug}), son numéro, la recherche par numéro ou par nom."""

from __future__ import annotations

from support.accounts import login, signup
from support.areas import create_area, create_thematic
from support.experiments import experiment_stats
from support.http import assert_handler_404
from support.microprojects import create_microproject, join_as, move_microproject


def test_creating_a_microprojet_directly_in_a_theme(client):
    signup(client, "boss@example.com")
    slug = create_area(client, "Contacts")["slug"]

    created = client.post("/api/microprojets", json={"name": "PGaN", "management_area_slug": slug})
    assert created.status_code == 201
    assert created.json()["management_area"]["slug"] == slug
    assert client.get("/api/microprojets/pgan").json()["management_area"]["name"] == "Contacts"

    bad = client.post("/api/microprojets", json={"name": "X", "management_area_slug": "inexistant"})
    assert_handler_404(bad)


def test_list_all_microprojets_is_admin_only(client):
    signup(client, "boss@example.com")
    create_microproject(client, "A")
    assert [p["slug"] for p in client.get("/api/microprojets/tous").json()] == ["a"]

    signup(client, "hand@example.com")
    assert client.get("/api/microprojets/tous").status_code == 403


def test_an_owner_renames_and_moves_a_microprojet(client):
    signup(client, "boss@example.com")  # admin
    create_thematic(client, "native-pt2", "Dopage PGaN")
    create_thematic(client, "nova-pt1", "Pilote")
    signup(client, "owner@example.com")
    create_microproject(client, "Recuit", description="Avant")

    patched = client.patch("/api/microprojects/recuit", json={"name": "Recuit Mg", "description": "Après"})
    assert patched.status_code == 200
    body = patched.json()
    assert (body["slug"], body["name"], body["description"], body["role"]) == ("recuit", "Recuit Mg", "Après", "owner")
    assert body["management_area"]["slug"] == "non-classe"  # un PATCH ne touche que les champs envoyés

    moved = client.patch("/api/microprojects/recuit", json={"area": "native-pt2", "thematic": "dopage-pgan"}).json()
    assert moved["management_area"]["slug"] == "native-pt2" and moved["thematique"]["slug"] == "dopage-pgan"
    assert moved["code"] == "Nat_0001" and moved["name"] == "Recuit Mg"

    # changer de projet laisse sa thématique ; une thématique seule se lit dans le projet actuel
    elsewhere = client.patch("/api/microprojects/recuit", json={"area": "nova-pt1"}).json()
    assert elsewhere["management_area"]["slug"] == "nova-pt1" and elsewhere["thematique"] is None
    assert client.patch("/api/microprojects/recuit", json={"thematic": "pilote"}).json()["thematique"]["slug"] == "pilote"
    assert client.patch("/api/microprojects/recuit", json={"thematic": None}).json()["thematique"] is None


def test_moving_a_microprojet_checks_its_target(client):
    signup(client, "boss@example.com")
    create_thematic(client, "native-pt2", "Dopage PGaN")
    create_microproject(client, "Recuit")

    def patch(body):
        return client.patch("/api/microprojects/recuit", json=body)

    assert patch({"area": "nova-pt1", "thematic": "dopage-pgan"}).status_code == 422  # la thématique d'un autre projet
    assert patch({"thematic": "dopage-pgan"}).status_code == 422  # il est encore dans « Non classé »
    assert patch({"area": "inconnu"}).status_code == 422
    assert patch({"area": None}).status_code == 422
    assert patch({"name": "  "}).status_code == 422
    assert client.get("/api/microprojets/recuit").json()["management_area"]["slug"] == "non-classe"  # rien n'a bougé
    assert_handler_404(client.patch("/api/microprojects/inconnu", json={"name": "x"}))


def test_only_an_owner_or_an_admin_moves_a_microprojet(client):
    signup(client, "boss@example.com")  # admin, pas membre du µprojet
    signup(client, "owner@example.com")
    create_microproject(client, "Recuit")
    join_as(client, "recuit", "editor@example.com", owner="owner@example.com", role="editor")

    assert client.patch("/api/microprojects/recuit", json={"area": "native-pt2"}).status_code == 403
    signup(client, "stranger@example.com")
    assert client.patch("/api/microprojects/recuit", json={"name": "Pris"}).status_code == 403

    login(client, "boss@example.com")
    moved = move_microproject(client, "native-pt2", "recuit")
    assert moved["management_area"]["slug"] == "native-pt2" and moved["role"] is None
    assert [row["microproject"]["slug"] for row in experiment_stats(client, area="native-pt2")] == ["recuit"]


def test_microprojets_get_an_auto_incremented_number_from_their_corporate_project(client):
    signup(client, "boss@example.com")

    def create(name, area=None):
        body = {"name": name, **({"management_area_slug": area} if area else {})}
        return client.post("/api/microprojets", json=body).json()

    nat1, nat2 = create("Dopage A", "native-pt2"), create("Dopage B", "native-pt2")
    nov1 = create("Pilote", "nova-pt1")
    loose = create("Pas encore classé")
    assert [nat1["code"], nat2["code"], nov1["code"], loose["code"]] == ["Nat_0001", "Nat_0002", "Nov_0001", None]

    # rattaché plus tard : numéroté à ce moment-là ; déplacé ensuite : garde son numéro
    move_microproject(client, "datacom-vlc", loose["slug"])
    move_microproject(client, "nova-pt1", nat1["slug"])
    codes = {p["slug"]: p["code"] for p in client.get("/api/microprojets/tous").json()}
    assert codes[loose["slug"]] == "VLC_0001" and codes[nat1["slug"]] == "Nat_0001"
    assert create("Dopage C", "native-pt2")["code"] == "Nat_0003"  # jamais de numéro réutilisé

    for typed in ("Nat_0002", "nat 2", "NAT2", "Nat-02"):
        found = client.get(f"/api/microprojets/code/{typed}")
        assert found.status_code == 200 and found.json()["slug"] == nat2["slug"], typed
    assert_handler_404(client.get("/api/microprojets/code/Nat_0099"))
    redirect = client.get("/p/Nat_0002", follow_redirects=False)
    assert redirect.status_code == 302 and redirect.headers["location"] == f"/microprojets/{nat2['slug']}"

    assert client.patch("/api/areas/native-pt2", json={"code_prefix": "Ntv"}).json()["code_prefix"] == "Ntv"
    assert create("Dopage D", "native-pt2")["code"] == "Ntv_0001"
    assert client.get(f"/api/microprojets/{nat2['slug']}").json()["code"] == "Nat_0002"


def test_topbar_search_finds_microprojets_by_number_or_name(client):
    signup(client, "boss@example.com")
    for name in ("Dopage PGaN", "Amélioration IQE", "Double EBL"):
        create_microproject(client, name, management_area_slug="native-pt2")

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
    signup(client, "boss@example.com", name="Alice Martin")
    create_microproject(client, "Recuit Mg", management_area_slug="native-pt2")

    assert client.get("/api/microprojets/recuit-mg").json()["owners"] == [{"id": 1, "name": "Alice Martin"}]
    assert client.get("/api/microprojets").json()[0]["owners"][0]["name"] == "Alice Martin"
    row = experiment_stats(client, area="native-pt2")[0]
    assert row["microproject"]["owners"] == [{"id": 1, "name": "Alice Martin"}]
