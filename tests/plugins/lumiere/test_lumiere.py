"""Le plugin lumiere : un rapport Lumière demandé pour une plaque, généré (ici dans la requête :
``SPECTRE_LUMIERE_SYNC=1``) sur la démo, gardé sous <data>/lumiere/reports et téléchargeable par qui l'a
demandé ; les modèles de rapport ; l'historique. Lumière doit être installé (sinon le plugin n'existe pas)."""

from __future__ import annotations

import pytest

pytest.importorskip("lumiere_report")

from spectre.plugins.lumiere import engine, service, templates  # noqa: E402
from support.accounts import login, signup  # noqa: E402

LASERMARK = "T001"  # scénario « en cours » de la démo du suivi : étapes MES (dont une mesure), FDL, tests


@pytest.fixture(autouse=True)
def demo(monkeypatch):
    monkeypatch.setenv("SPECTRE_DEMO_DATA", "1")
    monkeypatch.setenv("SPECTRE_LUMIERE_SYNC", "1")


def test_the_templates_say_what_they_contain_and_for_what(client):
    signup(client, "boss@example.com")
    data = client.get("/api/lumiere/templates", params={"context": "wafer"}).json()
    keys = [t["key"] for t in data["templates"]]
    assert "fiche-plaque" in keys and data["contexts"]["wafer"] == "une plaque"
    fiche = next(t for t in data["templates"] if t["key"] == "fiche-plaque")
    assert fiche["context"] == "wafer" and "Vie en ligne" in fiche["slides"] and "Images MEB - G4" in fiche["slides"]
    assert client.get("/api/lumiere/templates", params={"context": "lot"}).json()["templates"] == []
    with pytest.raises(Exception):
        templates.get("inconnu")


def test_a_wafer_report_is_generated_kept_and_downloadable(client):
    signup(client, "boss@example.com")
    created = client.post("/api/lumiere/reports", json={"template": "fiche-plaque", "context": {"kind": "wafer", "key": LASERMARK}})
    assert created.status_code == 202, created.text
    report = created.json()
    assert created.headers["Location"].endswith(f"/api/lumiere/reports/{report['id']}")
    assert report["context"] == {"kind": "wafer", "key": LASERMARK} and report["title"] == f"Fiche plaque · {LASERMARK}"

    done = client.get(f"/api/lumiere/reports/{report['id']}").json()
    assert done["status"] == "done", done["message"]
    assert done["bytes"] > 10_000 and done["file_url"] == f"/api/lumiere/reports/{report['id']}/file"
    path = service.reports_dir() / f"{report['id']}.html"
    assert path.is_file()

    file = client.get(done["file_url"])
    assert file.status_code == 200 and file.headers["content-type"].startswith("text/html")
    assert "attachment" in file.headers["content-disposition"] and f"-{report['id']}.html" in file.headers["content-disposition"]
    html = file.text
    assert f"Plaque {LASERMARK}" in html  # le titre
    for slide in ("Contexte", "Vie en ligne", "Images MEB - G4"):
        assert slide in html
    assert "spectre-facts" in html  # le bloc HTML de Spectre (contexte) sur la slide
    assert "Mesure PL" in html  # le parcours MES de la démo, par le bloc de suivi de Lumière ou le tableau de repli
    assert "cartes" in html and "Plotly" in html  # les données par type (eqe / pl de la démo) en WaferMaps

    listed = client.get("/api/lumiere/reports", params={"context_kind": "wafer", "context_key": LASERMARK}).json()["reports"]
    assert [r["id"] for r in listed] == [report["id"]]

    assert client.delete(f"/api/lumiere/reports/{report['id']}").status_code == 204
    assert not path.exists()
    assert client.get(f"/api/lumiere/reports/{report['id']}").status_code == 404


def test_a_report_belongs_to_who_asked_it_and_the_context_is_checked(client):
    signup(client, "alice@example.com")
    report = client.post("/api/lumiere/reports", json={"template": "fiche-plaque", "context": {"kind": "wafer", "key": LASERMARK}}).json()
    assert report["status"] == "done"
    assert client.post("/api/lumiere/reports", json={"template": "fiche-plaque", "context": {"kind": "lot", "key": "QRO09"}}).json()["code"] == "wrong_context"
    assert client.post("/api/lumiere/reports", json={"template": "fiche-plaque", "context": {"kind": "wafer", "key": ""}}).json()["code"] == "missing_context_key"
    assert client.post("/api/lumiere/reports", json={"template": "inconnu", "context": {"kind": "wafer", "key": LASERMARK}}).status_code == 404

    signup(client, "bob@example.com")
    assert client.get(f"/api/lumiere/reports/{report['id']}").json()["code"] == "not_report_owner"
    assert client.get(f"/api/lumiere/reports/{report['id']}/file").status_code == 403
    assert client.get("/api/lumiere/reports").json()["reports"] == []
    assert client.get("/api/lumiere/storage").status_code == 403

    login(client, "alice@example.com")
    storage = client.get("/api/lumiere/storage").json()  # alice est le premier compte : administratrice
    assert storage["reports"] == 1 and storage["bytes"] == report["bytes"] or storage["bytes"] > 0


def test_a_failing_build_is_an_error_report_not_a_crash(client, monkeypatch):
    signup(client, "boss@example.com")

    def boom(user, key):
        raise RuntimeError("plus de Plotly")

    monkeypatch.setitem(templates.TEMPLATES, "casse", templates.Template("casse", "Cassé", "", "wafer", boom, ("x",)))
    report = client.post("/api/lumiere/reports", json={"template": "casse", "context": {"kind": "wafer", "key": LASERMARK}}).json()
    assert report["status"] == "error" and "RuntimeError" in report["message"] and report["file_url"] is None
    assert client.get(f"/api/lumiere/reports/{report['id']}/file").json()["code"] == "report_not_ready"


def test_the_html_block_renders_what_spectre_gives_it():
    block = engine.html_block("<p>bonjour</p>", title="Contexte", subtitle="études")
    html = block.render()
    assert "<p>bonjour</p>" in html and "Contexte" in html and "études" in html and block.needs_plotly is False
