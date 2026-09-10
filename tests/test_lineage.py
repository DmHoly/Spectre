from __future__ import annotations


def _setup_microproject(client, email="owner@example.com", name="Owner"):
    client.post("/api/auth/register", json={"email": email, "password": "supersecret", "name": name})
    microproject = client.post("/api/microprojets", json={"name": "Salle blanche"}).json()
    return microproject["slug"]


def _substrate():
    return {"material": "Si", "domain_width": {"value": 200, "unit": "nm"}, "thickness": {"value": 50, "unit": "nm"}}


def _steps(thickness=20):
    return [{"kind": "deposition", "name": "Oxyde", "material": "SiO2", "recipe": "CVD Conformal", "thickness": {"value": thickness, "unit": "nm"}}]


def test_lineage_on_empty_microproject(client):
    slug = _setup_microproject(client)
    response = client.get(f"/api/microprojets/{slug}/filiation")
    assert response.status_code == 200
    assert response.json() == {"nodes": [], "edges": []}


def test_lineage_single_experience_is_a_root_and_a_tip(client):
    slug = _setup_microproject(client)
    launched = client.post(
        f"/api/microprojets/{slug}/experiences",
        json={"substrate": _substrate(), "steps": _steps(), "title": "Essai", "intent": "Verifier", "entities": [{"sample_id": "W1"}]},
    ).json()

    body = client.get(f"/api/microprojets/{slug}/filiation").json()
    assert body["edges"] == []
    assert len(body["nodes"]) == 1
    node = body["nodes"][0]
    assert node["id"] == launched["id"]
    assert node["title"] == "Essai"
    assert node["status"] == "draft"
    assert node["is_tip"] is True
    assert node["is_merge"] is False


def test_lineage_collapses_a_tag_only_commit_but_keeps_the_edge(client):
    slug = _setup_microproject(client)
    launched = client.post(
        f"/api/microprojets/{slug}/experiences",
        json={"substrate": _substrate(), "steps": _steps(), "title": "Essai", "intent": "Verifier", "entities": [{"sample_id": "W1"}]},
    ).json()
    tagged = client.post(f"/api/microprojets/{slug}/experiences/{launched['id']}/etiquettes", json={"tags": ["a-suivre"]}).json()
    evolved = client.post(
        f"/api/microprojets/{slug}/experiences/{tagged['id']}/evoluer",
        json={"substrate": _substrate(), "steps": _steps(40), "title": "Essai", "intent": "Doubler l'epaisseur", "objectives": []},
    ).json()

    body = client.get(f"/api/microprojets/{slug}/filiation").json()
    ids = {n["id"] for n in body["nodes"]}
    # the tag-only commit moved nothing structural forward - collapsed out of the graph entirely.
    assert tagged["id"] not in ids
    assert ids == {launched["id"], evolved["id"]}
    assert {"parent": launched["id"], "child": evolved["id"]} in body["edges"]

    evolved_node = next(n for n in body["nodes"] if n["id"] == evolved["id"])
    assert evolved_node["is_tip"] is True
    launched_node = next(n for n in body["nodes"] if n["id"] == launched["id"])
    assert launched_node["is_tip"] is False


def test_lineage_marks_a_combined_experience_as_a_merge(client):
    slug = _setup_microproject(client)
    a = client.post(
        f"/api/microprojets/{slug}/experiences",
        json={"substrate": _substrate(), "steps": _steps(), "title": "A", "intent": "Piste A", "entities": [{"sample_id": "W1"}]},
    ).json()
    b = client.post(
        f"/api/microprojets/{slug}/experiences",
        json={"substrate": _substrate(), "steps": _steps(30), "title": "B", "intent": "Piste B", "entities": [{"sample_id": "W2"}]},
    ).json()
    combined = client.post(
        f"/api/microprojets/{slug}/experiences/{a['id']}/combiner",
        json={"other_id": b["id"], "title": "Synthese A+B", "intent": "Regrouper les deux pistes"},
    ).json()

    body = client.get(f"/api/microprojets/{slug}/filiation").json()
    combined_node = next(n for n in body["nodes"] if n["id"] == combined["id"])
    assert combined_node["is_merge"] is True
    parents = {e["parent"] for e in body["edges"] if e["child"] == combined["id"]}
    assert parents == {a["id"], b["id"]}


def test_non_member_cannot_see_lineage(client):
    slug = _setup_microproject(client)
    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={"email": "stranger@example.com", "password": "supersecret", "name": "S"})
    response = client.get(f"/api/microprojets/{slug}/filiation")
    assert response.status_code == 403
