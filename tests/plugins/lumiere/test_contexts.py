"""Les contextes d'un rapport Lumière autres que la plaque : une analyse de plaques, une étude, un µprojet, un lot -
chacun avec son modèle livré, ses plaques, ses droits (une étude ou un µprojet demandent d'en être membre) ;
générés sur la démo (``SPECTRE_LUMIERE_SYNC=1``)."""

from __future__ import annotations

import pytest

pytest.importorskip("lumiere_report")

from spectre.plugins.lumiere import blocks, context, templates  # noqa: E402
from support.accounts import signup  # noqa: E402
from support.experiments import conclude, launch  # noqa: E402
from support.lots import add_wafers, create_lot  # noqa: E402
from support.meta_analysis import create_analysis  # noqa: E402
from support.microprojects import create_microproject  # noqa: E402

AREA = "native-pt2"


@pytest.fixture(autouse=True)
def demo(monkeypatch):
    monkeypatch.setenv("SPECTRE_DEMO_DATA", "1")
    monkeypatch.setenv("SPECTRE_LUMIERE_SYNC", "1")


def report(client, template, kind, key):
    made = client.post("/api/lumiere/reports", json={"template": template, "context": {"kind": kind, "key": key}})
    assert made.status_code == 202, made.text
    return made.json()


def html_of(client, made):
    assert made["status"] == "done", made["message"]
    return client.get(made["file_url"]).text


def test_every_context_has_its_builtin_template_and_blocks(client):
    signup(client, "boss@example.com")
    data = client.get("/api/lumiere/templates").json()
    by_context = {t["context"]: t for t in data["templates"] if t["builtin"]}
    assert set(by_context) == {"wafer", "analysis", "study", "microproject", "lot"} and set(data["contexts"]) == set(context.CONTEXTS)
    assert "KPI comparés" in by_context["analysis"]["outline"] and "Structure" in by_context["study"]["outline"]
    for kind in context.CONTEXTS:
        keys = {b["key"] for b in client.get("/api/lumiere/blocks", params={"context": kind}).json()["blocks"]}
        assert {"text", "context.facts", "wafer.timeline", "wafer.tracking", "data.maps", "data.boxes", "sem.gallery"} <= keys
    assert "analysis.kpis" in {b.key for b in blocks.for_context("analysis")} and "analysis.kpis" not in {b.key for b in blocks.for_context("lot")}
    with pytest.raises(Exception, match="ne s'applique pas"):
        templates.clean_slides([{"kind": "grid", "title": "x", "nrows": 1, "ncols": 1, "cells": [{"r": 0, "c": 0, "block": {"type": "analysis.kpis", "options": {}}}]}], "lot")


def test_an_analysis_report_compares_its_wafers(client):
    signup(client, "boss@example.com")
    analysis = create_analysis(client, "Deux plaques", ["T001", "T002"], question="Laquelle est la meilleure ?")
    client.patch(f"/api/analyses/{analysis['id']}", json={"kpis": [{"hook": "eqe", "column": "max_EQE", "label": "", "filters": [], "better": "high"}], "conclusion": "T002 gagne."})
    made = report(client, "analyse", "analysis", str(analysis["id"]))
    assert made["title"] == "Analyse de plaques · Analyse · Deux plaques"
    html = html_of(client, made)
    assert "Laquelle est la meilleure" in html and "T002 gagne" in html and "référence" in html
    assert "KPI comparés" in html and "max_EQE" in html and "T001" in html and "T002" in html
    assert "Frises des mesures" in html and html.count("plate-timeline__svg") == 2  # une frise par plaque
    assert client.post("/api/lumiere/reports", json={"template": "analyse", "context": {"kind": "analysis", "key": "999999"}}).status_code == 404
    assert client.post("/api/lumiere/reports", json={"template": "analyse", "context": {"kind": "analysis", "key": "abc"}}).status_code == 404


def test_a_study_report_needs_membership_and_shows_the_study(client):
    signup(client, "alice@example.com")
    slug = create_microproject(client, "Projet rapport", area=AREA)["slug"]
    study = launch(client, slug, title="Gravure profonde", intent="Voir l'effet de la gravure", entities=[{"sample_id": "T001"}, {"sample_id": "T002"}])
    conclude(client, slug, study["id"], summary="La gravure aide.", next_steps="Refaire à 2 µm.")
    key = f"{slug}/{study['id']}"
    made = report(client, "etude", "study", key)
    assert made["title"] == "Étude · Étude · Gravure profonde"
    html = html_of(client, made)
    assert "effet de la gravure" in html and "La gravure aide." in html and "Refaire à 2 µm." in html
    assert "Structure" in html and ("<svg" in html) and "T001" in html and "T002" in html
    assert client.post("/api/lumiere/reports", json={"template": "etude", "context": {"kind": "study", "key": f"{slug}/inconnue"}}).status_code == 404
    assert client.post("/api/lumiere/reports", json={"template": "etude", "context": {"kind": "study", "key": slug}}).json()["code"] == "invalid_study_key"

    signup(client, "bob@example.com")  # pas membre du µprojet
    assert client.post("/api/lumiere/reports", json={"template": "etude", "context": {"kind": "study", "key": key}}).status_code == 403
    assert client.post("/api/lumiere/reports", json={"template": "microprojet", "context": {"kind": "microproject", "key": slug}}).status_code == 403


def test_a_microproject_report_lists_its_studies(client):
    signup(client, "boss@example.com")
    slug = create_microproject(client, "Projet synthèse", area=AREA)["slug"]
    launch(client, slug, title="Étude A", intent="a", entities=[{"sample_id": "T001"}])
    launch(client, slug, title="Étude B", intent="b", entities=[{"sample_id": "T002"}])
    made = report(client, "microprojet", "microproject", slug)
    assert made["title"].startswith("µprojet · µprojet ")
    html = html_of(client, made)
    assert "Étude A" in html and "Étude B" in html and "Études du µprojet" in html
    assert "Vie en ligne des plaques" in html and "Suivi de 2 plaques" in html
    assert client.post("/api/lumiere/reports", json={"template": "microprojet", "context": {"kind": "microproject", "key": "nexiste-pas"}}).status_code == 404


def test_a_lot_report_covers_its_wafers(client):
    signup(client, "boss@example.com")
    lot = create_lot(client, "QRO09", title="Lot de test")
    add_wafers(client, lot["id"], ["T001", "T002"])
    made = report(client, "lot", "lot", "qro09")
    assert made["title"] == "Lot · Lot QRO09"
    html = html_of(client, made)
    assert "Lot de test" in html and "QRO09" in html and "Suivi de 2 plaques" in html and html.count("plate-timeline__svg") == 2
    assert client.post("/api/lumiere/reports", json={"template": "lot", "context": {"kind": "lot", "key": "ZZZ99"}}).status_code == 404
    assert client.post("/api/lumiere/reports", json={"template": "fiche-plaque", "context": {"kind": "lot", "key": "QRO09"}}).json()["code"] == "wrong_context"


def test_a_slide_of_another_context_is_previewed_on_it(client):
    signup(client, "boss@example.com")
    lot = create_lot(client, "QRO10")
    add_wafers(client, lot["id"], ["T001"])
    slides = [{"kind": "grid", "title": "Le lot", "nrows": 1, "ncols": 1, "cells": [{"r": 0, "c": 0, "block": {"type": "context.facts", "options": {}}}]}]
    html = client.post("/api/lumiere/preview", json={"context": "lot", "slides": slides, "index": 0, "key": "QRO10"}).json()["html"]
    assert "QRO10" in html and "spectre-facts" in html
