"""Les versions publiées depuis un µprojet, que sa page d'évolution montre en badges
(``include_versions``)."""

from __future__ import annotations

from support.experiments import launch, structure_history, tag
from support.microprojects import signup_with_microproject
from support.references import create_reference, publish, published_from
from support.structures import deposition, identified

STACK = identified([deposition("n-GaN", "GaN", thickness_nm=400), deposition("p-GaN", "GaN", thickness_nm=150)])


def test_the_evolution_page_can_show_the_published_versions(client):
    slug = signup_with_microproject(client, "ref-badges@example.com", "Epi")
    study = launch(client, slug, title="LED", intent="x", steps=STACK)
    # une version légère (une étiquette) : la page d'évolution ne la montre pas par défaut
    light = tag(client, slug, study["id"], ["approuvee"])
    create_reference(client, "LED")
    publish(client, "led", slug, study["id"])

    published = published_from(client, slug)
    assert [(p["version_id"], p["label"]) for p in published] == [(light["version_id"], "R LED 1.0")]
    default = {n["version_id"] for n in structure_history(client, slug)["nodes"]}
    assert light["version_id"] not in default
    shown = client.get(f"/api/microprojects/{slug}/structure-history", params={"include_versions": [light["version_id"], "exp_0000000000000000"]})
    assert shown.status_code == 200
    assert {n["version_id"] for n in shown.json()["nodes"]} == default | {light["version_id"]}
