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
    builtin = {t["key"]: t for t in data["templates"] if t["builtin"]}
    assert {t["context"] for t in builtin.values()} == {"wafer", "analysis", "study", "microproject", "lot"} and set(data["contexts"]) == set(context.CONTEXTS)
    assert "KPI comparés" in builtin["analyse"]["outline"] and "Structure" in builtin["etude"]["outline"] and "Cahier" in builtin["cahier"]["outline"]
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


def test_the_notebook_of_a_study_is_one_slide_per_entry(client):
    from support.notebook import add_entry, add_manual, take_snapshot, update_entry

    signup(client, "boss@example.com")
    slug = create_microproject(client, "Projet cahier", area=AREA)["slug"]
    study = launch(client, slug, title="Cahier test", intent="Mesurer", entities=[{"sample_id": "T001"}, {"sample_id": "T002"}])
    snapshot = take_snapshot(client, slug, "eqe", ["T001", "T002"])
    add_entry(client, slug, study["id"], snapshot["snapshot_id"], title="EQE après gravure", note="Première mesure")
    add_manual(client, slug, study["id"], "Rugosité AFM", measurements=[{"value": {"number": 1.25, "unit": "nm", "name": "rugosite_rms"}, "text": "Mesure au centre", "table": {"columns": ["point", "rms"], "rows": [["centre", 1.25], ["bord", 1.4]]}}], interpretation="Lisse.")
    hidden = add_manual(client, slug, study["id"], "Brouillon caché", measurements=[{"text": "pas dans le rapport"}])
    update_entry(client, slug, study["id"], hidden["id"], in_report=False)

    blocks_api = {b["key"]: b for b in client.get("/api/lumiere/blocks", params={"context": "study"}).json()["blocks"]}
    assert blocks_api["study.notebook"]["expands"] is True and blocks_api["context.facts"]["expands"] is False

    made = report(client, "cahier", "study", f"{slug}/{study['id']}")
    html = html_of(client, made)
    assert "EQE après gravure" in html and "Première mesure" in html
    assert "Rugosité AFM" in html and "1.25" in html and "rugosite_rms" in html and "Mesure au centre" in html and "Lisse." in html
    assert "Brouillon caché" not in html and "pas dans le rapport" not in html
    assert html.count("cahier de mesures</span>") >= 2 or html.count("cahier de mesures") >= 2  # une slide par entrée
    assert "figé du cahier" in html  # les distributions de l'instantané (SummaryBoxPlots)

    everything = client.post("/api/lumiere/preview", json={
        "context": "study", "key": f"{slug}/{study['id']}", "index": 0,
        "slides": [{"kind": "grid", "title": "Tout le cahier", "nrows": 1, "ncols": 1, "cells": [{"r": 0, "c": 0, "block": {"type": "study.notebook", "options": {"all_entries": True}}}]}],
    }).json()["html"]
    assert "Brouillon caché" in everything and "Rugosité AFM" in everything

    empty = launch(client, slug, title="Sans cahier", intent="rien", entities=[{"sample_id": "T001"}])
    html = html_of(client, report(client, "cahier", "study", f"{slug}/{empty['id']}"))
    assert "Le cahier de cette étude est vide" in html
