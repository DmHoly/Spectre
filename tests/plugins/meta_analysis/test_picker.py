"""GET /api/analyses/wafer-search : choisir les plaques d'une analyse sans connaître leur lasermark - comme dans la
barre du haut, par lasermark, lot, µprojet ou FDL ; chaque réponse est un groupe de plaques."""

from __future__ import annotations

from support.experiments import launch
from support.http import assert_ok
from support.lots import create_lot
from support.microprojects import create_microproject, signup_with_microproject


def groups(client, q: str) -> list[dict]:
    return assert_ok(client.get("/api/analyses/wafer-search", params={"q": q}))["groups"]


def lasermarks(group: dict) -> list[str]:
    return sorted(w["lasermark"] for w in group["wafers"])


def test_wafers_by_lasermark_lot_microproject_and_fdl(client):
    slug = signup_with_microproject(client, "picker@example.com", "Recuit rapide")
    launch(client, slug, title="Essai recuit", intent="x", entities=[{"sample_id": "W12-A3", "fdl": ["FDL-1201"]}, {"sample_id": "W12-A4"}])
    other = create_microproject(client, "Autre sujet")["slug"]
    launch(client, other, title="Essai", intent="x", entities=[{"sample_id": "Q7"}])
    create_lot(client, "QMDE10", wafers=["W12-A3", "Q7"])

    by_name = groups(client, "w12")
    assert by_name[0]["kind"] == "wafer" and lasermarks(by_name[0]) == ["W12-A3", "W12-A4"]
    first = next(w for w in by_name[0]["wafers"] if w["lasermark"] == "W12-A4")
    assert first["key"] == "W12A4" and "Essai recuit" in first["detail"]

    (lot,) = [g for g in groups(client, "QMDE10") if g["kind"] == "lot"]
    assert lot["label"] == "QMDE10" and lasermarks(lot) == ["Q7", "W12-A3"] and lot["total"] == 2

    (microproject,) = [g for g in groups(client, "recuit rap") if g["kind"] == "microproject"]
    assert microproject["detail"] == "Recuit rapide" or microproject["label"] == "Recuit rapide"
    assert lasermarks(microproject) == ["W12-A3", "W12-A4"]

    (fdl,) = [g for g in groups(client, "1201") if g["kind"] == "fdl"]
    assert fdl["label"] == "FDL 1201" and lasermarks(fdl) == ["W12-A3"]


def test_too_short_a_query_finds_nothing(client):
    signup_with_microproject(client, "picker-court@example.com")
    assert groups(client, "w") == [] and groups(client, "  ") == []


def test_many_matching_lots_make_one_group_whose_wafers_say_their_lot(client):
    slug = signup_with_microproject(client, "picker-lots@example.com")
    launch(client, slug, title="Essai", intent="x", entities=[{"sample_id": f"W{i}"} for i in range(5)])
    for i in range(5):
        create_lot(client, f"QX{i}0", wafers=[f"W{i}"])

    few = [g for g in groups(client, "QX10") if g["kind"] == "lot"]
    assert [g["label"] for g in few] == ["QX10"]
    (many,) = [g for g in groups(client, "QX") if g["kind"] == "lot"]
    assert many["label"] == "QX…" and many["total"] == 5
    assert sorted(w["detail"].split(" · ")[0] for w in many["wafers"]) == [f"lot QX{i}0" for i in range(5)]
