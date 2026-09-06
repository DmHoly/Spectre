"""Formulaires d'intention (spectre.core.intent_forms / spectre.api.intent_forms): a library of
named follow.storage.commit_form.CommitForm templates, one of which a project can activate -
materialized as that project's Follow commit_form.yml, enforced by Follow itself on every commit.
"""

from __future__ import annotations


def _substrate():
    return {"material": "Si", "domain_width": {"value": 200, "unit": "nm"}, "thickness": {"value": 50, "unit": "nm"}}


def _steps(thickness=20):
    return [
        {"kind": "deposition", "name": "Oxyde", "material": "SiO2", "recipe": "CVD Conformal", "thickness": {"value": thickness, "unit": "nm"}}
    ]

_SIMPLE_FORM_YAML = """
title: Formulaire simple
fields:
  - name: operateur
    label: Opérateur
    type: string
    required: true
"""


def _register_and_project(client, email, project_name="Projet"):
    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={"email": email, "password": "supersecret", "name": "T"})
    return client.post("/api/projects", json={"name": project_name}).json()["slug"]


def _launch(client, slug, **extra):
    payload = {
        "substrate": _substrate(),
        "steps": _steps(),
        "title": "Reference",
        "intent": "Depart",
        "entities": [{"sample_id": "W1"}],
    }
    payload.update(extra)
    return client.post(f"/api/projects/{slug}/experiences", json=payload)


def test_create_and_list_intent_form(client):
    slug = _register_and_project(client, "forms-list@example.com")
    response = client.post(
        f"/api/projects/{slug}/formulaires-intention", json={"name": "Simple", "yaml": _SIMPLE_FORM_YAML}
    )
    assert response.status_code == 201
    items = response.json()
    assert items["projet"][0]["name"] == "Simple"
    assert items["projet"][0]["form"]["title"] == "Formulaire simple"
    assert items["presets"] == []
    assert items["partagees"] == []


def test_invalid_yaml_is_rejected(client):
    slug = _register_and_project(client, "forms-invalid@example.com")
    response = client.post(f"/api/projects/{slug}/formulaires-intention", json={"name": "Cassé", "yaml": "not: [valid"})
    assert response.status_code == 422


def test_duplicate_name_conflicts(client):
    slug = _register_and_project(client, "forms-dup@example.com")
    client.post(f"/api/projects/{slug}/formulaires-intention", json={"name": "Simple", "yaml": _SIMPLE_FORM_YAML})
    response = client.post(f"/api/projects/{slug}/formulaires-intention", json={"name": "Simple", "yaml": _SIMPLE_FORM_YAML})
    assert response.status_code == 409


def test_launching_without_an_active_form_needs_no_answers(client):
    slug = _register_and_project(client, "forms-none@example.com")
    response = _launch(client, slug)
    assert response.status_code == 201
    assert client.get(f"/api/projects/{slug}/formulaire-actif").json() is None


def test_activating_a_form_requires_its_fields_on_launch(client):
    slug = _register_and_project(client, "forms-required@example.com")
    client.post(f"/api/projects/{slug}/formulaires-intention", json={"name": "Simple", "yaml": _SIMPLE_FORM_YAML})
    activated = client.post(f"/api/projects/{slug}/formulaire-actif", json={"name": "Simple", "partagee": False})
    assert activated.status_code == 200
    assert activated.json()["form"]["title"] == "Formulaire simple"

    missing = _launch(client, slug)
    assert missing.status_code == 422
    assert "operateur" in str(missing.json()["detail"])

    ok = _launch(client, slug, form_answers={"operateur": "Alice"})
    assert ok.status_code == 201
    detail = client.get(f"/api/projects/{slug}/experiences/{ok.json()['id']}").json()
    assert detail["form_answers"] == {"operateur": "Alice"}


def test_lightweight_actions_carry_forward_form_answers_unchanged(client):
    slug = _register_and_project(client, "forms-carry@example.com")
    client.post(f"/api/projects/{slug}/formulaires-intention", json={"name": "Simple", "yaml": _SIMPLE_FORM_YAML})
    client.post(f"/api/projects/{slug}/formulaire-actif", json={"name": "Simple", "partagee": False})
    launched = _launch(client, slug, form_answers={"operateur": "Alice"}).json()

    tagged = client.post(f"/api/projects/{slug}/experiences/{launched['id']}/etiquettes", json={"tags": ["a-suivre"]})
    assert tagged.status_code == 201
    detail = client.get(f"/api/projects/{slug}/experiences/{tagged.json()['id']}").json()
    assert detail["form_answers"] == {"operateur": "Alice"}


def test_evolving_requires_reanswering_the_form(client):
    slug = _register_and_project(client, "forms-evolve@example.com")
    client.post(f"/api/projects/{slug}/formulaires-intention", json={"name": "Simple", "yaml": _SIMPLE_FORM_YAML})
    client.post(f"/api/projects/{slug}/formulaire-actif", json={"name": "Simple", "partagee": False})
    launched = _launch(client, slug, form_answers={"operateur": "Alice"}).json()

    missing = client.post(
        f"/api/projects/{slug}/experiences/{launched['id']}/evoluer",
        json={"substrate": _substrate(), "steps": _steps(30), "title": "Suite", "intent": "x"},
    )
    assert missing.status_code == 422

    ok = client.post(
        f"/api/projects/{slug}/experiences/{launched['id']}/evoluer",
        json={"substrate": _substrate(), "steps": _steps(30), "title": "Suite", "intent": "x", "form_answers": {"operateur": "Bob"}},
    )
    assert ok.status_code == 201
    detail = client.get(f"/api/projects/{slug}/experiences/{ok.json()['id']}").json()
    assert detail["form_answers"] == {"operateur": "Bob"}


def test_deleting_the_active_form_deactivates_it(client):
    slug = _register_and_project(client, "forms-delete@example.com")
    client.post(f"/api/projects/{slug}/formulaires-intention", json={"name": "Simple", "yaml": _SIMPLE_FORM_YAML})
    client.post(f"/api/projects/{slug}/formulaire-actif", json={"name": "Simple", "partagee": False})

    client.delete(f"/api/projects/{slug}/formulaires-intention/Simple")
    assert client.get(f"/api/projects/{slug}/formulaire-actif").json() is None

    response = _launch(client, slug)
    assert response.status_code == 201


def test_deactivating_a_form_stops_requiring_it(client):
    slug = _register_and_project(client, "forms-deactivate@example.com")
    client.post(f"/api/projects/{slug}/formulaires-intention", json={"name": "Simple", "yaml": _SIMPLE_FORM_YAML})
    client.post(f"/api/projects/{slug}/formulaire-actif", json={"name": "Simple", "partagee": False})

    deactivated = client.post(f"/api/projects/{slug}/formulaire-actif", json={"name": None})
    assert deactivated.status_code == 200
    assert deactivated.json() is None

    response = _launch(client, slug)
    assert response.status_code == 201
