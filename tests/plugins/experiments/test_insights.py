"""Les lectures transverses des expériences : GET /api/experiment-stats (les compteurs de chaque
µprojet) et GET /api/experiment-timeline (la frise d'une thématique, masquée pour les non-membres)."""

from __future__ import annotations

import pytest

from support.accounts import signup
from support.areas import create_thematic
from support.experiments import conclude, experiment_stats, experiment_timeline, launch, set_status
from support.http import assert_handler_404
from support.microprojects import create_microproject


@pytest.fixture()
def loads(monkeypatch):
    """Les dépôts Follow chargés par les lectures transverses, dans l'ordre (un slug par chargement)."""
    from spectre.plugins.experiments import insights

    loaded: list[str] = []
    real = insights.get_repository

    def counting(slug):
        loaded.append(slug)
        return real(slug)

    monkeypatch.setattr(insights, "get_repository", counting)
    return loaded


def test_stats_count_each_line_of_study_and_each_wafer_once(client, loads):
    signup(client, "boss@example.com")
    create_microproject(client, "Recuit Mg", management_area_slug="native-pt2")
    create_microproject(client, "Ailleurs", management_area_slug="nova-pt1")
    running = launch(client, "recuit-mg", title="En cours", entities=[{"sample_id": "W12-A3"}, {"sample_id": "W1"}])
    done = launch(client, "recuit-mg", title="Conclue", entities=[{"sample_id": "w12 a3"}])
    dropped = launch(client, "recuit-mg", title="Abandonnée", entities=[{"sample_id": "W2"}])
    conclude(client, "recuit-mg", done["id"], decision="promote", summary="ok")
    conclude(client, "recuit-mg", dropped["id"], status="abandoned", summary="non")
    assert running["id"]

    loads.clear()
    rows = experiment_stats(client, area="native-pt2")
    assert [(r["microproject"]["slug"], r["running"], r["concluded"], r["abandoned"], r["wafers"]) for r in rows] == [
        ("recuit-mg", 1, 1, 1, 3)  # W12-A3 suivi par deux études : un seul wafer
    ]
    assert loads == ["recuit-mg"]  # chaque dépôt, une fois par requête

    row = rows[0]["microproject"]
    assert (row["code"], row["name"], row["role"]) == ("Nat_0001", "Recuit Mg", "owner")
    assert row["area"] == {"slug": "native-pt2", "name": "Native (PT2)"} and row["thematic"] is None
    assert row["created_at"].endswith("Z")

    loads.clear()
    every = experiment_stats(client)
    assert {r["microproject"]["slug"] for r in every} == {"recuit-mg", "ailleurs"}
    assert sorted(loads) == ["ailleurs", "recuit-mg"]
    assert [r["microproject"]["slug"] for r in experiment_stats(client, microproject="ailleurs")] == ["ailleurs"]
    assert experiment_stats(client, microproject="ailleurs", area="native-pt2") == []

    assert_handler_404(client.get("/api/experiment-stats?area=inconnu"), "inconnu")
    assert_handler_404(client.get("/api/experiment-stats?microproject=inconnu"), "inconnu")


def test_stats_are_visible_to_any_signed_in_user(client):
    signup(client, "boss@example.com")
    create_microproject(client, "Recuit Mg", management_area_slug="native-pt2")
    launch(client, "recuit-mg", title="Essai")

    signup(client, "hand@example.com")
    [row] = experiment_stats(client, area="native-pt2")
    assert row["running"] == 1 and row["microproject"]["role"] is None
    assert row["microproject"]["owners"][0]["id"] == 1


def test_thematique_frise_lists_its_microprojets_and_redacts_them_for_outsiders(client, loads):
    signup(client, "boss@example.com", name="Alice Martin")
    create_thematic(client, "native-pt2", "Dopage PGaN", description="Mg")
    create_thematic(client, "native-pt2", "Double EBL")
    create_microproject(client, "Recuit Mg", management_area_slug="native-pt2", thematique_slug="dopage-pgan")
    create_microproject(client, "Ailleurs", management_area_slug="native-pt2", thematique_slug="double-ebl")
    launched = launch(client, "recuit-mg", title="Recuit 700 C")
    paused = launch(client, "recuit-mg", title="En pause")
    set_status(client, "recuit-mg", paused["id"], "hold", hold_reason="four en panne")

    loads.clear()
    rows = experiment_timeline(client, area="native-pt2", thematic="dopage-pgan")
    assert loads == ["recuit-mg"]
    assert [r["microproject"]["slug"] for r in rows] == ["recuit-mg"]
    row = rows[0]
    assert row["microproject"]["owners"][0]["name"] == "Alice Martin" and row["microproject"]["created_at"].endswith("Z")
    by_title = {n["title"]: n for n in row["nodes"]}
    node = by_title["Recuit 700 C"]
    assert (node["experiment_id"], node["version_id"], node["status"], node["ended_at"], node["is_tip"]) == (
        launched["id"],
        launched["version_id"],
        "draft",
        None,
        True,
    )
    assert by_title["En pause"]["status"] == "hold" and by_title["En pause"]["hold"]["reason"] == "four en panne"
    assert [r["microproject"]["slug"] for r in experiment_timeline(client, area="native-pt2")] == ["recuit-mg", "ailleurs"]

    # Someone outside the µprojet sees its counts and dates, not what its experiments are.
    signup(client, "hand@example.com")
    nodes = experiment_timeline(client, area="native-pt2", thematic="dopage-pgan")[0]["nodes"]
    assert all("title" not in n and "id" not in n and "experiment_id" not in n and "version_id" not in n for n in nodes)
    assert sorted(n["status"] for n in nodes) == ["draft", "hold"]
    hold = next(n["hold"] for n in nodes if n["status"] == "hold")
    assert hold["since"] and "reason" not in hold
    assert all("wafers" not in n and "lots" not in n and "author" not in n for n in nodes)

    assert_handler_404(client.get("/api/experiment-timeline?area=native-pt2&thematic=inconnue"), "inconnue")
    assert_handler_404(client.get("/api/experiment-timeline?area=inconnu"))
    assert client.get("/api/experiment-timeline").status_code == 422  # le projet est obligatoire


def test_redact_for_viewer_keeps_dates_and_outcome_only():
    from spectre.plugins.experiments.insights import redact_for_viewer

    node = {
        "id": "exp_1",
        "title": "Secret",
        "author": "a@b",
        "started_at": "2026-01-01T00:00:00",
        "ended_at": None,
        "continued_at": None,
        "status": "hold",
        "decision": None,
        "is_merge": False,
        "is_tip": True,
        "hold": {"since": "2026-02-01", "reason": "panne"},
        "wafers": ["W1"],
    }
    outsider = redact_for_viewer(node, member=False)
    assert outsider == {
        "started_at": "2026-01-01T00:00:00",
        "ended_at": None,
        "continued_at": None,
        "status": "hold",
        "decision": None,
        "is_merge": False,
        "is_tip": True,
        "hold": {"since": "2026-02-01"},
    }
    member = redact_for_viewer(node, member=True)
    assert member["id"] == "exp_1" and member["title"] == "Secret" and member["hold"]["reason"] == "panne"
    assert "author" not in member and "wafers" not in member
