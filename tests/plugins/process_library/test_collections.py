"""Ce que les trois bibliothèques ont en commun (``ARCHITECTURE.md`` § 5, process_library) : des
collections à plat, un ``id`` opaque, le nom comme simple champ, la portée modifiable, et les
droits d'écriture de chaque portée."""

from __future__ import annotations

import json

import pytest

from support.accounts import signup, switch_user
from support.http import assert_handler_404
from support.microprojects import create_microproject, join_as, signup_with_microproject
from support.process_library import BODIES, COLLECTIONS, by_name, create_item, delete_item, get_item, list_items, names, tech_brick, update_item

pytestmark = pytest.mark.parametrize("collection", COLLECTIONS)


def _body(collection: str, name: str) -> dict:
    return BODIES[collection](name)


def test_create_answers_201_with_a_location_and_the_item(client, collection):
    slug = signup_with_microproject(client, "loc@example.com", name="Alice")
    response = client.post(f"/api/{collection}", json={**_body(collection, "Element"), "scope": "microproject", "microproject": slug})

    assert response.status_code == 201
    item = response.json()
    assert response.headers["location"] == f"/api/{collection}/{item['id']}"
    assert item["name"] == "Element"
    assert item["scope"] == "microproject"
    assert item["microproject"] == slug
    assert item["created_by"]["name"] == "Alice"
    assert item["updated_by"] == item["created_by"]
    assert get_item(client, collection, item["id"]) == item


def test_delete_answers_204_and_the_item_is_gone(client, collection):
    slug = signup_with_microproject(client, "del@example.com")
    item = create_item(client, collection, _body(collection, "Element"), microproject=slug)

    delete_item(client, collection, item["id"])
    assert_handler_404(client.get(f"/api/{collection}/{item['id']}"))
    assert_handler_404(client.delete(f"/api/{collection}/{item['id']}"))


def test_renaming_onto_a_taken_name_is_a_conflict_and_overwrites_nothing(client, collection):
    slug = signup_with_microproject(client, "b6@example.com")
    first = create_item(client, collection, _body(collection, "Premier"), microproject=slug)
    second = create_item(client, collection, _body(collection, "Second"), microproject=slug)

    response = client.patch(f"/api/{collection}/{second['id']}", json={"name": "Premier"})
    assert response.status_code == 409
    listed = list_items(client, collection, microproject=slug, scope="microproject")
    assert sorted(names(listed)) == ["Premier", "Second"]
    assert by_name(listed, "Premier")["id"] == first["id"]


def test_a_name_with_a_slash_stays_reachable(client, collection):
    slug = signup_with_microproject(client, "slash@example.com")
    item = create_item(client, collection, _body(collection, "Masque / gravure"), microproject=slug)

    assert get_item(client, collection, item["id"])["name"] == "Masque / gravure"
    assert update_item(client, collection, item["id"], name="Masque/gravure 2")["name"] == "Masque/gravure 2"


def test_an_empty_name_is_invalid(client, collection):
    slug = signup_with_microproject(client, "empty@example.com")
    response = client.post(f"/api/{collection}", json={**_body(collection, "  "), "scope": "microproject", "microproject": slug})
    assert response.status_code == 422


def test_the_scope_is_changed_by_a_patch(client, collection):
    """La case « Partagée » du constructeur : cochée sur un élément existant, elle le partage."""
    slug = signup_with_microproject(client, "scope@example.com")
    item = create_item(client, collection, _body(collection, "Element"), microproject=slug)

    shared = update_item(client, collection, item["id"], scope="shared")
    assert (shared["id"], shared["scope"], shared["microproject"]) == (item["id"], "shared", None)
    other = create_microproject(client, "Autre")["slug"]
    assert names(list_items(client, collection, microproject=other), "shared") == ["Element"]
    assert names(list_items(client, collection, microproject=slug), "microproject") == []

    back = update_item(client, collection, item["id"], scope="microproject", microproject=other)
    assert (back["scope"], back["microproject"]) == ("microproject", other)
    assert names(list_items(client, collection, microproject=other), "microproject") == ["Element"]
    assert names(list_items(client, collection, scope="shared")) == []


def test_moving_onto_a_taken_name_is_a_conflict(client, collection):
    slug = signup_with_microproject(client, "move409@example.com")
    create_item(client, collection, _body(collection, "Element"), scope="shared")
    item = create_item(client, collection, _body(collection, "Element"), microproject=slug)

    assert client.patch(f"/api/{collection}/{item['id']}", json={"scope": "shared"}).status_code == 409
    assert names(list_items(client, collection, microproject=slug), "microproject") == ["Element"]


def test_a_patch_without_effect_writes_nothing(client, collection):
    signup(client, "admin@example.com")  # le premier compte est administrateur
    signup(client, "author@example.com", name="Auteur")
    item = create_item(client, collection, _body(collection, "Element"), scope="shared")

    switch_user(client, "admin@example.com")
    same = update_item(client, collection, item["id"], name="Element")
    assert same["updated_by"]["name"] == "Auteur"


def test_a_shared_item_is_changed_only_by_its_author_or_an_admin(client, collection):
    signup(client, "admin@example.com")  # le premier compte est administrateur
    signup(client, "author@example.com")
    item = create_item(client, collection, _body(collection, "Commun"), scope="shared")
    assert item["can_edit"] is True

    switch_user(client, "other@example.com")
    seen = by_name(list_items(client, collection, scope="shared"), "Commun")
    assert seen["can_edit"] is False
    assert client.patch(f"/api/{collection}/{item['id']}", json={"name": "Pris"}).status_code == 403
    assert client.delete(f"/api/{collection}/{item['id']}").status_code == 403

    switch_user(client, "admin@example.com")
    assert update_item(client, collection, item["id"], name="Renomme")["updated_by"]["id"] != item["created_by"]["id"]
    delete_item(client, collection, item["id"])


def test_a_microproject_item_is_hidden_from_non_members_and_written_by_its_editors(client, collection):
    slug = signup_with_microproject(client, "owner@example.com")
    item = create_item(client, collection, _body(collection, "Interne"), microproject=slug)

    switch_user(client, "outsider@example.com")
    assert_handler_404(client.get(f"/api/{collection}/{item['id']}"))
    assert client.get(f"/api/{collection}", params={"microproject": slug}).status_code == 403
    assert client.delete(f"/api/{collection}/{item['id']}").status_code == 404

    join_as(client, slug, "viewer@example.com", owner="owner@example.com", role="viewer")
    assert get_item(client, collection, item["id"])["can_edit"] is False
    assert client.patch(f"/api/{collection}/{item['id']}", json={"name": "Non"}).status_code == 403


def test_an_item_cannot_be_moved_into_a_microproject_one_cannot_edit(client, collection):
    foreign = signup_with_microproject(client, "foreign@example.com", "Etranger")
    signup(client, "mover@example.com")
    item = create_item(client, collection, _body(collection, "Element"), scope="shared")

    response = client.patch(f"/api/{collection}/{item['id']}", json={"scope": "microproject", "microproject": foreign})
    assert response.status_code == 403


def test_builtin_items_are_read_only(client, collection):
    signup(client, "builtin@example.com")  # administrateur : même lui ne modifie pas un élément intégré ici
    if collection == "tech-bricks":  # aucune brique livrée : on en déclare une dans briques.yml (du JSON est du YAML)
        content = json.dumps({"bricks": [tech_brick("Brique livrée")]})
        assert client.put("/api/library/files/tech-bricks", json={"content": content}).status_code == 200
    item = list_items(client, collection, scope="builtin")[0]
    assert item["id"].startswith("builtin-")
    assert get_item(client, collection, item["id"]) == item
    assert client.patch(f"/api/{collection}/{item['id']}", json={"name": "Autre"}).status_code == 403
    assert client.delete(f"/api/{collection}/{item['id']}").status_code == 403
    assert client.post(f"/api/{collection}", json={**_body(collection, "X"), "scope": "builtin"}).status_code == 422


def test_listing_one_microprojects_items_needs_the_microproject(client, collection):
    signup(client, "list@example.com")
    assert client.get(f"/api/{collection}", params={"scope": "microproject"}).status_code == 422
    assert client.post(f"/api/{collection}", json={**_body(collection, "X"), "scope": "microproject"}).status_code == 422


def test_without_a_microproject_the_list_is_builtin_and_shared(client, collection):
    slug = signup_with_microproject(client, "hub@example.com")
    create_item(client, collection, _body(collection, "Partage"), scope="shared")
    create_item(client, collection, _body(collection, "Interne"), microproject=slug)

    listed = list_items(client, collection)
    assert {item["scope"] for item in listed} <= {"builtin", "shared"}
    assert "Partage" in names(listed) and "Interne" not in names(listed)


def test_an_invalid_item_on_disk_is_skipped_and_kept(client, data_dir, collection):
    from spectre.plugins.process_library.service import COLLECTIONS as STORES

    slug = signup_with_microproject(client, "invalid@example.com")
    create_item(client, collection, _body(collection, "Valide"), scope="shared")
    store = next(c for c in STORES if c.key == collection)
    path = data_dir / store.shared_filename
    data = json.loads(path.read_text(encoding="utf-8"))
    data["items"].append({"id": "abimé", "name": "Abimé"})  # champs obligatoires manquants
    path.write_text(json.dumps(data), encoding="utf-8")

    assert names(list_items(client, collection, scope="shared")) == ["Valide"]
    create_item(client, collection, _body(collection, "Autre"), microproject=slug)
    create_item(client, collection, _body(collection, "Encore"), scope="shared")
    kept = json.loads(path.read_text(encoding="utf-8"))["items"]
    assert [raw["name"] for raw in kept] == ["Valide", "Abimé", "Encore"]
