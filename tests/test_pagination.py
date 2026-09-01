from __future__ import annotations


def _substrate():
    return {"material": "Si", "domain_width": {"value": 200, "unit": "nm"}, "thickness": {"value": 50, "unit": "nm"}}


def _steps():
    return [
        {
            "kind": "deposition",
            "name": "Oxyde",
            "material": "SiO2",
            "mode": "conformal",
            "thickness": {"value": 20, "unit": "nm"},
        }
    ]


def test_experiences_are_paginated(client):
    client.post("/api/auth/register", json={"email": "page@example.com", "password": "supersecret", "name": "P"})
    slug = client.post("/api/projects", json={"name": "Projet pagine"}).json()["slug"]

    for i in range(5):
        client.post(
            f"/api/projects/{slug}/experiences",
            json={"substrate": _substrate(), "steps": _steps(), "title": f"Essai {i}", "intent": "x"},
        )

    page1 = client.get(f"/api/projects/{slug}/experiences?status=all&offset=0&limit=2").json()
    assert len(page1["items"]) == 2
    assert page1["total"] == 5
    assert page1["offset"] == 0
    assert page1["limit"] == 2

    page2 = client.get(f"/api/projects/{slug}/experiences?status=all&offset=2&limit=2").json()
    assert len(page2["items"]) == 2
    assert {i["id"] for i in page1["items"]}.isdisjoint({i["id"] for i in page2["items"]})

    page3 = client.get(f"/api/projects/{slug}/experiences?status=all&offset=4&limit=2").json()
    assert len(page3["items"]) == 1


def test_pagination_rejects_bad_params(client):
    client.post("/api/auth/register", json={"email": "page2@example.com", "password": "supersecret", "name": "P2"})
    slug = client.post("/api/projects", json={"name": "Projet"}).json()["slug"]

    assert client.get(f"/api/projects/{slug}/experiences?offset=-1").status_code == 422
    assert client.get(f"/api/projects/{slug}/experiences?limit=0").status_code == 422
    assert client.get(f"/api/projects/{slug}/experiences?limit=500").status_code == 422
