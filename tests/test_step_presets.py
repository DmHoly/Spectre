from __future__ import annotations

from support.microprojects import create_microproject, join_as, signup_with_microproject
from support.structures import deposition, substrate


def _deposition_payload():
    return {"kind": "deposition", "recipe": "CVD Conformal"}


def _etch_payload():
    return {"kind": "etch", "recipe": "Dry Oxide Etch"}


def test_create_a_microproject_scoped_deposition_preset(client):
    slug = signup_with_microproject(client, "presetA@example.com")

    created = client.post(
        f"/api/microprojets/{slug}/presets-etapes",
        json={"name": "Nitrure maison", "payload": _deposition_payload(), "notes": "recette perso", "partagee": False},
    )
    assert created.status_code == 201
    body = created.json()
    assert [p["name"] for p in body["microprojet"]] == ["Nitrure maison"]
    assert body["partagees"] == []


def test_create_an_etch_preset(client):
    slug = signup_with_microproject(client, "presetB@example.com")

    created = client.post(
        f"/api/microprojets/{slug}/presets-etapes",
        json={"name": "Gravure selective", "payload": _etch_payload(), "partagee": False},
    )
    assert created.status_code == 201
    preset = next(p for p in created.json()["microprojet"] if p["name"] == "Gravure selective")
    assert preset["payload"]["recipe"] == "Dry Oxide Etch"


def test_shared_preset_is_visible_from_a_different_microproject(client):
    slug_a = signup_with_microproject(client, "presetC@example.com")
    client.post(
        f"/api/microprojets/{slug_a}/presets-etapes",
        json={"name": "Base commune", "payload": _deposition_payload(), "partagee": True},
    )

    slug_b = create_microproject(client, "Autre projet")["slug"]
    listed = client.get(f"/api/microprojets/{slug_b}/presets-etapes").json()
    assert [p["name"] for p in listed["partagees"]] == ["Base commune"]
    assert listed["microprojet"] == []


def test_duplicate_name_in_the_same_library_is_rejected(client):
    slug = signup_with_microproject(client, "presetD@example.com")
    payload = {"name": "Preset X", "payload": _deposition_payload(), "partagee": False}
    first = client.post(f"/api/microprojets/{slug}/presets-etapes", json=payload)
    assert first.status_code == 201
    again = client.post(f"/api/microprojets/{slug}/presets-etapes", json=payload)
    assert again.status_code == 409


def test_rename_a_preset_in_place(client):
    slug = signup_with_microproject(client, "presetE@example.com")
    client.post(
        f"/api/microprojets/{slug}/presets-etapes",
        json={"name": "Nom initial", "payload": _deposition_payload(), "partagee": False},
    )
    renamed = client.put(
        f"/api/microprojets/{slug}/presets-etapes/Nom initial",
        params={"partagee": False},
        json={"name": "Nom corrige", "payload": _deposition_payload()},
    )
    assert renamed.status_code == 200
    assert [p["name"] for p in renamed.json()["microprojet"]] == ["Nom corrige"]


def test_delete_a_preset(client):
    slug = signup_with_microproject(client, "presetF@example.com")
    client.post(
        f"/api/microprojets/{slug}/presets-etapes",
        json={"name": "A retirer", "payload": _deposition_payload(), "partagee": False},
    )
    deleted = client.delete(f"/api/microprojets/{slug}/presets-etapes/A retirer", params={"partagee": False})
    assert deleted.status_code == 200
    assert deleted.json()["microprojet"] == []


def test_builtin_presets_are_listed_and_usable_in_a_step(client):
    slug = signup_with_microproject(client, "presetG@example.com")

    listed = client.get(f"/api/microprojets/{slug}/presets-etapes").json()
    presets = listed["presets"]
    assert any(p["name"] == "MOCVD Epitaxial" for p in presets)
    assert any(p["name"] == "Cl2 ICP-RIE (III-N)" for p in presets)
    mocvd = next(p for p in presets if p["name"] == "MOCVD Epitaxial")
    assert mocvd["scope"] == "preset"
    assert mocvd["payload"]["recipe"] == "MOCVD Epitaxial"

    # a preset only pre-fills a step's own fields - it's never referenced by name at simulate time
    sim = client.post(
        f"/api/microprojets/{slug}/structures/simulate",
        json={"substrate": substrate(), "steps": [deposition("GaN", "GaN", recipe=mocvd["payload"]["recipe"], thickness_nm=10)]},
    )
    assert sim.status_code == 200


def test_viewer_cannot_create_a_preset(client):
    slug = signup_with_microproject(client, "presetH-owner@example.com")
    join_as(client, slug, "presetH-viewer@example.com", owner="presetH-owner@example.com", role="viewer")
    denied = client.post(
        f"/api/microprojets/{slug}/presets-etapes",
        json={"name": "Interdit", "payload": _deposition_payload(), "partagee": False},
    )
    assert denied.status_code == 403
