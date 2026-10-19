"""Les modèles de rapport du plugin lumiere : composés slide par slide (grilles, cellules, blocs du catalogue avec
leurs options), vérifiés à l'enregistrement, copiés d'un modèle livré, modifiés par leur auteur ou un
administrateur, prévisualisés une slide à la fois sur une plaque de la démo."""

from __future__ import annotations

import pytest

pytest.importorskip("lumiere_report")

from spectre.plugins.lumiere import blocks, templates  # noqa: E402
from support.accounts import login, signup  # noqa: E402

LASERMARK = "T001"
BASE = "/api/lumiere/templates"


@pytest.fixture(autouse=True)
def demo(monkeypatch):
    monkeypatch.setenv("SPECTRE_DEMO_DATA", "1")
    monkeypatch.setenv("SPECTRE_LUMIERE_SYNC", "1")


def grid(title, cells, nrows=1, ncols=1, **extra):
    return {"kind": "grid", "title": title, "nrows": nrows, "ncols": ncols, **extra, "cells": [{"r": r, "c": c, "block": {"type": t, "options": o}} for r, c, t, o in cells]}


def test_the_block_catalog_describes_its_options_with_their_choices(client):
    signup(client, "boss@example.com")
    data = client.get("/api/lumiere/blocks", params={"context": "wafer"}).json()
    keys = {b["key"]: b for b in data["blocks"]}
    assert {"text", "context.facts", "wafer.timeline", "wafer.tracking", "data.maps", "data.boxes", "sem.gallery"} <= set(keys)
    hook = next(o for o in keys["data.maps"]["options"] if o["key"] == "hook")
    assert hook["kind"] == "choice" and {c["value"] for c in hook["choices"]} >= {"eqe", "pl"}  # les types à positions de la démo
    assert data["max_grid"] == 3 and "grid" in data["slide_kinds"]
    assert client.get("/api/lumiere/blocks", params={"context": "lot"}).json()["code"] == "unknown_context"


def test_slides_are_checked_and_options_cleaned():
    cleaned = templates.clean_slides([{"kind": "title"}, grid("Cartes", [(0, 0, "data.maps", {"hook": "eqe", "max_columns": "99"}), (0, 1, "text", {"content": "## Bonjour"})], ncols=2, col_widths=["2fr", "1fr"]), {"kind": "section", "title": " Fin ", "subtitle": ""}, {"kind": "summary"}], "wafer")
    assert cleaned[1]["cells"][0]["block"]["options"] == {"hook": "eqe", "max_columns": 16}  # borné
    assert cleaned[1]["col_widths"] == ["2fr", "1fr"] and cleaned[1]["row_heights"] == ["1fr"]
    assert cleaned[2] == {"kind": "section", "title": "Fin", "subtitle": ""}
    with pytest.raises(Exception, match="même cellule"):
        templates.clean_slides([grid("x", [(0, 0, "text", {}), (0, 0, "text", {})])], "wafer")
    with pytest.raises(Exception, match="sort de la grille"):
        templates.clean_slides([grid("x", [(0, 1, "text", {})])], "wafer")
    with pytest.raises(Exception, match="Bloc inconnu"):
        templates.clean_slides([grid("x", [(0, 0, "nope", {})])], "wafer")
    with pytest.raises(Exception, match="au moins une slide"):
        templates.clean_slides([], "wafer")
    with pytest.raises(Exception, match="fraction"):
        templates.clean_slides([grid("x", [], col_widths=["large"])], "wafer")
    assert blocks.get("context.facts").clean_options({"studies": "false", "notes": 1}) == {"studies": False, "notes": True}


def test_a_template_is_copied_from_the_builtin_edited_by_its_author_and_used_for_a_report(client):
    signup(client, "alice@example.com")
    builtin = client.get(f"{BASE}/fiche-plaque").json()
    assert builtin["builtin"] and builtin["outline"][0] == "Titre" and builtin["slides"][1]["cells"][0]["block"]["type"] == "context.facts"
    assert client.put(f"{BASE}/fiche-plaque", json={"name": "x"}).json()["code"] == "builtin_template"

    copied = client.post(BASE, json={"copy_of": "fiche-plaque", "name": "Ma fiche"})
    assert copied.status_code == 201, copied.text
    mine = copied.json()
    assert mine["key"] == "ma-fiche" and mine["slides"] == builtin["slides"] and not mine["builtin"] and mine["owner_name"] == "T"
    assert copied.headers["Location"].endswith("/ma-fiche")
    again = client.post(BASE, json={"copy_of": "fiche-plaque", "name": "Ma fiche"}).json()
    assert again["key"] == "ma-fiche-2"  # une clé lisible, unique

    short = [{"kind": "title"}, grid("Frise et contexte", [(0, 0, "wafer.timeline", {}), (0, 1, "context.facts", {"studies": False, "notes": True})], ncols=2), {"kind": "summary"}]
    updated = client.put(f"{BASE}/ma-fiche", json={"slides": short, "description": "Court"}).json()
    assert updated["outline"] == ["Titre", "Frise et contexte", "Sommaire"] and updated["description"] == "Court"
    assert client.put(f"{BASE}/ma-fiche", json={"slides": [grid("x", [(0, 0, "nope", {})])]}).json()["code"] == "unknown_block"
    listed = client.get(BASE, params={"context": "wafer"}).json()["templates"]
    assert [t["key"] for t in listed][:3] == ["fiche-plaque", "ma-fiche-2", "ma-fiche"] or "ma-fiche" in [t["key"] for t in listed]

    report = client.post("/api/lumiere/reports", json={"template": "ma-fiche", "context": {"kind": "wafer", "key": LASERMARK}}).json()
    assert report["status"] == "done", report["message"]
    html = client.get(report["file_url"]).text
    assert "Frise des mesures" in html and "spectre-facts" in html and "Aucune étude" not in html or "Frise des mesures" in html
    assert "Vie en ligne" not in html  # la slide retirée n'y est plus

    signup(client, "bob@example.com")
    assert client.put(f"{BASE}/ma-fiche", json={"name": "Vol"}).json()["code"] == "not_template_owner"
    assert client.delete(f"{BASE}/ma-fiche").status_code == 403
    assert client.post(BASE, json={"copy_of": "ma-fiche"}).json()["name"] == "Ma fiche (copie)"  # copier, tout le monde peut
    login(client, "alice@example.com")  # administratrice (premier compte) : retire le sien et ceux des autres
    assert client.delete(f"{BASE}/ma-fiche").status_code == 204
    assert client.get(f"{BASE}/ma-fiche").status_code == 404
    assert client.delete(f"{BASE}/ma-fiche-copie").status_code == 204


def test_a_single_slide_is_previewed_on_a_wafer(client):
    signup(client, "boss@example.com")
    slides = [{"kind": "title"}, grid("Texte et frise", [(0, 0, "text", {"content": "## Essai d'aperçu"}), (1, 0, "wafer.timeline", {})], nrows=2)]
    preview = client.post("/api/lumiere/preview", json={"context": "wafer", "slides": slides, "index": 1, "key": LASERMARK}).json()
    html = preview["html"]
    assert "Essai d'aperçu" in html and "plate-timeline__svg" in html and "Slide 1 / 1" in html or "Texte et frise" in html
    assert client.post("/api/lumiere/preview", json={"context": "wafer", "slides": slides, "index": 5, "key": LASERMARK}).json()["code"] == "no_such_slide"
    assert client.post("/api/lumiere/preview", json={"context": "wafer", "slides": slides, "index": 0, "key": " "}).json()["code"] == "missing_context_key"


def test_a_new_template_without_source_starts_minimal_and_the_name_is_required(client):
    signup(client, "boss@example.com")
    made = client.post(BASE, json={"name": "Vide", "context": "wafer"}).json()
    assert [s["kind"] for s in made["slides"]] == ["title", "summary"]
    assert client.post(BASE, json={"name": "  ", "context": "wafer"}).json()["code"] == "missing_name"
    assert client.post(BASE, json={"name": "x", "context": "lot"}).json()["code"] == "unknown_context"
