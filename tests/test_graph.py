from __future__ import annotations


def _setup_project(client, email="owner@example.com", name="Owner"):
    client.post("/api/auth/register", json={"email": email, "password": "supersecret", "name": name})
    project = client.post("/api/projects", json={"name": "Salle blanche"}).json()
    return project["slug"]


def test_graph_html_on_empty_project(client):
    slug = _setup_project(client)
    response = client.get(f"/api/projects/{slug}/graphe.html")
    assert response.status_code == 200
    assert "Aucune expérience" in response.text


def test_graph_html_with_experiments(client):
    slug = _setup_project(client)
    substrate = {"material": "Si", "domain_width": {"value": 200, "unit": "nm"}, "thickness": {"value": 50, "unit": "nm"}}
    steps = [
        {
            "kind": "deposition",
            "name": "Oxyde",
            "material": "SiO2",
            "mode": "conformal",
            "thickness": {"value": 20, "unit": "nm"},
        }
    ]
    client.post(
        f"/api/projects/{slug}/experiences",
        json={"substrate": substrate, "steps": steps, "title": "Essai", "intent": "Verifier"},
    )
    response = client.get(f"/api/projects/{slug}/graphe.html")
    assert response.status_code == 200
    assert "plotly" in response.text.lower()


def test_graph_page_is_served(client):
    slug = _setup_project(client)
    assert client.get(f"/projets/{slug}/graphe").status_code == 200


def test_non_member_cannot_see_graph(client):
    slug = _setup_project(client)
    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={"email": "stranger@example.com", "password": "supersecret", "name": "S"})
    response = client.get(f"/api/projects/{slug}/graphe.html")
    assert response.status_code == 403
