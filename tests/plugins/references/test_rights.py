"""Qui fait quoi sur une référence : tout compte connecté la lit et en crée une ; publier une version
demande le rôle editor sur le µprojet source ; renommer, décrire ou retirer revient à son créateur ou
à un admin. La source d'une version et les études qui en sont parties ne nomment que leur µprojet
pour qui n'en est pas membre."""

from __future__ import annotations

from support.accounts import login, signup
from support.experiments import launch
from support.microprojects import add_member, create_microproject, join_as
from support.references import (
    create_reference,
    delete_reference,
    get_reference,
    get_version,
    origin,
    patch_reference,
    post_reference,
    post_version,
    publish,
    published_from,
    references,
    version_graph,
)
from support.structures import steps


def _setup(client):
    """L'admin (premier compte), puis Léa, propriétaire du µprojet « Epi » où elle publie la
    référence « Epitaxie standard » (1.0), qu'une étude de son µprojet utilise."""
    signup(client, "admin@example.com", name="Admin")
    signup(client, "lea@example.com", name="Léa")
    slug = create_microproject(client, "Epi")["slug"]
    study = launch(client, slug, title="Epitaxie", intent="Depart", steps=steps(20))
    create_reference(client, "Epitaxie standard")
    publish(client, "epitaxie-standard", slug, study["id"])
    launch(client, slug, title="Suite", intent="Depuis la ref", steps=steps(20), reference_origin=origin("epitaxie-standard", "1.0"))
    return slug, study


def test_an_editor_of_the_source_publishes_a_viewer_or_an_outsider_does_not(client):
    slug, study = _setup(client)
    join_as(client, slug, "viewer@example.com", owner="lea@example.com", role="viewer")
    response = post_version(client, "epitaxie-standard", slug, study["id"])
    assert response.status_code == 403

    signup(client, "outsider@example.com")
    assert post_version(client, "epitaxie-standard", slug, study["id"]).status_code == 403

    join_as(client, slug, "editor@example.com", owner="lea@example.com", role="editor")
    launched = launch(client, slug, title="Plus epais", intent="x", steps=steps(25))
    assert publish(client, "epitaxie-standard", slug, launched["id"])["number"] == "1.1"


def test_anyone_signed_in_reads_and_creates_references(client):
    _setup(client)
    signup(client, "outsider@example.com", name="Ext")
    assert [r["slug"] for r in references(client)] == ["epitaxie-standard"]
    created = create_reference(client, "Mon point de depart")
    assert created["created_by"]["name"] == "Ext" and created["can_edit"] is True
    taken = post_reference(client, "EPITAXIE  Standard!")
    assert taken.status_code == 409 and taken.json()["code"] == "reference_name_taken"
    empty = post_reference(client, " -- ")
    assert empty.status_code == 422 and empty.json()["code"] == "invalid_reference_name"


def test_the_creator_or_an_admin_renames_and_describes(client):
    _setup(client)
    signup(client, "other@example.com")
    assert get_reference(client, "epitaxie-standard")["can_edit"] is False
    assert patch_reference(client, "epitaxie-standard", name="Autre").status_code == 403

    login(client, "lea@example.com")
    renamed = patch_reference(client, "epitaxie-standard", name="Épitaxie de base", description="Tampon AlN 20 nm")
    assert renamed.status_code == 200
    body = renamed.json()
    # le slug ne change pas : une étude cite sa référence par lui
    assert (body["slug"], body["name"], body["description"]) == ("epitaxie-standard", "Épitaxie de base", "Tampon AlN 20 nm")
    assert body["updated_by"]["name"] == "Léa"

    login(client, "admin@example.com")
    assert patch_reference(client, "epitaxie-standard", description="Revu").json()["description"] == "Revu"
    create_reference(client, "Autre")
    assert patch_reference(client, "epitaxie-standard", name="autre").status_code == 409


def test_retiring_a_reference(client):
    slug, _study = _setup(client)
    signup(client, "other@example.com")
    assert delete_reference(client, "epitaxie-standard").status_code == 403

    login(client, "lea@example.com")
    response = delete_reference(client, "epitaxie-standard")
    assert response.status_code == 409 and response.json()["code"] == "reference_has_versions"
    create_reference(client, "Brouillon")
    assert delete_reference(client, "brouillon").status_code == 204

    login(client, "admin@example.com")
    assert delete_reference(client, "epitaxie-standard").status_code == 204
    assert references(client) == []
    # l'étude qui en était partie garde son origine, désormais inconnue
    login(client, "lea@example.com")
    tips = client.get(f"/api/microprojects/{slug}/experiments").json()["items"]
    suite = client.get(f"/api/microprojects/{slug}/experiments/{next(t['id'] for t in tips if t['title'] == 'Suite')}").json()
    assert suite["reference_origin"] == {"reference": "epitaxie-standard", "version": "1.0"}


def test_the_slug_of_a_retired_reference_is_never_given_again(client):
    """Les études parties d'une référence retirée gardent une origine inconnue : une nouvelle
    référence du même nom reçoit un autre slug et ne compte pas leurs usages."""
    slug, _study = _setup(client)
    login(client, "admin@example.com")
    assert delete_reference(client, "epitaxie-standard").status_code == 204

    signup(client, "eve@example.com", name="Eve")
    eve_slug = create_microproject(client, "Eve")["slug"]
    again = create_reference(client, "Epitaxie standard", "Sans rapport")
    assert again["slug"] == "epitaxie-standard-2"
    publish(client, again["slug"], eve_slug, launch(client, eve_slug, title="Autre", intent="x", steps=steps(30))["id"])
    node = version_graph(client, again["slug"])["nodes"][0]
    assert (node["number"], node["usage_count"], node["usages"]) == ("1.0", 0, [])
    assert client.get("/api/references/epitaxie-standard").status_code == 404

    # une référence sans version (aucune étude n'a pu en partir) libère son slug
    create_reference(client, "Brouillon")
    assert delete_reference(client, "brouillon").status_code == 204
    assert create_reference(client, "Brouillon")["slug"] == "brouillon"


def test_sources_and_usages_are_masked_for_non_members(client):
    slug, study = _setup(client)
    member_view = version_graph(client, "epitaxie-standard")["nodes"][0]
    assert member_view["source"]["linked"] is True
    assert member_view["source"]["experiment_id"] == study["id"]
    assert member_view["source"]["title"] == "Epitaxie"
    assert member_view["usage_count"] == 1
    assert member_view["usages"][0]["title"] == "Suite" and member_view["usages"][0]["linked"] is True

    signup(client, "stranger@example.com")
    node = version_graph(client, "epitaxie-standard")["nodes"][0]
    assert node["source"] == {"microproject": {"name": "Epi"}, "linked": False}
    assert node["usages"] == [{"microproject": {"name": "Epi"}, "linked": False}]
    listed = references(client)[0]
    assert listed["latest_version"]["source"] == {"microproject": {"name": "Epi"}, "linked": False}
    assert listed["usage_count"] == 1
    # la structure, elle, est à tous : c'est un point de départ partagé
    assert get_version(client, "epitaxie-standard", "1.0")["process"]["steps"]

    # l'admin voit tout
    login(client, "admin@example.com")
    assert version_graph(client, "epitaxie-standard")["nodes"][0]["source"]["linked"] is True


def test_a_deleted_source_microproject_is_named_as_it_was(client):
    slug, _study = _setup(client)
    assert client.delete(f"/api/microprojects/{slug}", params={"confirm_name": "Epi"}).status_code == 204
    node = version_graph(client, "epitaxie-standard")["nodes"][0]
    assert node["source"] == {"microproject": {"name": "Epi", "deleted": True}, "linked": False}
    assert node["usages"] == []
    assert get_version(client, "epitaxie-standard", "1.0")["structure_svg"].startswith("<svg")


def test_versions_published_from_a_microproject_are_for_its_members(client):
    slug, study = _setup(client)
    published = published_from(client, slug)
    assert [(p["reference"]["slug"], p["number"], p["version_id"], p["label"]) for p in published] == [
        ("epitaxie-standard", "1.0", study["version_id"], "R Epitaxie standard 1.0")
    ]
    signup(client, "stranger@example.com")
    assert client.get("/api/reference-versions", params={"microproject": slug}).status_code == 403
    assert client.get("/api/reference-versions", params={"microproject": "inconnu"}).status_code == 404

    login(client, "lea@example.com")
    add_member(client, slug, "stranger@example.com", "viewer")
    login(client, "stranger@example.com")
    assert len(published_from(client, slug)) == 1
