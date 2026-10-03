from __future__ import annotations

from support.accounts import signup
from support.experiments import launch, track_entities
from support.http import assert_handler_404
from support.microprojects import create_microproject, get_microproject, list_microprojects, signup_with_microproject


def test_create_microproject_makes_creator_owner(client):
    owner = signup(client, "owner@example.com", name="Owner")
    response = client.post("/api/microprojects", json={"name": "Couches minces", "description": "Salle blanche 2"})
    assert response.status_code == 201
    assert response.headers["location"] == "/api/microprojects/couches-minces"
    body = response.json()
    assert body == {
        "id": body["id"],
        "slug": "couches-minces",
        "code": None,
        "name": "Couches minces",
        "description": "Salle blanche 2",
        "role": "owner",
        "area": {"slug": "non-classe", "name": "Non classé"},
        "thematic": None,
        "owners": [{"id": owner["id"], "name": "Owner"}],
    }
    assert get_microproject(client, "couches-minces") == body
    assert list_microprojects(client) == [body]


def test_creating_requires_a_name(client):
    signup(client, "owner@example.com")
    assert client.post("/api/microprojects", json={"name": "  "}).status_code == 422


def test_slug_collision_gets_suffixed(client):
    signup(client, "owner@example.com", name="Owner")
    create_microproject(client, "Couches minces")
    assert create_microproject(client, "Couches minces")["slug"] == "couches-minces-2"


def test_a_microproject_never_gets_a_reserved_slug(client):
    signup(client, "owner@example.com")
    assert create_microproject(client, "Nouvelle")["slug"] == "nouvelle-2"
    assert create_microproject(client, "New")["slug"] == "new-2"


def test_nonexistent_microproject_is_404(client):
    signup(client, "owner@example.com", name="Owner")
    assert_handler_404(client.get("/api/microprojects/does-not-exist"), "introuvable")


def test_microproject_requires_authentication(client):
    assert client.get("/api/microprojects").status_code == 401


def test_the_old_routes_are_gone(client):
    signup(client, "owner@example.com")
    slug = create_microproject(client, "Projet")["slug"]
    for path in ("/api/microprojets", f"/api/microprojets/{slug}", "/api/microprojets/tous", "/api/microprojets/recherche?q=p"):
        response = client.get(path)
        assert response.status_code in (404, 405) and response.json()["detail"] in ("Not Found", "Method Not Allowed"), path


def test_listing_by_project_and_thematique(client):
    signup(client, "boss@example.com")
    client.post("/api/areas/native-pt2/thematics", json={"name": "Dopage PGaN"})
    create_microproject(client, "Recuit", area="native-pt2", thematic="dopage-pgan")
    create_microproject(client, "Gravure", area="native-pt2")
    create_microproject(client, "Ailleurs", area="nova-pt1")

    def slugs(**params):
        return sorted(p["slug"] for p in list_microprojects(client, **params))

    assert slugs(area="native-pt2") == ["gravure", "recuit"]
    assert slugs(area="native-pt2", thematic="dopage-pgan") == ["recuit"]
    assert_handler_404(client.get("/api/microprojects", params={"area": "inconnu"}))
    assert_handler_404(client.get("/api/microprojects", params={"area": "native-pt2", "thematic": "inconnue"}))
    assert client.get("/api/microprojects", params={"thematic": "dopage-pgan"}).status_code == 422


def test_listing_shows_only_my_microprojects(client):
    signup(client, "boss@example.com")
    create_microproject(client, "Le sien")
    signup(client, "hand@example.com")
    create_microproject(client, "Le mien")
    assert [p["slug"] for p in list_microprojects(client)] == ["le-mien"]


def test_search_and_number_combine_with_no_other_filter(client):
    signup(client, "boss@example.com")
    for params in ({"q": "x", "scope": "all"}, {"code": "Nat_1", "area": "native-pt2"}, {"q": "x", "thematic": "t"}):
        assert client.get("/api/microprojects", params=params).status_code == 422, params


def test_entity_history_is_empty_for_a_microproject_with_no_tracked_entities(client):
    slug = signup_with_microproject(client, "hist-empty@example.com", name="Owner")
    history = client.get(f"/api/microprojets/{slug}/entites/historique").json()
    assert history == {"sample_ids": [], "locations": [], "fdls": []}


def test_entity_history_collects_distinct_values_across_experiences(client):
    slug = signup_with_microproject(client, "hist@example.com", name="Owner")

    launch(client, slug, title="A", intent="x", entities=[{"sample_id": "W1-A1", "location": "congélateur B"}])
    second = launch(client, slug, title="B", intent="x", entities=[{"sample_id": "W1-A2", "location": "congélateur B"}])
    # a repeated value (même emplacement) doit rester unique dans l'historique
    track_entities(client, slug, second["id"], [{"sample_id": "W1-A2", "location": "congélateur B"}])

    history = client.get(f"/api/microprojets/{slug}/entites/historique").json()
    assert history == {"sample_ids": ["W1-A1", "W1-A2"], "locations": ["congélateur B"], "fdls": []}
