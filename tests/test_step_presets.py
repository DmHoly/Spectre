from __future__ import annotations


def _deposition_payload():
    return {"kind": "deposition", "mode": "conformal", "angle_deg": 0.0}


def _etch_payload():
    return {
        "kind": "etch",
        "mode": "isotropic",
        "angle_deg": 0.0,
        "selectivity_by_material": {"SiO2": 3.5},
        "selectivity_by_category": {},
        "default_factor": 1.0,
    }


def _register_and_project(client, email, project_name="Projet"):
    client.post("/api/auth/register", json={"email": email, "password": "supersecret", "name": "T"})
    return client.post("/api/projects", json={"name": project_name}).json()["slug"]


def test_create_a_project_scoped_deposition_preset(client):
    slug = _register_and_project(client, "presetA@example.com")

    created = client.post(
        f"/api/projects/{slug}/presets-etapes",
        json={"name": "Nitrure maison", "payload": _deposition_payload(), "notes": "recette perso", "partagee": False},
    )
    assert created.status_code == 201
    body = created.json()
    assert [p["name"] for p in body["projet"]] == ["Nitrure maison"]
    assert body["partagees"] == []


def test_create_an_etch_preset_with_selectivity(client):
    slug = _register_and_project(client, "presetB@example.com")

    created = client.post(
        f"/api/projects/{slug}/presets-etapes",
        json={"name": "Gravure selective", "payload": _etch_payload(), "partagee": False},
    )
    assert created.status_code == 201
    preset = next(p for p in created.json()["projet"] if p["name"] == "Gravure selective")
    assert preset["payload"]["selectivity_by_material"]["SiO2"] == 3.5


def test_shared_preset_is_visible_from_a_different_project(client):
    slug_a = _register_and_project(client, "presetC@example.com")
    client.post(
        f"/api/projects/{slug_a}/presets-etapes",
        json={"name": "Base commune", "payload": _deposition_payload(), "partagee": True},
    )

    slug_b = client.post("/api/projects", json={"name": "Autre projet"}).json()["slug"]
    listed = client.get(f"/api/projects/{slug_b}/presets-etapes").json()
    assert [p["name"] for p in listed["partagees"]] == ["Base commune"]
    assert listed["projet"] == []


def test_duplicate_name_in_the_same_library_is_rejected(client):
    slug = _register_and_project(client, "presetD@example.com")
    payload = {"name": "Preset X", "payload": _deposition_payload(), "partagee": False}
    first = client.post(f"/api/projects/{slug}/presets-etapes", json=payload)
    assert first.status_code == 201
    again = client.post(f"/api/projects/{slug}/presets-etapes", json=payload)
    assert again.status_code == 409


def test_rename_a_preset_in_place(client):
    slug = _register_and_project(client, "presetE@example.com")
    client.post(
        f"/api/projects/{slug}/presets-etapes",
        json={"name": "Nom initial", "payload": _deposition_payload(), "partagee": False},
    )
    renamed = client.put(
        f"/api/projects/{slug}/presets-etapes/Nom initial",
        params={"partagee": False},
        json={"name": "Nom corrige", "payload": _deposition_payload()},
    )
    assert renamed.status_code == 200
    assert [p["name"] for p in renamed.json()["projet"]] == ["Nom corrige"]


def test_delete_a_preset(client):
    slug = _register_and_project(client, "presetF@example.com")
    client.post(
        f"/api/projects/{slug}/presets-etapes",
        json={"name": "A retirer", "payload": _deposition_payload(), "partagee": False},
    )
    deleted = client.delete(f"/api/projects/{slug}/presets-etapes/A retirer", params={"partagee": False})
    assert deleted.status_code == 200
    assert deleted.json()["projet"] == []


def test_builtin_presets_are_listed_and_usable_in_a_step(client):
    slug = _register_and_project(client, "presetG@example.com")

    listed = client.get(f"/api/projects/{slug}/presets-etapes").json()
    presets = listed["presets"]
    assert any(p["name"] == "MOCVD Epitaxial" for p in presets)
    assert any(p["name"] == "Cl2 ICP-RIE (III-N)" for p in presets)
    mocvd = next(p for p in presets if p["name"] == "MOCVD Epitaxial")
    assert mocvd["scope"] == "preset"
    assert mocvd["payload"]["mode"] == "conformal"

    # a preset only pre-fills a step's own fields - it's never referenced by name at simulate time
    sim = client.post(
        f"/api/projects/{slug}/structures/simulate",
        json={
            "substrate": {"material": "Si", "domain_width": {"value": 200, "unit": "nm"}, "thickness": {"value": 50, "unit": "nm"}},
            "steps": [
                {
                    "kind": "deposition",
                    "name": "GaN",
                    "material": "GaN",
                    "mode": mocvd["payload"]["mode"],
                    "angle_deg": mocvd["payload"]["angle_deg"],
                    "thickness": {"value": 10, "unit": "nm"},
                }
            ],
        },
    )
    assert sim.status_code == 200


def test_viewer_cannot_create_a_preset(client):
    slug = _register_and_project(client, "presetH-owner@example.com")
    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={"email": "presetH-viewer@example.com", "password": "supersecret", "name": "V"})
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "presetH-owner@example.com", "password": "supersecret"})
    client.post(f"/api/projects/{slug}/members", json={"email": "presetH-viewer@example.com", "role": "viewer"})

    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "presetH-viewer@example.com", "password": "supersecret"})
    denied = client.post(
        f"/api/projects/{slug}/presets-etapes",
        json={"name": "Interdit", "payload": _deposition_payload(), "partagee": False},
    )
    assert denied.status_code == 403
