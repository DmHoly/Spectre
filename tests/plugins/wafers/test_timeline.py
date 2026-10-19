"""La frise d'une plaque (spectre.plugins.wafers.timeline) : les événements datés de sa vie en ligne (fabrication
et mesures MES, tests, étapes JIRA faites) et ceux que les autres plugins déclarent (les jours de données de
wafer_data, les acquisitions MEB de sem_images), sur un seul axe, dessinés en SVG cliquable ; la route."""

from __future__ import annotations

from datetime import datetime

import pytest

from spectre.plugins.wafers import timeline
from support.accounts import signup

LASERMARK = "T001"  # démo : scénario « en cours » (étapes MES dont « Mesure PL », FDL avec étapes faites et annulées)


@pytest.fixture(autouse=True)
def demo(monkeypatch):
    monkeypatch.setenv("SPECTRE_DEMO_DATA", "1")


def test_dates_are_read_as_the_fiches_write_them():
    assert timeline.parse_date("2026-09-02 04:48") == datetime(2026, 9, 2, 4, 48)
    assert timeline.parse_date("2026-10-17T01:40:24+00:00") == datetime(2026, 10, 17, 1, 40, 24)
    assert timeline.parse_date("2026-09-01") == datetime(2026, 9, 1)
    assert timeline.parse_date("2026-09-01 10:00:00.123456") == datetime(2026, 9, 1, 10, 0, 0, 123456)
    assert timeline.parse_date("") is None and timeline.parse_date("hier") is None and timeline.parse_date(None) is None


def test_the_online_life_gives_fabrication_measures_tests_and_done_jira_steps():
    fiche = {
        "steps": [
            {"step": "SAG_SIN.WET_EKC", "start": "2026-09-01 08:00", "end_effective": "2026-09-01 10:00", "equipment": "WET-02", "measurement": False},
            {"step": "SAG_SIN.MEASUREMENT_DEV", "start": "2026-09-02 08:00", "end_effective": None, "equipment": "INSPECT-01", "measurement": True},
        ],
        "tests": [{"type": "EQE", "date": "2026-09-03 09:00", "end": "2026-09-03 11:00", "sensor": "54°"}],
        "fdls": {"FDL-1": {"steps": [
            {"stage": "Litho", "category": "done", "closed": "2026-08-30 12:00", "assignee": "A"},
            {"stage": "Dépôt", "category": "skipped", "closed": None},
            {"stage": "Recuit", "category": "todo", "closed": None},
        ]}},
    }
    found = timeline.tracking_events(fiche)
    kinds = [(e["kind"], e["label"]) for e in found]
    assert kinds == [("fab", "SAG_SIN.WET_EKC"), ("measure", "SAG_SIN.MEASUREMENT_DEV"), ("test", "EQE"), ("jira", "Litho")]
    assert found[0]["end"] == "2026-09-01 10:00" and found[0]["ref"] == {"detail": "action", "index": 0, "running": False}
    assert found[1]["ref"]["running"] is True and found[1]["end"] is None
    assert found[2]["ref"] == {"detail": "test", "index": 0} and "54°" in found[2]["detail"]
    assert found[3]["ref"] == {"detail": "fdl-step", "request": "FDL-1", "index": 0} and "FDL-1" in found[3]["detail"]


def test_the_svg_draws_one_clickable_mark_per_event_and_says_when_empty():
    found = timeline.tracking_events({
        "steps": [{"step": "A.X", "start": "2026-09-01 08:00", "end_effective": "2026-09-01 10:00"}, {"step": "A.MESURE", "start": "2026-09-05 08:00", "end_effective": "2026-09-05 09:00", "measurement": True}],
        "tests": [{"type": "PL", "date": "2026-09-06"}],
        "fdls": {},
    })
    for i, e in enumerate(found):
        e["index"] = i
    svg = timeline.svg(found, title="Frise de X")
    assert svg.count('data-detail="timeline"') == 3 and 'data-index="2"' in svg
    assert "plate-timeline__event--measure" in svg and "plate-timeline__event--test" in svg
    assert "<title>A.MESURE · 2026-09-05 08:00 → 2026-09-05 09:00" in svg
    assert "Fabrication (MES)" in svg and "Mesures (MES)" in svg and "Données" in svg
    assert "var(--" not in svg  # autonome : le rapport Lumière l'emporte tel quel
    assert "Aucun événement daté" in timeline.svg([])


def test_registered_sources_add_their_events_and_a_failing_one_is_ignored(client, monkeypatch):
    signup(client, "boss@example.com")
    monkeypatch.setattr(timeline, "_SOURCES", {})
    timeline.register_source("test_ok", lambda user, lm: [{"kind": "data", "at": "2026-09-10", "end": None, "label": f"données de {lm}", "detail": "", "ref": {"detail": "data", "hook": "x"}}])

    def boom(user, lm):
        raise RuntimeError("partage absent")

    timeline.register_source("test_ko", boom)
    data = client.get(f"/api/wafers/{LASERMARK}/timeline").json()
    kinds = {e["kind"] for e in data["events"]}
    assert {"fab", "measure", "data"} <= kinds  # la démo a une « Mesure PL », et la source de test ses données
    extra = [e for e in data["events"] if e["source"] == "test_ok"]
    assert len(extra) == 1 and extra[0]["label"] == f"données de {LASERMARK}" and extra[0]["at"] == "2026-09-10 00:00"
    assert [e["index"] for e in data["events"]] == list(range(len(data["events"])))
    assert data["events"] == sorted(data["events"], key=lambda e: (e["at"], e["kind"]))
    assert data["counts"]["data"] >= 1 and data["counts"]["measure"] >= 1
    assert data["svg"].count('data-detail="timeline"') == len(data["events"])


def test_the_demo_wafer_has_data_days_from_wafer_data_on_its_frieze(client):
    """wafer_data déclare les jours de mesure des types datés (la PL de la démo a une colonne « PL date »)."""
    signup(client, "boss@example.com")
    data = client.get(f"/api/wafers/{LASERMARK}/timeline").json()
    pl = [e for e in data["events"] if e["source"] == "PRISM pl"]
    assert pl and all(e["kind"] == "data" and e["ref"]["hook"] == "pl" and e["ref"]["rows"] > 0 for e in pl)
    assert pl[0]["label"].startswith("PL") or "ligne" in pl[0]["label"]


def test_the_frieze_needs_a_session(client):
    assert client.get(f"/api/wafers/{LASERMARK}/timeline").status_code == 401
