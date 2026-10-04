"""Le plugin kpis_demo n'existe que sur une instance de démonstration (``SPECTRE_DEMO_DATA=1``) : ses
séries fictives remplacent alors l'EQE encore sans source, et la fiche d'étude derrière un point
devient lisible."""

from __future__ import annotations

import pytest

from support.accounts import signup
from support.http import ROUTER_NOT_FOUND, assert_handler_404


@pytest.fixture()
def demo_client(data_dir, monkeypatch):
    monkeypatch.setenv("SPECTRE_DEMO_DATA", "1")
    from fastapi.testclient import TestClient

    from spectre.kernel.app import create_app

    with TestClient(create_app()) as test_client:
        yield test_client


def test_eqe_demo_trend_rises_and_opens_a_mock_study_fiche(demo_client):
    client = demo_client
    signup(client, "boss@example.com")
    kpis = {k["key"]: k for k in client.get("/api/areas/native-pt2/kpis").json()}
    assert kpis["eqe"]["status"] == "demo" and kpis["activite"]["status"] == "live"
    assert list(kpis)[:2] == ["activite", "eqe"]  # l'EQE de démo prend la place de l'EQE à brancher

    eqe = client.get("/api/areas/native-pt2/kpis/eqe?months=12").json()
    assert eqe["status"] == "demo" and "fictives" in eqe["message"]
    values = [p["value"] for p in eqe["points"]]
    assert values[-1] > values[0] + 4  # clearly rising
    studies = [p for p in eqe["points"] if p.get("study")]
    assert studies and all(p["label"] for p in studies)

    fiche = client.get(f"/api/areas/native-pt2/kpis/eqe/studies/{studies[-1]['study']}").json()
    assert fiche["demo"] is True and fiche["project"] == "Native (PT2)"
    assert "<svg" in fiche["structure_svg"] and "InGaN" in fiche["materials"]
    assert fiche["objective"]["target"] == 10.0 and fiche["conclusion"]["summary"]
    assert any(node["state"] == "current" for node in fiche["tree"]["nodes"]) and fiche["tree"]["edges"]

    assert_handler_404(client.get("/api/areas/native-pt2/kpis/eqe/studies/inconnue"), "inconnue")
    assert_handler_404(client.get("/api/areas/native-pt2/kpis/activite/studies/eqe-ref"))  # pas un KPI de démo
    assert_handler_404(client.get("/api/areas/native-pt2/kpis/inconnu/studies/eqe-ref"))
    assert_handler_404(client.get("/api/areas/inconnu/kpis/eqe/studies/eqe-ref"))
    assert client.get("/static/kpis_demo/study.js").status_code == 200


def test_without_demo_data_the_eqe_waits_for_its_source(client):
    signup(client, "boss@example.com")
    eqe = client.get("/api/areas/native-pt2/kpis/eqe").json()
    assert eqe["status"] == "placeholder" and eqe["points"] == []

    # ni la route de la fiche, ni les fichiers du plugin
    missing = client.get("/api/areas/native-pt2/kpis/eqe/studies/eqe-ref")
    assert missing.status_code == 404 and missing.json()["detail"] == ROUTER_NOT_FOUND
    assert client.get("/static/kpis_demo/study.js").status_code == 404


def test_a_material_colour_with_html_is_escaped_in_the_demo_study_svg(demo_client):
    # la couleur d'un matériau vient de la bibliothèque éditable et finit dans un attribut du SVG,
    # que la fiche insère par innerHTML ; sans cache, la correction de la bibliothèque se voit aussitôt
    from spectre.plugins.library.service import library_dir

    client = demo_client
    signup(client, "boss@example.com")
    url = "/api/areas/native-pt2/kpis/eqe/studies/eqe-ref"
    assert 'fill="#dbe4ee"' in client.get(url).json()["structure_svg"]  # le saphir de la bibliothèque livrée

    library = library_dir() / "materiaux.yml"
    original = library.read_text(encoding="utf-8")
    hostile = '"><img src=x onerror=alert(1)>'
    library.write_text(original.replace('color: "#dbe4ee"', f"color: '{hostile}'"), encoding="utf-8")
    svg = client.get(url).json()["structure_svg"]
    assert "<img" not in svg and "&lt;img src=x onerror=alert(1)&gt;" in svg

    library.write_text(original, encoding="utf-8")
    assert 'fill="#dbe4ee"' in client.get(url).json()["structure_svg"]
