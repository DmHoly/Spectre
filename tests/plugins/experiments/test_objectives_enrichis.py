from __future__ import annotations

from support.experiments import conclude, evolve, get_experiment, launch
from support.microprojects import signup_with_microproject
from support.structures import steps


def test_launch_stores_rationale_and_verification_method(client):
    slug = signup_with_microproject(client, "obj@example.com", name="O")

    launched = launch(
        client,
        slug,
        intent="Verifier isolation",
        objectives=[
            {
                "name": "Isolation",
                "metric": "resistivity_ohm_cm",
                "direction": "target",
                "target": 1e6,
                "rationale": "condition pour passer en production",
                "verification_method": "mesure au profilometre",
            }
        ],
    )

    detail = get_experiment(client, slug, launched["id"])
    assert detail["objectives"][0]["rationale"] == "condition pour passer en production"
    assert detail["objective_verification"] == {"Isolation": "mesure au profilometre"}


def test_conclude_captures_reasoning_per_objective(client):
    slug = signup_with_microproject(client, "obj2@example.com", name="O2")
    launched = launch(client, slug, objectives=[{"name": "Isolation", "metric": "r", "direction": "observe"}])

    concluded = conclude(
        client, slug, launched["id"], objective_results=[{"objective": "Isolation", "status": "met", "reasoning": "Mesure conforme a 1.2e6"}]
    )

    detail = get_experiment(client, slug, concluded["id"])
    assert detail["conclusion"]["objective_results"][0]["reasoning"] == "Mesure conforme a 1.2e6"


def test_evolve_carries_verification_when_objectives_unchanged(client):
    slug = signup_with_microproject(client, "obj3@example.com", name="O3")
    launched = launch(
        client,
        slug,
        steps=steps(20),
        objectives=[{"name": "Isolation", "metric": "r", "direction": "observe", "verification_method": "profilometre"}],
    )

    evolved = evolve(client, slug, launched["id"], intent="Reduire", steps=steps(10))

    detail = get_experiment(client, slug, evolved["id"])
    assert detail["objective_verification"] == {"Isolation": "profilometre"}
