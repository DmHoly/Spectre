"""La recherche de la barre du haut (``GET /api/search``) : une requête, les fournisseurs de chaque
plugin (µprojets, lots, plaques, FDL), et l'adresse de chaque résultat donnée par le serveur."""

from __future__ import annotations

from support.accounts import signup
from support.experiments import launch
from support.lots import create_lot
from support.microprojects import create_microproject, signup_with_microproject
from support.search import search


def test_one_query_finds_microprojects_lots_wafers_and_fdls(client):
    signup(client, "boss@example.com", name="Alice")
    create_microproject(client, "Recuit Mg", area="native-pt2")
    launched = launch(client, "recuit-mg", title="Recuit 700 C", entities=[{"sample_id": "W12-A3", "fdl": ["FDL-1201"]}])
    create_lot(client, "L-W12", title="Run EBL", priority="P10", wafers=["W12-A3"])

    assert search(client, "nat 1") == [
        {"type": "microproject", "label": "Nat_0001", "detail": "Recuit Mg", "badge": "Native (PT2)", "url": "/microprojets/recuit-mg"}
    ]
    hits = search(client, "w12")
    assert [(h["type"], h["label"]) for h in hits] == [("lot", "L-W12"), ("wafer", "W12-A3")]
    assert hits[0] == {"type": "lot", "label": "L-W12", "detail": "Run EBL", "badge": "P10 · en préparation", "url": "/lots/L-W12"}
    assert hits[1] == {"type": "wafer", "label": "W12-A3", "detail": "Recuit 700 C", "badge": "Nat_0001", "url": "/plaques/W12-A3"}
    assert [(h["type"], h["detail"]) for h in search(client, "w12a3")] == [("lot", "contient W12-A3"), ("wafer", "Recuit 700 C")]

    # « 1201 » : une FDL d'abord, qui ouvre l'étude dont une plaque la porte
    fdl = search(client, "1201")[0]
    assert fdl == {
        "type": "fdl",
        "label": "FDL-1201",
        "detail": "Recuit 700 C · W12-A3",
        "badge": "Nat_0001",
        "url": f"/microprojets/recuit-mg/experiences/{launched['id']}",
    }


def test_types_narrow_the_search(client):
    signup(client, "boss@example.com", name="Alice")
    create_microproject(client, "W12 analyse")
    create_lot(client, "W12-LOT")
    assert {h["type"] for h in search(client, "w12")} == {"microproject", "lot"}
    assert {h["type"] for h in search(client, "w12", types="lot")} == {"lot"}
    assert search(client, "w12", types="wafer,fdl") == []
    refused = client.get("/api/search", params={"q": "w12", "types": "lot,plate"})
    assert refused.status_code == 422 and "plate" in refused.json()["detail"]
    assert search(client, "   ") == []


def test_a_study_of_someone_elses_microproject_is_not_found_by_its_fdl(client):
    slug = signup_with_microproject(client, "owner@example.com", "Secret")
    launch(client, slug, title="Confidentiel", entities=[{"sample_id": "W-PRIV", "fdl": ["FDL-77"]}])
    assert [h["type"] for h in search(client, "77")] == ["fdl"]

    signup(client, "stranger@example.com")
    assert search(client, "77") == []
    (wafer,) = search(client, "w-priv")  # the wafer, not what follows it
    assert wafer["detail"] == "" and wafer["url"] == "/plaques/W-PRIV"


def test_a_registered_provider_is_searched(client, monkeypatch):
    from spectre.plugins.search import service

    monkeypatch.setattr(service, "_PROVIDERS", dict(service._PROVIDERS))
    service.register_provider(
        service.SearchProvider(type="doc", search=lambda q, user: [service.SearchHit(label=q.upper(), url="/docs")], order=1)
    )
    signup(client, "reader@example.com")
    assert search(client, "guide", types="doc") == [{"type": "doc", "label": "GUIDE", "detail": "", "badge": "", "url": "/docs"}]
    assert search(client, "guide")[0]["type"] == "doc"  # its order comes first
