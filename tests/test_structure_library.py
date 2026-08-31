from __future__ import annotations


def _substrate():
    return {"material": "Si", "domain_width": {"value": 200, "unit": "nm"}, "thickness": {"value": 50, "unit": "nm"}}


def _steps():
    return [
        {
            "kind": "deposition",
            "name": "PGaN",
            "material": "GaN",
            "recipe": "MOCVD Epitaxial",
            "thickness": {"value": 50, "unit": "nm"},
        }
    ]


def _register_and_project(client, email, project_name="Projet"):
    client.post("/api/auth/register", json={"email": email, "password": "supersecret", "name": "T"})
    return client.post("/api/projects", json={"name": project_name}).json()["slug"]


def test_create_a_project_scoped_structure(client):
    slug = _register_and_project(client, "libA@example.com")

    created = client.post(
        f"/api/projects/{slug}/structures-sauvegardees",
        json={"name": "Epitaxie PGaN", "substrate": _substrate(), "steps": _steps(), "partagee": False},
    )
    assert created.status_code == 201
    body = created.json()
    assert [s["name"] for s in body["projet"]] == ["Epitaxie PGaN"]
    assert body["partagees"] == []


def test_shared_structure_is_visible_from_a_different_project(client):
    slug_a = _register_and_project(client, "libB@example.com")
    client.post(
        f"/api/projects/{slug_a}/structures-sauvegardees",
        json={"name": "Base commune", "substrate": _substrate(), "steps": _steps(), "partagee": True},
    )

    slug_b = client.post("/api/projects", json={"name": "Autre projet"}).json()["slug"]
    listed = client.get(f"/api/projects/{slug_b}/structures-sauvegardees").json()
    assert [s["name"] for s in listed["partagees"]] == ["Base commune"]
    assert listed["projet"] == []


def test_derive_a_structure_keeps_a_derived_from_link(client):
    slug = _register_and_project(client, "libC@example.com")
    client.post(
        f"/api/projects/{slug}/structures-sauvegardees",
        json={"name": "Epitaxie", "substrate": _substrate(), "steps": _steps(), "partagee": False},
    )

    derived_steps = _steps() + [
        {"kind": "deposition", "name": "Contact", "material": "Au", "recipe": "Sputter Metal (normal)", "thickness": {"value": 80, "unit": "nm"}}
    ]
    derived = client.post(
        f"/api/projects/{slug}/structures-sauvegardees",
        json={
            "name": "Epitaxie + contact",
            "substrate": _substrate(),
            "steps": derived_steps,
            "derived_from": "Epitaxie",
            "partagee": False,
        },
    )
    assert derived.status_code == 201
    saved = next(s for s in derived.json()["projet"] if s["name"] == "Epitaxie + contact")
    assert saved["derived_from"] == "Epitaxie"
    assert len(saved["steps"]) == 2


def test_duplicate_name_in_the_same_library_is_rejected(client):
    slug = _register_and_project(client, "libD@example.com")
    payload = {"name": "Structure X", "substrate": _substrate(), "steps": _steps(), "partagee": False}
    first = client.post(f"/api/projects/{slug}/structures-sauvegardees", json=payload)
    assert first.status_code == 201
    again = client.post(f"/api/projects/{slug}/structures-sauvegardees", json=payload)
    assert again.status_code == 409


def test_rename_a_saved_structure_in_place(client):
    slug = _register_and_project(client, "libE@example.com")
    client.post(
        f"/api/projects/{slug}/structures-sauvegardees",
        json={"name": "Nom initial", "substrate": _substrate(), "steps": _steps(), "partagee": False},
    )
    renamed = client.put(
        f"/api/projects/{slug}/structures-sauvegardees/Nom initial",
        params={"partagee": False},
        json={"name": "Nom corrige", "substrate": _substrate(), "steps": _steps()},
    )
    assert renamed.status_code == 200
    names = [s["name"] for s in renamed.json()["projet"]]
    assert names == ["Nom corrige"]


def test_delete_a_saved_structure(client):
    slug = _register_and_project(client, "libF@example.com")
    client.post(
        f"/api/projects/{slug}/structures-sauvegardees",
        json={"name": "A retirer", "substrate": _substrate(), "steps": _steps(), "partagee": False},
    )
    deleted = client.delete(f"/api/projects/{slug}/structures-sauvegardees/A retirer", params={"partagee": False})
    assert deleted.status_code == 200
    assert deleted.json()["projet"] == []


def test_viewer_cannot_create_a_saved_structure(client):
    slug = _register_and_project(client, "libG-owner@example.com")
    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={"email": "libG-viewer@example.com", "password": "supersecret", "name": "V"})
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "libG-owner@example.com", "password": "supersecret"})
    client.post(f"/api/projects/{slug}/members", json={"email": "libG-viewer@example.com", "role": "viewer"})

    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "libG-viewer@example.com", "password": "supersecret"})
    denied = client.post(
        f"/api/projects/{slug}/structures-sauvegardees",
        json={"name": "Interdit", "substrate": _substrate(), "steps": _steps(), "partagee": False},
    )
    assert denied.status_code == 403
