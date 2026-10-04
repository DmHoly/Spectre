"""Les ids d'étape côté constructeur : la simulation rend l'id de chaque étape (celui reçu, ou un
neuf attribué par le serveur - le constructeur n'en invente jamais), et l'aperçu d'une campagne
désigne les étapes par cet id."""

from __future__ import annotations

import re

from support.microprojects import signup_with_microproject
from support.structures import campaign_plan, deposition, etch, fixed_step_id, identified, preview_campaign, simulate, steps, substrate

STEP_ID = re.compile(r"^st_[0-9a-f]{8}$")


def test_the_simulation_keeps_the_ids_it_receives_and_hands_out_new_ones(client):
    signup_with_microproject(client, "simulate@example.com")
    process_steps = [
        {**deposition("Oxyde"), "id": fixed_step_id(1)},
        etch("Gravure"),  # une nouvelle étape
        {**deposition("Copie"), "id": fixed_step_id(1)},  # une étape dupliquée
        {**deposition("Nitrure", "Si3N4"), "id": "pas-un-id"},
    ]
    response = simulate(client, {"substrate": substrate(), "steps": process_steps})
    assert response.status_code == 200, response.text
    body = response.json()
    ids = body["step_ids"]
    assert ids[0] == fixed_step_id(1)
    assert all(STEP_ID.fullmatch(step_id) for step_id in ids) and len(set(ids)) == 4
    assert len(body["frames"]) == 5  # le substrat, puis une image par étape : l'id ne gêne pas StructureForge


def test_a_campaign_preview_names_steps_by_id(client):
    signup_with_microproject(client, "preview-ids@example.com")
    process_steps = identified([deposition("Oxyde"), deposition("Nitrure", "Si3N4", thickness_nm=10)])
    response = preview_campaign(client, {"substrate": substrate(), "steps": process_steps, "plan": campaign_plan([5, 15], step_id=fixed_step_id(2))})
    assert response.status_code == 200, response.text
    assert response.json()["factor_labels"] == ["Épaisseur — Nitrure"]

    # un id qu'aucune étape ne porte, ou une étape envoyée sans id : refusé
    unknown = preview_campaign(client, {"substrate": substrate(), "steps": process_steps, "plan": campaign_plan([5, 15], step_id=fixed_step_id(3))})
    assert unknown.status_code == 422
    without_ids = preview_campaign(client, {"substrate": substrate(), "steps": [deposition()], "plan": campaign_plan([5, 15])})
    assert without_ids.status_code == 422

    substrate_only = preview_campaign(client, {"substrate": substrate(), "steps": steps(), "plan": campaign_plan([40, 80], step_id="substrate")})
    assert substrate_only.status_code == 200, substrate_only.text
    assert substrate_only.json()["factor_labels"] == ["Épaisseur — Substrat"]
