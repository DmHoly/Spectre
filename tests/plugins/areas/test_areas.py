from __future__ import annotations

from support.accounts import signup
from support.areas import create_area, create_objective, create_thematic, get_area
from support.experiments import experiment_stats
from support.http import assert_handler_404
from support.microprojects import create_microproject, move_microproject


def _slugs(rows):
    return [row["microproject"]["slug"] for row in rows]


def test_new_microprojet_lands_in_the_system_area(client):
    signup(client, "boss@example.com")
    create_microproject(client, "Contact ohmique")

    areas = client.get("/api/areas").json()
    by_slug = {a["slug"]: a for a in areas}
    assert {"datacom-vlc", "nova-pt1", "native-pt2"} <= set(by_slug)  # 3 thèmes phares seedés
    system = [a for a in areas if a["is_system"]]
    assert [a["slug"] for a in system] == ["non-classe"] and areas[-1]["is_system"]  # « Non classé », en dernier
    assert system[0]["can_delete"] is False
    assert all(a["can_delete"] and not a["is_system"] for a in areas[:-1])
    assert _slugs(experiment_stats(client, area="non-classe")) == ["contact-ohmique"]
    assert "totals" not in areas[0] and "stats" not in areas[0] and "is_admin" not in areas[0]


def test_flagship_themes_are_seeded_on_a_fresh_instance(client):
    signup(client, "boss@example.com")
    names = {a["name"] for a in client.get("/api/areas").json()}
    assert {"VLC (microlink)", "Nova (PT1)", "Native (PT2)"} <= names


def test_admin_creates_an_area_and_moves_a_microprojet_into_it(client):
    signup(client, "boss@example.com")
    create_microproject(client, "Contact ohmique")

    created = client.post("/api/areas", json={"name": "Fiabilité", "strategy": "Réduire les retours"})
    assert created.status_code == 201
    assert created.headers["location"] == "/api/areas/fiabilite"
    body = created.json()
    assert body["slug"] == "fiabilite" and body["strategy"] == "Réduire les retours"
    assert body["thematics"] == [] and body["objectives"] == []
    assert get_area(client, "fiabilite")["name"] == "Fiabilité"

    moved = move_microproject(client, "fiabilite", "contact-ohmique")
    assert moved["area"] == {"slug": "fiabilite", "name": "Fiabilité"}
    assert _slugs(experiment_stats(client, area="fiabilite")) == ["contact-ohmique"]
    assert experiment_stats(client, area="non-classe") == []


def test_non_admin_reads_but_cannot_write_the_strategy_layer(client):
    signup(client, "boss@example.com")  # le premier compte est admin
    create_area(client, "Thème A")
    create_thematic(client, "theme-a", "T")
    objective = create_objective(client, "theme-a", "O")
    signup(client, "hand@example.com")

    assert client.get("/api/areas").status_code == 200
    assert client.get("/api/areas/theme-a").status_code == 200
    assert client.get("/api/areas/theme-a/thematics/t").status_code == 200
    assert client.post("/api/areas", json={"name": "Thème B"}).status_code == 403
    assert client.patch("/api/areas/theme-a", json={"name": "x"}).status_code == 403
    assert client.delete("/api/areas/theme-a").status_code == 403
    assert client.post("/api/areas/theme-a/thematics", json={"name": "x"}).status_code == 403
    assert client.patch("/api/areas/theme-a/thematics/t", json={"name": "x"}).status_code == 403
    assert client.delete("/api/areas/theme-a/thematics/t").status_code == 403
    assert client.post("/api/areas/theme-a/objectives", json={"title": "x"}).status_code == 403
    assert client.patch(f"/api/areas/theme-a/objectives/{objective['id']}", json={"title": "x"}).status_code == 403
    assert client.delete(f"/api/areas/theme-a/objectives/{objective['id']}").status_code == 403


def test_deleting_an_area_returns_its_microprojets_to_the_system_area(client):
    signup(client, "boss@example.com")
    create_microproject(client, "P1")
    slug = create_area(client, "Temporaire")["slug"]
    move_microproject(client, slug, "p1")

    deleted = client.delete(f"/api/areas/{slug}")
    assert deleted.status_code == 204 and deleted.content == b""
    assert _slugs(experiment_stats(client, area="non-classe")) == ["p1"]
    assert_handler_404(client.get(f"/api/areas/{slug}"))


def test_the_system_area_is_kept_and_takes_neither_thematique_nor_objective(client):
    signup(client, "boss@example.com")
    assert client.delete("/api/areas/non-classe").status_code == 409
    assert client.post("/api/areas/non-classe/thematics", json={"name": "T"}).status_code == 409
    assert client.post("/api/areas/non-classe/objectives", json={"title": "O"}).status_code == 409
    assert client.patch("/api/areas/non-classe", json={"code_prefix": "Ncl"}).status_code == 409  # il ne numérote rien
    renamed = client.patch("/api/areas/non-classe", json={"description": "En attente"})
    assert renamed.status_code == 200 and renamed.json()["description"] == "En attente"
    assert renamed.json()["name"] == "Non classé"  # un PATCH ne touche que les champs envoyés


def test_thematiques_group_microprojets_inside_a_corporate_project(client):
    signup(client, "boss@example.com")
    created = client.post("/api/areas/native-pt2/thematics", json={"name": "Dopage PGaN", "description": "Mg"})
    assert created.status_code == 201
    assert created.headers["location"] == "/api/areas/native-pt2/thematics/dopage-pgan"
    assert created.json()["slug"] == "dopage-pgan" and created.json()["area"] == {"slug": "native-pt2", "name": "Native (PT2)"}
    create_thematic(client, "native-pt2", "Double EBL")
    assert [t["slug"] for t in get_area(client, "native-pt2")["thematics"]] == ["dopage-pgan", "double-ebl"]

    recuit = create_microproject(client, "Recuit Mg", area="native-pt2", thematic="dopage-pgan")
    assert recuit["thematic"] == {"slug": "dopage-pgan", "name": "Dopage PGaN"}

    create_microproject(client, "Orphelin")
    move_microproject(client, "native-pt2", "orphelin", "double-ebl")
    by_slug = {row["microproject"]["slug"]: row["microproject"]["thematic"] for row in experiment_stats(client, area="native-pt2")}
    assert by_slug == {"recuit-mg": {"slug": "dopage-pgan", "name": "Dopage PGaN"}, "orphelin": {"slug": "double-ebl", "name": "Double EBL"}}

    # A thématique of another project is rejected.
    bad = client.post("/api/microprojects", json={"name": "X", "area": "nova-pt1", "thematic": "dopage-pgan"})
    assert bad.status_code == 422 and "n'appartient pas à ce projet" in bad.json()["detail"]

    renamed = client.patch("/api/areas/native-pt2/thematics/dopage-pgan", json={"name": "Dopage p-GaN"})
    assert renamed.status_code == 200
    assert (renamed.json()["slug"], renamed.json()["name"], renamed.json()["description"]) == ("dopage-pgan", "Dopage p-GaN", "Mg")
    assert client.get("/api/areas/native-pt2/thematics/dopage-pgan").json()["name"] == "Dopage p-GaN"

    # Deleting a thématique keeps its µprojets in the project, without thématique.
    deleted = client.delete("/api/areas/native-pt2/thematics/dopage-pgan")
    assert deleted.status_code == 204 and deleted.content == b""
    by_slug = {row["microproject"]["slug"]: row["microproject"]["thematic"] for row in experiment_stats(client, area="native-pt2")}
    assert by_slug["recuit-mg"] is None
    assert_handler_404(client.get("/api/areas/native-pt2/thematics/dopage-pgan"), "dopage-pgan")
    assert_handler_404(client.get("/api/areas/nova-pt1/thematics/double-ebl"))  # une thématique d'un autre projet


def test_thematics_are_listed_flat_for_every_project(client):
    signup(client, "boss@example.com")
    dopage = create_thematic(client, "native-pt2", "Dopage PGaN")
    create_thematic(client, "nova-pt1", "Pilote")

    every = client.get("/api/thematics").json()
    assert {(t["name"], t["area"]["slug"]) for t in every} == {("Dopage PGaN", "native-pt2"), ("Pilote", "nova-pt1")}
    assert client.get("/api/thematics?area=native-pt2").json() == [
        {"id": dopage["id"], "slug": "dopage-pgan", "name": "Dopage PGaN", "area": {"slug": "native-pt2", "name": "Native (PT2)"}}
    ]
    assert_handler_404(client.get("/api/thematics?area=inconnu"))


def test_corporate_objectives_are_ranked_and_editable(client):
    signup(client, "boss@example.com")
    base = "/api/areas/nova-pt1/objectives"
    first = client.post(base, json={"title": "Qualifier le procédé", "target": "T1 2027"})
    assert first.status_code == 201
    assert first.headers["location"] == f"{base}/{first.json()['id']}"
    assert client.get(first.headers["location"]).json() == first.json()  # le Location se lit
    assert_handler_404(client.get(f"/api/areas/native-pt2/objectives/{first.json()['id']}"))  # pas l'objectif de ce projet
    assert first.json()["title"] == "Qualifier le procédé" and first.json()["target"] == "T1 2027"
    create_objective(client, "nova-pt1", "Transférer en prod")
    create_objective(client, "nova-pt1", "Réduire le coût")
    area = get_area(client, "nova-pt1")
    ids = [o["id"] for o in area["objectives"]]
    assert [o["title"] for o in area["objectives"]] == ["Qualifier le procédé", "Transférer en prod", "Réduire le coût"]
    assert area["objectives_period"] == "6 prochains mois" and area["horizon_months"] == 6

    assert client.put(base, json={"ids": [ids[2], ids[0], ids[1]]}).status_code == 405  # plus de réordonnancement

    edited = client.patch(f"{base}/{ids[1]}", json={"title": "Transférer en production", "detail": "Ligne 200 mm"})
    assert edited.status_code == 200
    assert (edited.json()["title"], edited.json()["detail"]) == ("Transférer en production", "Ligne 200 mm")
    assert get_area(client, "nova-pt1")["objectives"][1]["title"] == "Transférer en production"
    deleted = client.delete(f"{base}/{ids[0]}")
    assert deleted.status_code == 204 and deleted.content == b""
    assert get_area(client, "nova-pt1")["objectives"][0]["title"] == "Transférer en production"
    assert_handler_404(client.patch(f"{base}/{ids[0]}", json={"title": "x"}))
    assert_handler_404(client.delete(f"/api/areas/native-pt2/objectives/{ids[1]}"))  # l'objectif d'un autre projet

    renamed = client.patch("/api/areas/nova-pt1", json={"objectives_period": "S1 2027"})
    assert renamed.status_code == 200
    assert renamed.json()["objectives_period"] == "S1 2027" and renamed.json()["name"] == "Nova (PT1)"
    assert renamed.json()["horizon_months"] == 6  # aucun nombre de mois : l'horizon par défaut
    assert client.patch("/api/areas/nova-pt1", json={"objectives_period": "12 prochains mois"}).json()["horizon_months"] == 12
    assert client.patch("/api/areas/nova-pt1", json={"objectives_period": "36 mois"}).json()["horizon_months"] == 24

    signup(client, "hand@example.com")
    assert get_area(client, "nova-pt1")["objectives"]


def test_objectives_record_a_bonus_percentage_and_the_microproject_that_validated_them(client):
    signup(client, "boss@example.com")
    create_objective(client, "nova-pt1", "Réduire le coût", weight=5)
    create_objective(client, "nova-pt1", "Sans pourcentage")
    create_objective(client, "nova-pt1", "Qualifier le procédé", weight=60)
    objectives = get_area(client, "nova-pt1")["objectives"]
    assert [(o["title"], o["weight"]) for o in objectives] == [
        ("Qualifier le procédé", 60),
        ("Réduire le coût", 5),
        ("Sans pourcentage", None),
    ]
    assert all("effort" not in o for o in objectives)  # un simple chiffre, rien de calculé
    assert all(o["achieved"] is False and o["validated_by"] is None for o in objectives)

    microproject = create_microproject(client, "Pilote procédé", area="nova-pt1")
    objective_id = objectives[0]["id"]
    done = client.patch(
        f"/api/areas/nova-pt1/objectives/{objective_id}", json={"achieved": True, "validated_by": microproject["slug"]}
    ).json()
    assert done["achieved"] is True and done["weight"] == 60 and done["title"] == "Qualifier le procédé"
    assert done["validated_by"] == {"slug": microproject["slug"], "code": "Nov_0001", "name": "Pilote procédé"}
    assert get_area(client, "nova-pt1")["objectives"][0]["validated_by"]["code"] == "Nov_0001"
    cleared = client.patch(f"/api/areas/nova-pt1/objectives/{objective_id}", json={"validated_by": None, "weight": None}).json()
    assert cleared["validated_by"] is None and cleared["weight"] is None and cleared["achieved"] is True

    nova = "/api/areas/nova-pt1/objectives"
    assert client.post(nova, json={"title": "Trop", "weight": 120}).status_code == 422
    assert client.post(nova, json={"title": "Zéro", "weight": 0}).status_code == 201
    assert client.post(nova, json={"title": "Fantôme", "validated_by": "inconnu"}).status_code == 422
    assert client.post(nova, json={"title": "  "}).status_code == 422


def test_code_prefix_of_a_project(client):
    signup(client, "boss@example.com")
    area = create_area(client, "Fiabilité")
    assert area["code_prefix"] == "Fia"
    assert client.patch(f"/api/areas/{area['slug']}", json={"code_prefix": "Nat"}).status_code == 409  # déjà pris
    assert client.patch(f"/api/areas/{area['slug']}", json={"code_prefix": "N4t"}).status_code == 422
    assert client.post("/api/areas", json={"name": "Autre", "code_prefix": "Nov"}).status_code == 409
    assert client.post("/api/areas", json={"name": " "}).status_code == 422
    assert client.patch("/api/areas/native-pt2", json={"code_prefix": "Ntv"}).json()["code_prefix"] == "Ntv"


def test_unknown_projects_are_404(client):
    signup(client, "boss@example.com")
    assert_handler_404(client.get("/api/areas/inconnu"), "inconnu")
    assert_handler_404(client.patch("/api/areas/inconnu", json={"name": "x"}))
    assert_handler_404(client.delete("/api/areas/inconnu"))
    assert_handler_404(client.post("/api/areas/inconnu/thematics", json={"name": "x"}))
    assert_handler_404(client.post("/api/areas/inconnu/objectives", json={"title": "x"}))


def test_the_pages_of_the_strategy_layer_are_served(client):
    signup(client, "boss@example.com")
    create_thematic(client, "native-pt2", "Dopage PGaN")
    for url in ("/", "/management/native-pt2", "/management/native-pt2/thematiques/dopage-pgan"):
        assert client.get(url).status_code == 200, url
