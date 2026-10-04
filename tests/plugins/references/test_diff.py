"""Comparer deux versions d'une référence : le diff des structures (celui des études), étiquettes de
couches et paramètres déclarés compris, lu dans les instantanés - et les versions publiées depuis un
µprojet, que sa page d'évolution montre en badges (``include_versions``)."""

from __future__ import annotations

from support.experiments import evolve, launch, structure_history, tag
from support.http import assert_handler_404
from support.microprojects import signup_with_microproject
from support.references import create_reference, publish, published_from, version_diff
from support.structures import deposition, identified, layer_label

STACK = identified([deposition("n-GaN", "GaN", thickness_nm=400), deposition("p-GaN", "GaN", thickness_nm=150)])
THICKER = identified([deposition("n-GaN", "GaN", thickness_nm=400), deposition("p-GaN", "GaN", thickness_nm=200)])


def test_two_versions_compare_structure_labels_and_parameters(client):
    slug = signup_with_microproject(client, "ref-diff@example.com", "Epi")
    study = launch(client, slug, title="LED", intent="x", steps=STACK)
    create_reference(client, "LED")
    publish(client, "led", slug, study["id"])

    evolve(
        client,
        slug,
        study["id"],
        title="LED",
        intent="y",
        steps=THICKER,
        declared_params={"1": [{"name": "dopage", "value": 3e18, "unit": "cm⁻³"}]},
        layer_labels={"1": layer_label("p-GaN", "thickness", "declared:dopage")},
    )
    publish(client, "led", slug, study["id"])

    diff = version_diff(client, "led", "1.1")
    assert diff["target"] == {"number": "1.0"}  # sa version parente par défaut
    assert diff["entries"]  # l'épaisseur du p-GaN a changé
    assert [c["change"] for c in diff["label_changes"]] == ["added"]
    assert [(c["param"], c["change"]) for c in diff["param_changes"]] == [("dopage", "added")]

    back = version_diff(client, "led", "1.0", against="1.1")
    assert back["target"] == {"number": "1.1"}
    assert [c["change"] for c in back["label_changes"]] == ["removed"]

    assert version_diff(client, "led", "1.0") == {"target": None, "entries": []}
    assert_handler_404(client.get("/api/references/led/versions/1.0/structure-diff", params={"against": "5.0"}))


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
