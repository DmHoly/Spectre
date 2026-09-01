from __future__ import annotations


def _substrate():
    return {"material": "Si", "domain_width": {"value": 200, "unit": "nm"}, "thickness": {"value": 50, "unit": "nm"}}


def _steps(thickness=20):
    return [
        {
            "kind": "deposition",
            "name": "Oxyde",
            "material": "SiO2",
            "mode": "conformal",
            "thickness": {"value": thickness, "unit": "nm"},
        }
    ]


def _register_and_project(client, email):
    client.post("/api/auth/register", json={"email": email, "password": "supersecret", "name": "T"})
    return client.post("/api/projects", json={"name": "Projet"}).json()["slug"]


def test_combine_two_experiences_keeps_the_base_structure_and_links_the_other(client):
    slug = _register_and_project(client, "combine@example.com")
    a = client.post(
        f"/api/projects/{slug}/experiences",
        json={"substrate": _substrate(), "steps": _steps(20), "title": "Piste A", "intent": "Depart A"},
    ).json()
    b = client.post(
        f"/api/projects/{slug}/experiences",
        json={"substrate": _substrate(), "steps": _steps(40), "title": "Piste B", "intent": "Depart B"},
    ).json()

    combined = client.post(
        f"/api/projects/{slug}/experiences/{a['id']}/combiner",
        json={"other_id": b["id"], "title": "Synthese A+B", "intent": "Regrouper les deux pistes"},
    )
    assert combined.status_code == 201
    combined_id = combined.json()["id"]

    detail = client.get(f"/api/projects/{slug}/experiences/{combined_id}").json()
    assert sorted(detail["parents"]) == sorted([a["id"], b["id"]])
    assert detail["title"] == "Synthese A+B"
    # kept A's structure/steps (the default, conflict-free behaviour)
    process = client.get(f"/api/projects/{slug}/experiences/{combined_id}/process").json()
    assert process["steps"][0]["thickness"]["value"] == 20


def test_combine_rejects_combining_an_experience_with_itself(client):
    slug = _register_and_project(client, "combineself@example.com")
    a = client.post(
        f"/api/projects/{slug}/experiences",
        json={"substrate": _substrate(), "steps": _steps(), "title": "Solo", "intent": "Depart"},
    ).json()
    response = client.post(
        f"/api/projects/{slug}/experiences/{a['id']}/combiner",
        json={"other_id": a["id"], "title": "X", "intent": "Y"},
    )
    assert response.status_code == 422


def test_combine_rejects_a_single_experience_with_a_campaign(client):
    slug = _register_and_project(client, "combinetypes@example.com")
    single = client.post(
        f"/api/projects/{slug}/experiences",
        json={"substrate": _substrate(), "steps": _steps(), "title": "Solo", "intent": "Depart"},
    ).json()
    campaign = client.post(
        f"/api/projects/{slug}/experiences/campagne",
        json={
            "substrate": _substrate(),
            "steps": _steps(),
            "plan": {"factors": [{"step_index": 0, "field": "thickness", "values": [10, 20, 30]}]},
            "title": "Campagne",
            "intent": "Balayage",
        },
    ).json()
    response = client.post(
        f"/api/projects/{slug}/experiences/{single['id']}/combiner",
        json={"other_id": campaign["id"], "title": "X", "intent": "Y"},
    )
    assert response.status_code == 422


def test_setting_and_removing_tags_records_a_new_version_and_preserves_status(client):
    slug = _register_and_project(client, "tags@example.com")
    launched = client.post(
        f"/api/projects/{slug}/experiences",
        json={"substrate": _substrate(), "steps": _steps(), "title": "Reference", "intent": "Depart"},
    ).json()

    tagged = client.post(
        f"/api/projects/{slug}/experiences/{launched['id']}/etiquettes",
        json={"tags": ["a valider", "prioritaire", "a valider"]},
    )
    assert tagged.status_code == 201
    assert tagged.json()["tags"] == ["a valider", "prioritaire"]
    tagged_id = tagged.json()["id"]
    assert tagged_id != launched["id"]

    detail = client.get(f"/api/projects/{slug}/experiences/{tagged_id}").json()
    assert detail["tags"] == ["a valider", "prioritaire"]
    assert detail["status"] == "draft"  # tagging must not change the status

    untagged = client.post(f"/api/projects/{slug}/experiences/{tagged_id}/etiquettes", json={"tags": ["prioritaire"]})
    assert untagged.json()["tags"] == ["prioritaire"]


def test_adding_evidence_or_concluding_preserves_existing_tags(client):
    slug = _register_and_project(client, "tagscarry@example.com")
    launched = client.post(
        f"/api/projects/{slug}/experiences",
        json={"substrate": _substrate(), "steps": _steps(), "title": "Reference", "intent": "Depart"},
    ).json()
    tagged = client.post(
        f"/api/projects/{slug}/experiences/{launched['id']}/etiquettes", json={"tags": ["important"]}
    ).json()

    with_evidence = client.post(
        f"/api/projects/{slug}/experiences/{tagged['id']}/preuves",
        json={"description": "Mesure", "source": "profilometre"},
    ).json()
    assert client.get(f"/api/projects/{slug}/experiences/{with_evidence['id']}").json()["tags"] == ["important"]

    concluded = client.post(
        f"/api/projects/{slug}/experiences/{with_evidence['id']}/conclure",
        json={"status": "concluded", "summary": "Fini", "objective_results": []},
    ).json()
    detail = client.get(f"/api/projects/{slug}/experiences/{concluded['id']}").json()
    assert detail["tags"] == ["important"]
    assert detail["status"] == "concluded"


def test_concluding_does_not_reset_status_of_a_later_evidence_addition(client):
    # regression: add_evidence used to leave `conclusion` at its fresh default, silently
    # un-concluding an already-concluded experience the moment evidence was attached to it.
    slug = _register_and_project(client, "statuscarry@example.com")
    launched = client.post(
        f"/api/projects/{slug}/experiences",
        json={"substrate": _substrate(), "steps": _steps(), "title": "Reference", "intent": "Depart"},
    ).json()
    concluded = client.post(
        f"/api/projects/{slug}/experiences/{launched['id']}/conclure",
        json={"status": "concluded", "summary": "Fini", "objective_results": []},
    ).json()
    assert client.get(f"/api/projects/{slug}/experiences/{concluded['id']}").json()["status"] == "concluded"

    with_evidence = client.post(
        f"/api/projects/{slug}/experiences/{concluded['id']}/preuves",
        json={"description": "Mesure tardive", "source": "profilometre"},
    ).json()
    assert client.get(f"/api/projects/{slug}/experiences/{with_evidence['id']}").json()["status"] == "concluded"
