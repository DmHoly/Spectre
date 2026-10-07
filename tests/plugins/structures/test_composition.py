"""Combiner des études « au marché » (POST /api/compositions) : une ligne par brique, alignées par
leur nom, une source choisie par ligne, et le procédé assemblé dans l'ordre de la source principale."""

from __future__ import annotations

from support.http import assert_ok
from support.microprojects import signup_with_microproject
from support.structures import deposition, fixed_step_id, layer_label, substrate


def _brick(group_id: str, name: str, *positions: int) -> dict:
    return {"group_id": group_id, "name": name, "source": None, "step_indexes": list(positions)}


def _process(steps: list[dict], bricks: list[dict], *, ids: bool = False, **extra) -> dict:
    if ids:
        steps = [{"id": fixed_step_id(i + 1), **step} for i, step in enumerate(steps)]
    return {"substrate": substrate("Si"), "steps": steps, "bricks": bricks, **extra}


# A : buffer, zone active (2 étapes), EBL 20 nm, p-GaN - avec ses ids (la source principale)
A = _process(
    [
        deposition("Buffer", "GaN", thickness_nm=100),
        deposition("Puits", "InGaN", thickness_nm=3),
        deposition("Barrière", "GaN", thickness_nm=10),
        deposition("EBL", "AlGaN", thickness_nm=20),
        deposition("p-GaN", "GaN", thickness_nm=80),
    ],
    [_brick("brick-a1", "Zone active", 1, 2), _brick("brick-a2", "EBL", 3), _brick("brick-a3", "p-GaN", 4)],
    ids=True,
    layer_labels={"3": layer_label("EBL", "thickness")},
)
# B : la même zone active, une autre EBL (15 nm), et une couche de contact qu'A n'a pas
B = _process(
    [
        deposition("Buffer", "GaN", thickness_nm=100),
        deposition("Puits", "InGaN", thickness_nm=3),
        deposition("Barrière", "GaN", thickness_nm=10),
        deposition("EBL", "AlGaN", thickness_nm=15),
        deposition("Contact", "ITO", thickness_nm=50),
    ],
    [_brick("brick-b1", "zone  ACTIVE", 1, 2), _brick("brick-b2", "EBL", 3), _brick("brick-b3", "Contact ITO", 4)],
)


def _compose(client, sources, choices=None, status=200):
    response = client.post("/api/compositions", json={"sources": sources, "choices": choices})
    assert response.status_code == status, response.text
    return response.json()


def test_rows_align_bricks_by_name_in_the_main_source_order(client):
    signup_with_microproject(client, "compose-rows@example.com", "Marché")
    result = _compose(client, [A, B])
    rows = result["rows"]
    assert [row["name"] for row in rows] == ["Substrat", "Zone active", "EBL", "p-GaN", "Contact ITO"]
    active = rows[1]
    assert active["present"] == [True, True] and active["same_as"] == [0, 0]  # la même zone active
    assert rows[2]["same_as"] == [0, 1]  # deux EBL différentes
    assert rows[3]["present"] == [True, False]
    # par défaut : tout de la principale, rien de ce qu'elle n'a pas
    assert [row["chosen"] for row in rows] == [0, 0, 0, 0, None]
    # le procédé par défaut est celui de A, ses étapes gardant leurs ids
    assert [step["id"] for step in result["process"]["steps"]] == [fixed_step_id(i) for i in range(1, 6)]


def test_the_chosen_bricks_are_assembled_with_their_labels_and_new_steps_have_no_id(client):
    signup_with_microproject(client, "compose-pick@example.com", "Marché")
    # zone active de A, EBL de B, p-GaN de A, contact de B
    result = _compose(client, [A, B], [0, 0, 1, 0, 1])
    process = result["process"]
    assert [step["name"] for step in process["steps"]] == ["Buffer", "Puits", "Barrière", "EBL", "p-GaN", "Contact"]
    assert process["steps"][3]["thickness"]["value"] == 15  # l'EBL de B
    assert "id" not in process["steps"][3] and "id" not in process["steps"][5]
    assert process["steps"][4]["id"] == fixed_step_id(5)
    assert [(b["name"], b["step_indexes"]) for b in process["bricks"]] == [
        ("Zone active", [1, 2]),
        ("EBL", [3]),
        ("p-GaN", [4]),
        ("Contact ITO", [5]),
    ]
    assert process["layer_labels"] == {}  # l'étiquette était sur l'EBL de A, qu'on ne prend pas
    kept = _compose(client, [A, B], [0, 0, 0, 0, None])["process"]
    assert kept["layer_labels"] == {"3": layer_label("EBL", "thickness")}
    # le procédé assemblé se simule tel quel
    assert_ok(client.post("/api/simulations", json=process))


def test_a_brick_can_be_left_out(client):
    signup_with_microproject(client, "compose-drop@example.com", "Marché")
    process = _compose(client, [A, B], [0, 0, 0, None, None])["process"]
    assert [step["name"] for step in process["steps"]] == ["Buffer", "Puits", "Barrière", "EBL"]


def test_refusals(client):
    signup_with_microproject(client, "compose-refuse@example.com", "Marché")
    unbricked = _process([deposition()], [])
    assert _compose(client, [unbricked, B], status=422)["code"] == "no_bricks"
    assert _compose(client, [A, unbricked], status=422)["code"] == "no_bricks"
    # une brique choisie chez une source qui ne l'a pas, un mauvais nombre de choix, le substrat omis
    assert _compose(client, [A, B], [0, 0, 0, 1, None], status=422)["code"] == "bad_choices"
    assert _compose(client, [A, B], [0, 0], status=422)["code"] == "bad_choices"
    assert _compose(client, [A, B], [None, 0, 0, 0, None], status=422)["code"] == "bad_choices"
    assert client.post("/api/compositions", json={"sources": [A]}).status_code == 422
