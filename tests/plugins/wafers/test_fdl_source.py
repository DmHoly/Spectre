"""Les plaques d'une FDL (spectre.plugins.wafers.fdl_source) : lues dans la source courante - PRISM
(le hook ``fdl_wafers``), la base locale saisie à la main en repli (et seule source sous
``SPECTRE_FDL_SOURCE=local``, ce que pose la fixture des tests), ou la démo (``SPECTRE_DEMO_DATA=1``)
- pour associer chaque place d'une étude à une vraie plaque. PRISM n'est jamais appelé : ``_run``
est remplacé."""

from __future__ import annotations

import pandas as pd
import pytest

from spectre.kernel.errors import Unavailable, UpstreamError
from spectre.plugins.wafers import fdl_source
from spectre.plugins.wafers.fdl_source import FdlWafer, PrismSource
from support.accounts import signup
from support.wafers import get_fdl, put_fdl_wafers


def test_an_unknown_fdl_is_editable_in_the_local_base(client):
    signup(client, "fdl-local@example.com")
    fdl = get_fdl(client, "1234")
    assert fdl == {"fdl": "FDL-1234", "source": "local", "editable": True, "known": False, "wafers": []}


def test_the_wafers_of_an_fdl_are_entered_by_hand_once_each_in_order(client):
    signup(client, "fdl-write@example.com")
    response = put_fdl_wafers(client, "fdl 77", ["W3", " w-3 ", "W1", "", "W2"])
    assert response.status_code == 200
    assert response.json()["known"] is True
    assert response.json()["wafers"] == [{"lasermark": "W3", "slot": 1}, {"lasermark": "W1", "slot": 2}, {"lasermark": "W2", "slot": 3}]
    assert get_fdl(client, "FDL-77")["wafers"][0]["lasermark"] == "W3"
    # une nouvelle saisie remplace la précédente ; vide, la FDL redevient inconnue
    assert [w["lasermark"] for w in put_fdl_wafers(client, "77", ["W9"]).json()["wafers"]] == ["W9"]
    assert put_fdl_wafers(client, "77", []).json()["known"] is False


def test_the_demo_source_invents_the_same_wafers_for_the_same_fdl_and_is_read_only(client, monkeypatch):
    signup(client, "fdl-demo@example.com")
    monkeypatch.setenv("SPECTRE_DEMO_DATA", "1")
    first = get_fdl(client, "FDL-42")
    assert first["source"] == "demo" and first["known"] and not first["editable"]
    assert 4 <= len(first["wafers"]) <= 12
    assert all(w["lasermark"].startswith("D42-W") for w in first["wafers"])
    assert get_fdl(client, "42") == first
    assert get_fdl(client, "ABC-3")["known"] is False
    refused = put_fdl_wafers(client, "42", ["W1"])
    assert refused.status_code == 409 and refused.json()["code"] == "fdl_source_read_only"


# --- PRISM -----------------------------------------------------------------------------------------


@pytest.fixture
def prism(monkeypatch):
    """La source PRISM, répondant au hook ``fdl_wafers`` par ``rows`` (sans base) ; rend la liste
    des appels (hook, params)."""
    monkeypatch.setenv("SPECTRE_FDL_SOURCE", "prism")
    calls: list[tuple[str, dict]] = []

    def answer(rows=(), error=None):
        def run(hook, params):
            calls.append((hook, params))
            if error:
                raise error
            return pd.DataFrame(list(rows), columns=["Request_Number", "PK_FDL", "wafer", "rank"])

        monkeypatch.setattr(PrismSource, "_run", staticmethod(run))
        return calls

    return answer


def test_the_prism_source_reads_the_fdl_wafers_hook_in_rank_order_once_each(prism):
    calls = prism(
        [
            ("FDL-4821", 1, "16J5A427MMD4", 2),
            ("FDL-4821", 1, "16J5A426MMD4", 1),
            ("FDL-4821", 1, "16j5a426mmd4", 3),  # la même plaque citée deux fois
            ("FDL-9", 2, "OTHER", 1),  # une autre FDL rendue par la même requête : ignorée
        ]
    )
    assert PrismSource().wafers("FDL-4821") == [FdlWafer("16J5A426MMD4", 1), FdlWafer("16J5A427MMD4", 2)]
    assert calls == [("fdl_wafers", {"fdl_numbers": ["FDL-4821"]})]
    assert PrismSource().wafers("FDL-77") is None


def test_a_study_reads_the_real_wafers_of_a_known_fdl_and_cannot_enter_them_by_hand(client, prism):
    signup(client, "fdl-prism@example.com")
    prism([("FDL-4821", 1, "16J5A426MMD4", 1), ("FDL-4821", 1, "16J5A427MMD4", 2)])
    sheet = get_fdl(client, "4821")
    assert sheet == {
        "fdl": "FDL-4821",
        "source": "prism",
        "editable": False,
        "known": True,
        "wafers": [{"lasermark": "16J5A426MMD4", "slot": 1}, {"lasermark": "16J5A427MMD4", "slot": 2}],
    }
    refused = put_fdl_wafers(client, "4821", ["W1"])
    assert refused.status_code == 409 and refused.json()["code"] == "fdl_source_read_only"


def test_an_fdl_unknown_to_gozer_falls_back_to_the_local_base_which_stays_editable(client, prism):
    signup(client, "fdl-fallback@example.com")
    prism([])
    assert get_fdl(client, "FDL-5")["source"] == "local"
    assert get_fdl(client, "FDL-5")["known"] is False
    saved = put_fdl_wafers(client, "5", ["W1", "W2"]).json()
    assert saved["source"] == "local" and saved["editable"] and [w["lasermark"] for w in saved["wafers"]] == ["W1", "W2"]
    assert get_fdl(client, "FDL-5")["wafers"] == saved["wafers"]


def test_prism_errors_are_told_and_do_not_fall_back_to_the_local_base(client, prism):
    import prism as prism_pkg

    signup(client, "fdl-errors@example.com")
    prism(error=prism_pkg.ConfigError("pas de connections.yml"))
    with pytest.raises(Unavailable):
        fdl_source.read("FDL-1")
    assert client.get("/api/fdls/FDL-1").status_code == 503
    prism(error=prism_pkg.QueryFailed("relation FDL does not exist"))
    with pytest.raises(UpstreamError):
        fdl_source.read("FDL-1")
    assert client.get("/api/fdls/FDL-1").status_code == 502


def test_the_demo_wins_over_prism(client, prism, monkeypatch):
    signup(client, "fdl-demo-prism@example.com")
    calls = prism([("FDL-42", 1, "REAL", 1)])
    monkeypatch.setenv("SPECTRE_DEMO_DATA", "1")
    assert get_fdl(client, "42")["source"] == "demo"
    assert calls == []
