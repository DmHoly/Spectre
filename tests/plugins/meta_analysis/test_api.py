"""/api/analyses : une analyse garde son cadre - titre, question, plaques (la référence d'abord), conclusion -,
se retrouve depuis chacune de ses plaques, se lit et s'écrit par tout compte, se supprime par son auteur ou un
administrateur."""

from __future__ import annotations

from support.accounts import signup, switch_user
from support.http import assert_handler_404, assert_ok
from support.meta_analysis import create_analysis, lasermarks, list_analyses, update_analysis


def test_an_analysis_keeps_its_reference_first_and_its_wafers_once(client):
    signup(client, "analyse-cree@example.com", name="Ada")
    created = create_analysis(client, "  Pourquoi   B12 brille ", ["W-REF", "b12", "W REF", "w-ref", "C7"], question="EQE + 30 % ?")

    assert created["title"] == "Pourquoi B12 brille"
    assert created["question"] == "EQE + 30 % ?" and created["conclusion"] == ""
    # une même plaque, écrite autrement, n'entre qu'une fois ; la première écriture est gardée
    assert lasermarks(created) == ["W-REF", "b12", "C7"]
    assert created["reference"] == {"key": "WREF", "lasermark": "W-REF"}
    assert created["created_by"] == created["updated_by"] == "Ada"
    assert assert_ok(client.get(f"/api/analyses/{created['id']}")) == created


def test_changing_the_order_changes_the_reference_and_the_conclusion_is_kept(client):
    signup(client, "analyse-ordre@example.com")
    analysis = create_analysis(client, "Ordre", ["W1", "W2", "W3"])

    changed = assert_ok(update_analysis(client, analysis["id"], wafers=["W2", "W1"], conclusion="  La gravure fait tout.  "))
    assert lasermarks(changed) == ["W2", "W1"]
    assert changed["reference"]["key"] == "W2"
    assert changed["conclusion"] == "La gravure fait tout."
    assert changed["title"] == "Ordre"  # ce qui n'est pas envoyé ne change pas

    # sans « wafers », les plaques restent
    assert lasermarks(assert_ok(update_analysis(client, analysis["id"], question="Et le recuit ?"))) == ["W2", "W1"]


def test_an_analysis_is_found_from_each_of_its_wafers(client):
    signup(client, "analyse-liste@example.com")
    first = create_analysis(client, "Première", ["W1", "W2"])
    second = create_analysis(client, "Seconde", ["w-2", "W3"])

    assert [a["id"] for a in list_analyses(client)] == [second["id"], first["id"]]  # la plus récente d'abord
    assert [a["title"] for a in list_analyses(client, wafer="W 2")] == ["Seconde", "Première"]
    assert [a["title"] for a in list_analyses(client, wafer="W3")] == ["Seconde"]
    assert list_analyses(client, wafer="W9") == []

    # ôter une plaque ôte l'analyse de sa liste
    update_analysis(client, first["id"], wafers=["W1"])
    assert [a["title"] for a in list_analyses(client, wafer="W2")] == ["Seconde"]


def test_a_title_and_a_reference_are_required_and_the_wafers_are_bounded(client):
    signup(client, "analyse-refus@example.com")
    assert client.post("/api/analyses", json={"title": "  ", "wafers": ["W1"]}).json()["code"] == "missing_title"
    assert client.post("/api/analyses", json={"title": "Vide", "wafers": [" ", ""]}).json()["code"] == "no_wafers"

    analysis = create_analysis(client, "Bornes", ["W1"])
    too_many = update_analysis(client, analysis["id"], wafers=[f"W{i}" for i in range(17)])
    assert too_many.status_code == 422
    refused = update_analysis(client, analysis["id"], wafers=[])
    assert refused.status_code == 422 and refused.json()["code"] == "no_wafers"
    assert update_analysis(client, analysis["id"], title="").json()["code"] == "missing_title"
    assert_handler_404(update_analysis(client, 999, title="x"), "analyse")


def test_anyone_enriches_an_analysis_but_only_its_author_or_an_admin_deletes_it(client):
    signup(client, "analyse-admin@example.com", name="Admin")  # le premier compte est administrateur
    switch_user(client, "analyse-auteur@example.com", name="Auteur")
    analysis = create_analysis(client, "Partagée", ["W1", "W2"])

    switch_user(client, "analyse-autre@example.com", name="Autre")
    changed = assert_ok(update_analysis(client, analysis["id"], conclusion="Vu par un autre"))
    assert changed["updated_by"] == "Autre" and changed["created_by"] == "Auteur"
    refused = client.delete(f"/api/analyses/{analysis['id']}")
    assert refused.status_code == 403 and refused.json()["code"] == "not_analysis_author"

    switch_user(client, "analyse-admin@example.com")
    assert client.delete(f"/api/analyses/{analysis['id']}").status_code == 204
    assert_handler_404(client.get(f"/api/analyses/{analysis['id']}"), "analyse")
    assert list_analyses(client, wafer="W1") == []


def test_the_author_deletes_their_own_analysis(client):
    signup(client, "analyse-proprio@example.com")
    analysis = create_analysis(client, "À jeter", ["W1"])
    assert client.delete(f"/api/analyses/{analysis['id']}").status_code == 204
    assert list_analyses(client) == []
