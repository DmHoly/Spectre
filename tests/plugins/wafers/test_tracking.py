"""La vie d'une plaque en ligne (spectre.plugins.wafers.tracking) : la fiche assemblée depuis les
tables de la source (tracking_model), la source PRISM et la démo (tracking_source), et les règles de
relecture - au plus toutes les 24 h, plus jamais pour une plaque immobile depuis 30 jours, toujours
sur le bouton. Aucun test ne touche à une base : la démo répond aux mêmes lectures que PRISM, et
PRISM lui-même est remplacé par un enregistreur d'appels."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from spectre.kernel.errors import UpstreamError
from spectre.plugins.wafers import tracking, tracking_model, tracking_source
from spectre.plugins.wafers.tracking_source import HOOKS, DemoSource, PrismSource, demo_scenario

from support.accounts import signup
from support.wafers import get_tracking, refresh_tracking

NOW = datetime(2026, 10, 14, 9, 0)


def _lasermark(scenario: str) -> str:
    """Un lasermark de démo qui tombe sur ce scénario (déterministe : le même à chaque exécution)."""
    for n in range(500):
        lm = f"T{n:03d}"
        if demo_scenario(lm) == scenario:
            return lm
    raise AssertionError(scenario)


# --- la fiche --------------------------------------------------------------------------------------


def test_the_demo_covers_every_scenario_and_the_fiche_says_the_status():
    source = DemoSource(now=lambda: NOW)
    seen = {}
    for scenario in ("running", "waiting", "old", "missing", "alias"):
        fiche = tracking_model.build(source.fetch(_lasermark(scenario)), now=NOW)
        seen[scenario] = fiche["status"]
        assert all(p["ok"] for p in fiche["phases"].values())
        assert fiche["epitaxy"] and fiche["tests"] and fiche["tickets"] and fiche["record"]["wafer_name"]
    assert seen == {"running": "en cours", "waiting": "en attente", "old": "clos", "missing": "introuvable", "alias": "en cours"}


def test_a_running_wafer_shows_its_current_step_and_lot_name_from_jira():
    fiche = tracking_model.build(DemoSource(now=lambda: NOW).fetch(_lasermark("running")), now=NOW)
    assert fiche["current"]["step"] and fiche["current"]["equipment"] and fiche["current"]["idle_h"] == 0
    assert fiche["lot"].startswith("E26") and fiche["lot_name"].startswith("QMDE") and fiche["lot_source"] == "JIRA"
    assert fiche["steps"][-1]["end"] is None and fiche["n_steps"] == len(fiche["steps"])
    # l'épitaxie Gozer complétée par l'étape MES EPI.EPITAXY, sans écraser Gozer
    epi = fiche["epitaxy"][0]
    assert epi["run"].startswith("RUN-") and epi["reactor"].startswith("R") and epi["mes_recipe"] == "SPC_PT2_LED_G_MOCVD_PM1"
    # l'avancement des FDL citées (par la plaque, par le lot, par l'épitaxie), ordonné par le chaînage JIRA
    assert set(fiche["fdls"]) >= {t["request"] for t in fiche["tickets"]}
    flow = fiche["fdls"][fiche["tickets"][0]["request"]]
    assert flow["order"] == "chain" and flow["pct"] == 50 and flow["running"] and flow["n"] == len(flow["steps"])


def test_a_waiting_wafer_has_a_rework_and_an_unclosed_step_that_does_not_make_it_running():
    fiche = tracking_model.build(DemoSource(now=lambda: NOW).fetch(_lasermark("waiting")), now=NOW)
    assert fiche["status"] == "en attente" and fiche["current"]["idle_h"] > 0
    assert fiche["n_rework"] == 1 and fiche["n_unclosed"] == 1
    orphan = next(s for s in fiche["steps"] if s["unclosed"])
    assert orphan["end"] is None and orphan["end_effective"] is not None


def test_a_renamed_wafer_keeps_its_whole_history_under_both_identifiers():
    lm = _lasermark("alias")
    fiche = tracking_model.build(DemoSource(now=lambda: NOW).fetch(lm), now=NOW)
    assert fiche["aliases"] == [f"{lm.upper()}-B"]
    assert fiche["status"] == "en cours" and fiche["n_steps"] > 2


def test_a_closed_fdl_after_the_last_movement_closes_the_wafer_and_it_is_dormant():
    fiche = tracking_model.build(DemoSource(now=lambda: NOW).fetch(_lasermark("old")), now=NOW)
    assert fiche["status"] == "clos" and fiche["closed_at"] and fiche["last_fdl"]["state"] == "clos"
    assert fiche["last_movement"] < (NOW - timedelta(days=30)).strftime("%Y-%m-%d %H:%M")
    assert tracking.is_dormant(fiche["last_movement"], NOW.replace(tzinfo=timezone.utc))


def test_a_wafer_unknown_to_the_mes_still_has_its_gozer_side():
    fiche = tracking_model.build(DemoSource(now=lambda: NOW).fetch(_lasermark("missing")), now=NOW)
    assert fiche["status"] == "introuvable" and fiche["steps"] == [] and fiche["current"] is None
    assert fiche["record"]["substrat_lasermark"] and fiche["tickets"] and fiche["tests"]
    assert fiche["last_movement"] is not None  # un test, un ticket : la plaque a bougé


def test_lot_names_follow_the_nomenclature():
    assert tracking_model.find_lots("Lot QMDE 06 en split, puis qtwe12 et QT3") == ["QMDE06", "QTWE12", "QT3"]
    assert tracking_model.find_lots("E26090001") == []


def test_fdl_steps_follow_the_jira_chain_and_cancelled_steps_do_not_count():
    rows = [
        {"Request_Number": "FDL-1", "jira_key": "B", "jira_workshop_stage": "Gravure", "status": "In Progress", "jira_previous_ws": "A", "jira_next_ws": "C"},
        {"Request_Number": "FDL-1", "jira_key": "A", "jira_workshop_stage": "Litho", "status": "Done", "jira_closure_date": "2026-10-01 10:00", "jira_next_ws": "B"},
        {"Request_Number": "FDL-1", "jira_key": "C", "jira_workshop_stage": "Dépôt", "status": "Canceled", "jira_previous_ws": "B"},
        {"Request_Number": "FDL-1", "jira_key": "D", "jira_workshop_stage": "Recuit", "status": "Ready To Do", "jira_previous_ws": "C", "jira_estimative_done_date": "2026-10-02 00:00"},
    ]
    flows = tracking_model.build_fdl_flows(pd.DataFrame(rows), NOW)
    flow = flows["FDL-1"]
    assert [s["key"] for s in flow["steps"]] == ["A", "B", "C", "D"] and flow["order"] == "chain"
    assert flow["pct"] == 33 and flow["n_skipped"] == 1 and flow["running"] == ["Gravure"]
    assert flow["next"] == ["Recuit"] and flow["n_late"] == 1  # Recuit : prête (C écartée), fin estimée passée


# --- la source PRISM ----------------------------------------------------------------------------------


def test_the_prism_source_reads_the_tracking_hooks_with_their_parameters(monkeypatch):
    """PRISM est remplacé par les tables de la démo : ce qui est vérifié, c'est la suite des
    lectures - les hooks et leurs paramètres, puis la MES relue avec l'identifiant rencontré."""
    demo = DemoSource(now=lambda: NOW)
    lm = _lasermark("alias")
    tables = demo._tables(lm)
    calls: list[tuple[str, dict]] = []

    def run(hook: str, params: dict) -> pd.DataFrame:
        assert hook in HOOKS and list(params) == [HOOKS[hook]]
        calls.append((hook, params))
        return demo._answer(tables, hook, params)

    monkeypatch.setattr(PrismSource, "_run", staticmethod(run))
    frames = PrismSource().fetch(lm)
    hooks = [h for h, _ in calls]
    assert hooks[:2] == ["wafer_mes_history", "wafer_mes_history"]  # la MES, puis l'identifiant de sortie
    assert set(calls[1][1]["wafer_names"]) >= {lm, f"{lm.upper()}-B"}
    assert hooks[2:] == ["wafer_epitaxy", "wafer_record", "wafer_fdl", "lot_fdl", "fdl_steps", "wafer_tests"]
    assert calls[-1][1]["wafer_names"] == sorted({lm.upper(), f"{lm.upper()}-B", f"W{lm.upper()[:6]}"})
    assert frames.aliases == {f"{lm.upper()}-B": lm} and frames.any_ok


def test_a_failing_base_leaves_the_other_phases_and_says_so(monkeypatch):
    demo = DemoSource(now=lambda: NOW)
    lm = _lasermark("running")
    tables = demo._tables(lm)

    def run(hook: str, params: dict) -> pd.DataFrame:
        if hook == "wafer_mes_history":
            raise RuntimeError("connexion impossible au profil 'gozer'")
        return demo._answer(tables, hook, params)

    monkeypatch.setattr(PrismSource, "_run", staticmethod(run))
    fiche = tracking_model.build(PrismSource().fetch(lm), now=NOW)
    assert fiche["phases"]["mes"] == {"ok": False, "rows": 0, "seconds": fiche["phases"]["mes"]["seconds"], "error": "connexion impossible au profil 'gozer'"}
    assert fiche["status"] == "introuvable" and fiche["epitaxy"] and fiche["tickets"]


def test_no_base_at_all_is_an_upstream_error(monkeypatch):
    def run(hook: str, params: dict) -> pd.DataFrame:
        raise RuntimeError("réseau")

    monkeypatch.setattr(PrismSource, "_run", staticmethod(run))
    with pytest.raises(UpstreamError):
        PrismSource().fetch("W1")


def test_the_tracking_hooks_are_in_the_installed_prism_catalogue():
    import prism

    missing = sorted(set(HOOKS) - set(prism.list_hooks()))
    if missing:
        pytest.skip(f"PRISM installé sans les hooks de traçabilité {missing} : réinstaller PRISM (ou PRISM_HOOKS_DIR)")
    for key, parameter in HOOKS.items():
        assert prism.load_hook(key).parameters == [parameter]


# --- les règles de relecture (API) ------------------------------------------------------------------


@pytest.fixture
def demo(monkeypatch):
    monkeypatch.setenv("SPECTRE_DEMO_DATA", "1")
    monkeypatch.setattr(tracking_source._DEMO, "_now", lambda: NOW)


def test_the_page_reads_the_bases_once_then_keeps_the_fiche_for_a_day(client, demo, monkeypatch):
    signup(client, "tracking@example.com")
    lm = _lasermark("running")
    first = get_tracking(client, lm).json()
    assert first["status"] == "en cours" and first["lasermark"] == lm
    assert first["meta"]["source"] == "demo" and first["meta"]["refreshed"] and first["meta"]["freshness"] == "fresh"
    assert first["meta"]["auto_refresh"] and not first["meta"]["dormant"] and first["meta"]["error"] is None
    assert first["meta"]["rules"] == {"auto_refresh_hours": 24, "dormant_days": 30}

    calls = []
    original = DemoSource.fetch
    monkeypatch.setattr(DemoSource, "fetch", lambda self, lasermark: calls.append(lasermark) or original(self, lasermark))
    again = get_tracking(client, lm.lower()).json()  # par sa clé, sans casse
    assert not again["meta"]["refreshed"] and again["meta"]["fetched_at"] == first["meta"]["fetched_at"] and calls == []

    # 25 h plus tard : relue d'elle-même ; le bouton relit quoi qu'il arrive
    later = datetime.fromisoformat(first["meta"]["fetched_at"]) + timedelta(hours=25)
    monkeypatch.setattr(tracking, "_utcnow", lambda: later)
    assert get_tracking(client, lm).json()["meta"]["refreshed"] and calls == [lm]
    assert refresh_tracking(client, lm).json()["meta"]["refreshed"] and calls == [lm, lm]
    assert get_tracking(client, lm).json()["meta"]["age_hours"] == 0


def test_a_dormant_wafer_is_not_reread_by_itself_but_the_button_still_does(client, demo, monkeypatch):
    signup(client, "dormant@example.com")
    lm = _lasermark("old")
    first = get_tracking(client, lm).json()
    assert first["status"] == "clos" and first["meta"]["dormant"] and not first["meta"]["auto_refresh"]
    later = datetime.fromisoformat(first["meta"]["fetched_at"]) + timedelta(days=10)
    monkeypatch.setattr(tracking, "_utcnow", lambda: later)
    kept = get_tracking(client, lm).json()
    assert not kept["meta"]["refreshed"] and kept["meta"]["freshness"] == "stale" and kept["meta"]["age_hours"] == 240
    assert refresh_tracking(client, lm).json()["meta"]["refreshed"]


def test_a_failed_reread_keeps_the_previous_fiche_and_says_why(client, demo, monkeypatch):
    signup(client, "failed@example.com")
    lm = _lasermark("waiting")
    first = get_tracking(client, lm).json()

    def down(self, lasermark):
        raise UpstreamError("les bases de la ligne ne répondent pas : réseau")

    monkeypatch.setattr(DemoSource, "fetch", down)
    kept = refresh_tracking(client, lm).json()
    assert kept["status"] == "en attente" and kept["meta"]["fetched_at"] == first["meta"]["fetched_at"]
    assert kept["meta"]["error"] == "les bases de la ligne ne répondent pas : réseau" and not kept["meta"]["refreshed"]
    # sans fiche gardée, l'erreur est celle de la source
    response = get_tracking(client, "jamais-lue")
    assert response.status_code == 502 and response.json()["code"] == "upstream_error"


def test_tracking_needs_a_session(client):
    assert get_tracking(client, "W1").status_code == 401
