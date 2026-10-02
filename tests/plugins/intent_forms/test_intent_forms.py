"""Formulaires d'intention (spectre.plugins.intent_forms): a library of
named follow.storage.commit_form.CommitForm templates, one of which a microproject can activate -
materialized as that microproject's Follow commit_form.yml, enforced by Follow itself on every commit.
"""

from __future__ import annotations

import pytest

from support.experiments import conclude, get_experience, launch, launch_body, tag
from support.microprojects import signup_with_microproject
from support.structures import steps, substrate

_SIMPLE_FORM_YAML = """
title: Formulaire simple
fields:
  - name: operateur
    label: Opérateur
    type: string
    required: true
"""


def _activate_simple_form(client, slug):
    created = client.post(f"/api/microprojets/{slug}/formulaires-intention", json={"name": "Simple", "yaml": _SIMPLE_FORM_YAML})
    assert created.status_code == 201, created.text
    activated = client.post(f"/api/microprojets/{slug}/formulaire-actif", json={"name": "Simple", "partagee": False})
    assert activated.status_code == 200, activated.text
    return activated.json()


def _launch_response(client, slug, **extra):
    return client.post(f"/api/microprojets/{slug}/experiences", json=launch_body(title="Reference", intent="Depart", **extra))


def test_create_and_list_intent_form(client):
    slug = signup_with_microproject(client, "forms-list@example.com")
    response = client.post(
        f"/api/microprojets/{slug}/formulaires-intention", json={"name": "Simple", "yaml": _SIMPLE_FORM_YAML}
    )
    assert response.status_code == 201
    items = response.json()
    assert items["microprojet"][0]["name"] == "Simple"
    assert items["microprojet"][0]["form"]["title"] == "Formulaire simple"
    assert items["presets"] == []
    assert items["partagees"] == []


def test_invalid_yaml_is_rejected(client):
    slug = signup_with_microproject(client, "forms-invalid@example.com")
    response = client.post(f"/api/microprojets/{slug}/formulaires-intention", json={"name": "Cassé", "yaml": "not: [valid"})
    assert response.status_code == 422


def test_duplicate_name_conflicts(client):
    slug = signup_with_microproject(client, "forms-dup@example.com")
    client.post(f"/api/microprojets/{slug}/formulaires-intention", json={"name": "Simple", "yaml": _SIMPLE_FORM_YAML})
    response = client.post(f"/api/microprojets/{slug}/formulaires-intention", json={"name": "Simple", "yaml": _SIMPLE_FORM_YAML})
    assert response.status_code == 409


def test_launching_without_an_active_form_needs_no_answers(client):
    slug = signup_with_microproject(client, "forms-none@example.com")
    assert _launch_response(client, slug).status_code == 201
    assert client.get(f"/api/microprojets/{slug}/formulaire-actif").json() is None


def test_activating_a_form_requires_its_fields_on_launch(client):
    slug = signup_with_microproject(client, "forms-required@example.com")
    assert _activate_simple_form(client, slug)["form"]["title"] == "Formulaire simple"

    missing = _launch_response(client, slug)
    assert missing.status_code == 422
    assert "operateur" in str(missing.json()["detail"])

    ok = _launch_response(client, slug, form_answers={"operateur": "Alice"})
    assert ok.status_code == 201
    assert get_experience(client, slug, ok.json()["id"])["form_answers"] == {"operateur": "Alice"}


def test_lightweight_actions_carry_forward_form_answers_unchanged(client):
    slug = signup_with_microproject(client, "forms-carry@example.com")
    _activate_simple_form(client, slug)
    launched = launch(client, slug, form_answers={"operateur": "Alice"})

    tagged = tag(client, slug, launched["id"], ["a-suivre"])
    assert get_experience(client, slug, tagged["id"])["form_answers"] == {"operateur": "Alice"}


def test_evolving_requires_reanswering_the_form(client):
    slug = signup_with_microproject(client, "forms-evolve@example.com")
    _activate_simple_form(client, slug)
    launched = launch(client, slug, form_answers={"operateur": "Alice"})

    missing = client.post(
        f"/api/microprojets/{slug}/experiences/{launched['id']}/evoluer",
        json={"substrate": substrate(), "steps": steps(30), "title": "Suite", "intent": "x"},
    )
    assert missing.status_code == 422

    ok = client.post(
        f"/api/microprojets/{slug}/experiences/{launched['id']}/evoluer",
        json={"substrate": substrate(), "steps": steps(30), "title": "Suite", "intent": "x", "form_answers": {"operateur": "Bob"}},
    )
    assert ok.status_code == 201
    assert get_experience(client, slug, ok.json()["id"])["form_answers"] == {"operateur": "Bob"}


@pytest.mark.xfail(
    strict=True,
    reason="bug connu : les évolutions légères (/conclure, /etiquettes...) recopient form_answers de la "
    "version parente, qui ne répond pas à un formulaire activé après coup - Follow refuse alors le "
    "commit (422). À corriger à l'étape plugin experiments.",
)
def test_activating_a_form_after_launch_does_not_block_concluding(client):
    slug = signup_with_microproject(client, "forms-late@example.com")
    launched = launch(client, slug)
    _activate_simple_form(client, slug)

    conclude(client, slug, launched["id"], summary="Fini")


def test_deleting_the_active_form_deactivates_it(client):
    slug = signup_with_microproject(client, "forms-delete@example.com")
    _activate_simple_form(client, slug)

    client.delete(f"/api/microprojets/{slug}/formulaires-intention/Simple")
    assert client.get(f"/api/microprojets/{slug}/formulaire-actif").json() is None

    assert _launch_response(client, slug).status_code == 201


def test_deactivating_a_form_stops_requiring_it(client):
    slug = signup_with_microproject(client, "forms-deactivate@example.com")
    _activate_simple_form(client, slug)

    deactivated = client.post(f"/api/microprojets/{slug}/formulaire-actif", json={"name": None})
    assert deactivated.status_code == 200
    assert deactivated.json() is None

    assert _launch_response(client, slug).status_code == 201
