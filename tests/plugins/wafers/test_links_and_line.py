"""Ce que la vie en ligne apporte à la plaque et à sa recherche : ses FDL (lues dans JIRA et Gozer,
dans l'en-tête et la recherche par FDL), ses renommages (XX devenue YY : liens vus dans la MES ou
déclarés, la lignée sur la page, chercher XX trouve YY), les descriptions des étapes JIRA, et la
structure attachée à une plaque sans µprojet. La démo répond à la place des bases."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest

from spectre.plugins.wafers import tracking_model, tracking_source
from spectre.plugins.wafers.tracking_source import demo_scenario

from support.accounts import signup, switch_user
from support.wafers import create_records, get_tracking, get_wafer, list_wafers

NOW = datetime(2026, 10, 15, 9, 0)


@pytest.fixture()
def demo(monkeypatch):
    monkeypatch.setenv("SPECTRE_DEMO_DATA", "1")
    monkeypatch.setattr(tracking_source._DEMO, "_now", lambda: NOW)


def _lasermark(scenario: str) -> str:
    for n in range(500):
        lm = f"T{n:03d}"
        if demo_scenario(lm) == scenario:
            return lm
    raise AssertionError(scenario)


# --- l'assemblage ------------------------------------------------------------------------------


def test_jira_text_keeps_its_lines_for_the_detail_window():
    raw = "h2. Contexte\r\nSplit sur le *recuit*  contact.\n\n\n{color:red}Attention{color}"
    assert tracking_model.clean_jira_text(raw) == "h2. Contexte Split sur le recuit contact. Attention"
    assert tracking_model.clean_jira_text(raw, keep_lines=True) == "Contexte\nSplit sur le recuit contact.\n\nAttention"


def test_the_plate_fdls_are_its_own_tickets_and_gozer_requests_not_the_lot_ones():
    rec = {
        "tickets": [{"request": "FDL-0012", "via": "wafer"}, {"request": "FDL-900", "via": "lot"}],
        "epitaxy": [{"request": "FDL-100"}],
        "base_wafer_fdl": ["FDL-50"],
        "test_fdl": ["FDL-12"],
    }
    assert tracking_model.plate_fdls(rec) == ["FDL-12", "FDL-100", "FDL-50"]


def test_renames_are_read_in_the_mes_in_order_and_once():
    steps = tracking_model.mes_rows(
        pd.DataFrame(
            [
                {"physical_item_id": "XX1", "physical_item_id_out": "XX1", "step_start_date": "2026-01-01 08:00", "step_end_date": "2026-01-01 09:00", "step_order": 1, "last_update": None},
                {"physical_item_id": "XX1", "physical_item_id_out": "YY1", "step_start_date": "2026-01-02 08:00", "step_end_date": "2026-01-02 09:00", "step_order": 2, "step_detailed_name": "BOND.COLLAGE", "last_update": None},
                {"physical_item_id": "XX1", "physical_item_id_out": "YY1", "step_start_date": "2026-01-03 08:00", "step_end_date": "2026-01-03 09:00", "step_order": 3, "last_update": None},
            ]
        ),
        {"XX1", "YY1"},
    )
    assert tracking_model.renames(steps) == [{"from": "XX1", "to": "YY1", "at": "2026-01-02 09:00", "step": "BOND.COLLAGE"}]


# --- FDL et lot de la vie en ligne -------------------------------------------------------------


def test_the_line_fdls_reach_the_passport_and_the_fdl_search(client, demo):
    signup(client, "fdl@example.com")
    lm = _lasermark("running")
    create_records(client, [lm])  # la fiche créée lit tout de suite la vie en ligne de la plaque
    fiche = get_tracking(client, lm).json()
    assert fiche["fdl_numbers"] and fiche["lot_name"]
    assert fiche["meta"]["refreshed"] is False  # déjà gardée : la page n'a pas relu les bases
    plate = get_wafer(client, lm)
    assert plate["line_fdl"] == fiche["fdl_numbers"] and plate["lot_name"] == fiche["lot_name"]
    number = fiche["fdl_numbers"][0]
    assert [w["lasermark"] for w in list_wafers(client, fdl=number)] == [lm]  # une fiche, sans étude, trouvée par sa FDL
    assert list_wafers(client, q=lm)[0]["line_fdl"] == fiche["fdl_numbers"]


def test_a_step_description_comes_whole(client, demo):
    signup(client, "desc@example.com")
    fiche = get_tracking(client, _lasermark("running")).json()
    step = next(iter(fiche["fdls"].values()))["steps"][0]
    assert "\n" in step["description"] and step["description"].startswith(step["stage"])


# --- renommages ----------------------------------------------------------------------------------


def test_a_rename_seen_in_the_mes_links_both_names(client, demo):
    signup(client, "alias@example.com")
    lm = _lasermark("alias")
    create_records(client, [lm])
    get_tracking(client, lm)  # la MES dit : entrée sous lm, sortie sous lm-B
    plate = get_wafer(client, lm)
    assert [n["lasermark"] for n in plate["links"]["after"]] == [f"{lm}-B"]
    assert plate["links"]["current"]["lasermark"] == f"{lm}-B" and plate["links"]["links"][0]["source"] == "mes"
    other = get_wafer(client, f"{lm}-B")  # la page de l'autre nom le sait aussi
    assert [n["lasermark"] for n in other["links"]["before"]] == [lm]
    get_tracking(client, lm)  # relue : pas de doublon
    assert len(get_wafer(client, lm)["links"]["links"]) == 1


def test_a_declared_rename_makes_the_old_name_find_the_new_plate(client):
    signup(client, "bond@example.com")
    create_records(client, ["YY-77"])
    response = client.post("/api/wafer-links", json={"from_lasermark": "xx-12", "to_lasermark": "YY-77", "note": "collage CMOS", "happened_at": "2026-09-01"})
    assert response.status_code == 201, response.text
    found = list_wafers(client, q="XX12")
    assert [w["lasermark"] for w in found] == ["YY-77"] and found[0]["matched_alias"] == "xx-12"
    assert list_wafers(client, q="YY-77")[0]["aliases"] == ["xx-12"]
    chain = get_wafer(client, "XX-12")["links"]  # la page de l'ancien nom, sans fiche ni étude
    assert chain["current"]["lasermark"] == "YY-77" and chain["after"][0]["note"] == "collage CMOS"
    # déjà reliées, dans un sens ou dans l'autre ; une plaque ne devient pas elle-même
    assert client.post("/api/wafer-links", json={"from_lasermark": "YY77", "to_lasermark": "XX 12"}).status_code == 409
    assert client.post("/api/wafer-links", json={"from_lasermark": "A1", "to_lasermark": "a-1"}).status_code == 422


def test_a_declared_link_is_removed_by_its_author_only(client):
    signup(client, "author@example.com")
    link = client.post("/api/wafer-links", json={"from_lasermark": "XX1", "to_lasermark": "YY1"}).json()
    signup(client, "other@example.com")
    assert client.delete(f"/api/wafer-links/{link['id']}").status_code == 403
    switch_user(client, "author@example.com")
    assert client.delete(f"/api/wafer-links/{link['id']}").status_code == 204
    assert get_wafer(client, "XX1")["links"]["links"] == []


# --- structure attachée sans µprojet -------------------------------------------------------------


def test_a_library_structure_is_attached_to_a_plate_without_a_microproject(client):
    signup(client, "structure@example.com")
    create_records(client, ["W-STRUCT"])
    saved = client.get("/api/saved-structures").json()
    assert saved, "la bibliothèque a des structures intégrées"
    response = client.put("/api/wafers/W-STRUCT/structure", json={"kind": "saved", "source_id": saved[0]["id"]})
    assert response.status_code == 200, response.text
    attached = get_wafer(client, "w struct")["structure"]
    assert attached["kind"] == "saved" and attached["label"] == saved[0]["name"] and attached["svg"].startswith("<svg")
    assert client.delete("/api/wafers/W-STRUCT/structure").status_code == 204
    assert get_wafer(client, "W-STRUCT")["structure"] is None
    assert client.put("/api/wafers/W-STRUCT/structure", json={"kind": "saved", "source_id": "nope"}).status_code == 404


# --- runs d'épitaxie : les noms courants d'une plaque ----------------------------------------------


def test_the_most_recent_run_is_the_principal_and_every_run_is_kept():
    epitaxy = [{"run": "VA1801", "start": "2026-03-01 08:00"}, {"run": None, "start": "2025-01-01 08:00"}, {"run": "VA1725", "start": "2026-01-06 08:00"}, {"run": "VA1725", "start": "2026-01-06 08:00"}]
    assert tracking_model.plate_runs(epitaxy) == ["VA1801", "VA1725"]
    assert tracking_model.plate_runs([{"run": "M105_0819", "start": "2026-07-27 00:00"}]) == ["M105_0819"]  # un seul run : c'est lui


def test_a_plate_with_two_runs_is_found_by_either_and_its_run_page_leads_to_it(client, demo):
    signup(client, "runs@example.com")
    lm = _lasermark("waiting")  # la démo lui donne une reprise d'épi : deux runs
    record = create_records(client, [lm])["items"][0]
    principal, other = record["summary"]["runs"]  # la fiche les garde dès sa création, le plus récent d'abord
    assert principal == f"{other}R"  # la reprise d'épi, plus récente
    assert get_wafer(client, lm)["run_names"] == [principal, other]
    for name in (principal, other):
        found = list_wafers(client, q=name)
        assert [w["lasermark"] for w in found] == [lm] and found[0]["matched_alias"] == name
    fiche = get_tracking(client, lm).json()  # la vie en ligne les relit
    assert fiche["run_names"] == [principal, other]
    page = get_wafer(client, other)  # « /plaques/<run> » : ce n'est pas une plaque, c'est son run
    assert page["occurrences"] == [] and page["record"] is None
    assert page["run_of"] == [{"key": record["key"], "lasermark": lm, "principal": False}]
    assert get_wafer(client, principal)["run_of"][0]["principal"] is True


# --- son contexte : les études de ses µprojets, et ses notes -------------------------------------


def test_the_plate_page_tells_why_each_study_follows_it_to_members_only(client):
    from support.experiments import conclude, launch
    from support.microprojects import signup_with_microproject

    slug = signup_with_microproject(client, "ctx@example.com", "Contexte")
    study = launch(client, slug, title="Dopage", intent="Montrer l'effet du Mg", hypothesis="Plus de Mg, moins de Vf", context="Suite du run W40", entities=[{"sample_id": "W-CTX"}])
    conclude(client, slug, study["id"], decision="promote", summary="Le Mg baisse la Vf de 0,2 V", next_steps="Refaire sur 200 mm", objective_results=[])
    story = get_wafer(client, "W-CTX")["occurrences"][0]["experiment"]["story"]
    assert story["context"] == "Suite du run W40" and story["intent"] == "Montrer l'effet du Mg" and story["hypothesis"] == "Plus de Mg, moins de Vf"
    assert story["conclusion"]["summary"] == "Le Mg baisse la Vf de 0,2 V" and story["conclusion"]["decision"] == "promote" and story["conclusion"]["next_steps"] == "Refaire sur 200 mm"
    signup(client, "outsider@example.com")
    assert "story" not in get_wafer(client, "W-CTX")["occurrences"][0]["experiment"]  # pas membre : ni titre ni contexte


def test_notes_are_written_on_the_plate_page_and_erased_when_empty(client):
    signup(client, "notes@example.com")
    create_records(client, ["W-NOTE"])
    assert get_wafer(client, "W-NOTE")["notes"] is None
    saved = client.put("/api/wafers/w note/notes", json={"context": "Plaque témoin du lot QMDE10", "learnings": "  "})
    assert saved.status_code == 200, saved.text
    notes = get_wafer(client, "W-NOTE")["notes"]
    assert notes["context"] == "Plaque témoin du lot QMDE10" and notes["learnings"] is None and notes["updated_by"]
    client.put("/api/wafers/W-NOTE/notes", json={"hypothesis": "Le recuit long abîme le contact"})  # un champ seul : les autres restent
    assert get_wafer(client, "W-NOTE")["notes"]["context"] == "Plaque témoin du lot QMDE10"
    assert client.put("/api/wafers/W-NOTE/notes", json={"context": "", "hypothesis": None}).json() is None
    assert get_wafer(client, "W-NOTE")["notes"] is None


# --- recherche par lot ----------------------------------------------------------------------------


def test_a_lot_name_finds_its_plates(client):
    signup(client, "lotsearch@example.com")
    create_records(client, ["W-L1", "W-L2", "W-OTHER"])
    assert client.post("/api/lots", json={"code": "QT112", "wafers": ["W-L1", "W-L2"]}).status_code == 201
    found = list_wafers(client, q="qt 112")
    assert sorted(w["lasermark"] for w in found) == ["W-L1", "W-L2"]
    assert {w["matched_kind"] for w in found} == {"lot"} and found[0]["lots"] == ["QT112"]
