"""Les macro-étapes d'une structure : une brique a un rôle (gabarit SAG, épitaxie, procédé), un
gabarit SAG garde son substrat et son réseau, une épi ou un procédé les briques sur lesquelles on
l'a composé (pour l'aperçu seulement) ; une structure a au plus une brique de chaque rôle, que
l'étude garde d'une version à l'autre et qu'une combinaison reprend."""

from __future__ import annotations

from support.experiments import evolve, launch, process
from support.microprojects import signup_with_microproject
from support.process_library import create_item, get_item, tech_brick, update_item
from support.structures import deposition, identified, length, simulate

from spectre.plugins.structures import composition
from spectre.plugins.structures.schemas import ProcessInput

SAG_SUBSTRATE = {"material": "GaN", "domain_width": length(400), "thickness": length(50), "lattice": {"pitch": 400, "wires": 1}}
STACK = identified(
    [
        deposition("Masque", "Si3N4", thickness_nm=30),
        deposition("n-GaN", "GaN", recipe="MOCVD Epitaxial", thickness_nm=200),
        deposition("Puits", "In0.20Ga0.80N", recipe="MOCVD Epitaxial", thickness_nm=30),
        deposition("Passivation", "SiO2", thickness_nm=20),
    ]
)
SAG = {"group_id": "brick-sag", "name": "SAG 400", "source": "b-sag", "step_indexes": [0], "role": "sag"}
EPI = {"group_id": "brick-epi", "name": "Épi bleue", "source": "b-epi", "step_indexes": [1, 2], "role": "epi"}
PROCESS = {"group_id": "brick-proc", "name": "Passivation", "step_indexes": [3], "role": "process"}


def test_a_sag_template_keeps_its_substrate_and_the_others_their_preview_bricks(client):
    slug = signup_with_microproject(client, "macro-library@example.com", "Salle blanche")
    sag = create_item(client, "tech-bricks", tech_brick("SAG 400", role="sag", substrate=SAG_SUBSTRATE), microproject=slug)
    assert get_item(client, "tech-bricks", sag["id"])["substrate"]["lattice"] == {"pitch": 400, "wires": 1}
    assert sag["role"] == "sag"

    # une épi n'a pas de substrat : elle s'applique sur un gabarit, gardé pour l'aperçu seulement
    epi = create_item(client, "tech-bricks", tech_brick("Épi bleue", role="epi", substrate=SAG_SUBSTRATE, preview_on=[sag["id"]]), microproject=slug)
    assert epi["role"] == "epi" and "substrate" not in epi and epi["preview_on"] == [sag["id"]]

    # une brique libre, comme avant ; un rôle se retire
    assert create_item(client, "tech-bricks", tech_brick("Libre"), microproject=slug)["role"] is None
    assert update_item(client, "tech-bricks", epi["id"], role=None)["role"] is None


def test_a_structure_has_at_most_one_brick_of_each_role(client):
    signup_with_microproject(client, "macro-roles@example.com", "Salle blanche")
    body = {"substrate": SAG_SUBSTRATE, "steps": STACK, "bricks": [SAG, EPI, PROCESS]}
    response = simulate(client, body)
    assert response.status_code == 200

    twice = {**body, "bricks": [SAG, EPI, {**PROCESS, "role": "epi"}]}
    refused = simulate(client, twice)
    assert refused.status_code == 422 and refused.json()["code"] == "invalid_brick"
    assert "épitaxie" in refused.json()["detail"]


def test_a_study_keeps_the_roles_of_its_bricks(client):
    slug = signup_with_microproject(client, "macro-study@example.com", "Salle blanche")
    study = launch(client, slug, substrate=SAG_SUBSTRATE, steps=STACK, bricks=[SAG, EPI, PROCESS])
    bricks = process(client, slug, study["id"])["bricks"]
    assert [(b["name"], b.get("role")) for b in bricks] == [("SAG 400", "sag"), ("Épi bleue", "epi"), ("Passivation", "process")]

    # une autre épi sur le même gabarit et le même procédé
    other = identified([deposition("n-GaN", "GaN", recipe="MOCVD Epitaxial", thickness_nm=300)])[0]
    steps = [STACK[0], {**other, "id": STACK[1]["id"]}, STACK[3]]
    bricks = [SAG, {**EPI, "name": "Épi verte", "source": "b-epi2", "step_indexes": [1]}, {**PROCESS, "step_indexes": [2]}]
    evolve(client, slug, study["id"], title="Essai", intent="Autre épi", substrate=SAG_SUBSTRATE, steps=steps, bricks=bricks)
    assert [(b["name"], b.get("role")) for b in process(client, slug, study["id"])["bricks"]] == [
        ("SAG 400", "sag"),
        ("Épi verte", "epi"),
        ("Passivation", "process"),
    ]


def test_a_combination_keeps_one_brick_per_role():
    first = ProcessInput.model_validate({"substrate": SAG_SUBSTRATE, "steps": STACK, "bricks": [SAG, EPI]})
    second = ProcessInput.model_validate(
        {"substrate": SAG_SUBSTRATE, "steps": STACK, "bricks": [{**SAG, "name": "Autre SAG", "group_id": "b2"}, {**EPI, "name": "Épi verte", "group_id": "b3"}]}
    )
    assembled = composition.compose([first, second])["process"]
    roles = [b.get("role") for b in assembled["bricks"] if b.get("role")]
    assert len(roles) == len(set(roles))
