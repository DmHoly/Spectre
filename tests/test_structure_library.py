from __future__ import annotations

from support.microprojects import create_microproject, join_as, signup_with_microproject
from support.structures import deposition, substrate


PGAN_STEPS = [deposition("PGaN", "GaN", thickness_nm=50)]


def test_create_a_microproject_scoped_structure(client):
    slug = signup_with_microproject(client, "libA@example.com")

    created = client.post(
        f"/api/microprojets/{slug}/structures-sauvegardees",
        json={"name": "Epitaxie PGaN", "substrate": substrate(), "steps": PGAN_STEPS, "partagee": False},
    )
    assert created.status_code == 201
    body = created.json()
    assert [s["name"] for s in body["microprojet"]] == ["Epitaxie PGaN"]
    assert body["partagees"] == []


def test_shared_structure_is_visible_from_a_different_microproject(client):
    slug_a = signup_with_microproject(client, "libB@example.com")
    client.post(
        f"/api/microprojets/{slug_a}/structures-sauvegardees",
        json={"name": "Base commune", "substrate": substrate(), "steps": PGAN_STEPS, "partagee": True},
    )

    slug_b = create_microproject(client, "Autre projet")["slug"]
    listed = client.get(f"/api/microprojets/{slug_b}/structures-sauvegardees").json()
    assert [s["name"] for s in listed["partagees"]] == ["Base commune"]
    assert listed["microprojet"] == []


def test_derive_a_structure_keeps_a_derived_from_link(client):
    slug = signup_with_microproject(client, "libC@example.com")
    client.post(
        f"/api/microprojets/{slug}/structures-sauvegardees",
        json={"name": "Epitaxie", "substrate": substrate(), "steps": PGAN_STEPS, "partagee": False},
    )

    derived_steps = PGAN_STEPS + [
        {"kind": "deposition", "name": "Contact", "material": "Au", "recipe": "Evaporation (normal)", "thickness": {"value": 80, "unit": "nm"}}
    ]
    derived = client.post(
        f"/api/microprojets/{slug}/structures-sauvegardees",
        json={
            "name": "Epitaxie + contact",
            "substrate": substrate(),
            "steps": derived_steps,
            "derived_from": "Epitaxie",
            "partagee": False,
        },
    )
    assert derived.status_code == 201
    saved = next(s for s in derived.json()["microprojet"] if s["name"] == "Epitaxie + contact")
    assert saved["derived_from"] == "Epitaxie"
    assert len(saved["steps"]) == 2


def test_duplicate_name_in_the_same_library_is_rejected(client):
    slug = signup_with_microproject(client, "libD@example.com")
    payload = {"name": "Structure X", "substrate": substrate(), "steps": PGAN_STEPS, "partagee": False}
    first = client.post(f"/api/microprojets/{slug}/structures-sauvegardees", json=payload)
    assert first.status_code == 201
    again = client.post(f"/api/microprojets/{slug}/structures-sauvegardees", json=payload)
    assert again.status_code == 409


def test_rename_a_saved_structure_in_place(client):
    slug = signup_with_microproject(client, "libE@example.com")
    client.post(
        f"/api/microprojets/{slug}/structures-sauvegardees",
        json={"name": "Nom initial", "substrate": substrate(), "steps": PGAN_STEPS, "partagee": False},
    )
    renamed = client.put(
        f"/api/microprojets/{slug}/structures-sauvegardees/Nom initial",
        params={"partagee": False},
        json={"name": "Nom corrige", "substrate": substrate(), "steps": PGAN_STEPS},
    )
    assert renamed.status_code == 200
    names = [s["name"] for s in renamed.json()["microprojet"]]
    assert names == ["Nom corrige"]


def test_delete_a_saved_structure(client):
    slug = signup_with_microproject(client, "libF@example.com")
    client.post(
        f"/api/microprojets/{slug}/structures-sauvegardees",
        json={"name": "A retirer", "substrate": substrate(), "steps": PGAN_STEPS, "partagee": False},
    )
    deleted = client.delete(f"/api/microprojets/{slug}/structures-sauvegardees/A retirer", params={"partagee": False})
    assert deleted.status_code == 200
    assert deleted.json()["microprojet"] == []


def test_builtin_presets_are_listed_and_can_be_duplicated_into_a_real_structure(client):
    slug = signup_with_microproject(client, "libH@example.com")

    listed = client.get(f"/api/microprojets/{slug}/structures-sauvegardees").json()
    presets = listed["presets"]
    assert any(s["name"] == "Nanofil pointe semipolaire (V-pit inversé)" for s in presets)
    preset = next(s for s in presets if s["name"] == "Nanofil pointe semipolaire (V-pit inversé)")
    assert preset["scope"] == "preset"
    assert any(step["kind"] == "faceted_growth" for step in preset["steps"])

    # duplicating a preset creates a real, editable structure (presets themselves aren't stored)
    derived = client.post(
        f"/api/microprojets/{slug}/structures-sauvegardees",
        json={
            "name": "Mon nanofil",
            "substrate": preset["substrate"],
            "steps": preset["steps"],
            "derived_from": preset["name"],
            "partagee": False,
        },
    )
    assert derived.status_code == 201
    saved = next(s for s in derived.json()["microprojet"] if s["name"] == "Mon nanofil")
    assert saved["derived_from"] == "Nanofil pointe semipolaire (V-pit inversé)"


def test_viewer_cannot_create_a_saved_structure(client):
    slug = signup_with_microproject(client, "libG-owner@example.com")
    join_as(client, slug, "libG-viewer@example.com", owner="libG-owner@example.com", role="viewer")
    denied = client.post(
        f"/api/microprojets/{slug}/structures-sauvegardees",
        json={"name": "Interdit", "substrate": substrate(), "steps": PGAN_STEPS, "partagee": False},
    )
    assert denied.status_code == 403


def test_a_saved_structure_keeps_its_declared_parameters(client):
    slug = signup_with_microproject(client, "libDeclared@example.com")
    declared = {"0": [{"name": "dopage", "value": 1e19, "obtention": {"precurseur": "Cp2Mg"}}]}
    body = client.post(
        f"/api/microprojets/{slug}/structures-sauvegardees",
        json={"name": "PGaN dope", "substrate": substrate(), "steps": PGAN_STEPS, "declared_params": declared},
    ).json()
    assert body["microprojet"][0]["declared_params"] == declared
