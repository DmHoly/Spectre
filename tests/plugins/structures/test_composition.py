"""Combiner des études « au marché » (POST /api/compositions) : une ligne par étape - alignées par
leur id, sinon par brique, type et nom -, une source choisie par ligne (ou aucune), une étape qui en
remplace une autre, et le procédé assemblé dans l'ordre de la source principale."""

from __future__ import annotations

from support.http import assert_ok
from support.microprojects import signup_with_microproject
from support.structures import deposition, etch, fixed_step_id, layer_label, substrate


def _brick(group_id: str, name: str, *positions: int) -> dict:
    return {"group_id": group_id, "name": name, "source": None, "step_indexes": list(positions)}


def _process(steps: list[dict], bricks: list[dict], *, ids: bool = False, **extra) -> dict:
    if ids:
        steps = [{"id": fixed_step_id(i + 1), **step} for i, step in enumerate(steps)]
    return {"substrate": substrate("Si"), "steps": steps, "bricks": bricks, **extra}


# A : buffer (hors brique), zone active (2 étapes), EBL 20 nm, p-GaN - avec ses ids (la principale)
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
# B, sans ids : la même zone active (nom de brique écrit autrement), une autre EBL (15 nm), et une
# couche de contact qu'A n'a pas
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


def _key(rows, name):
    return next(row["key"] for row in rows if row["name"] == name)


def test_one_row_per_step_aligned_by_brick_kind_and_name(client):
    signup_with_microproject(client, "compose-rows@example.com", "Marché")
    rows = _compose(client, [A, B])["rows"]
    assert [row["name"] for row in rows] == ["Substrat", "Buffer", "Puits", "Barrière", "EBL", "p-GaN", "Contact"]
    assert [row["brick"] for row in rows] == [None, None, "Zone active", "Zone active", "EBL", "p-GaN", "Contact ITO"]
    puits = rows[2]
    assert puits["present"] == [True, True] and puits["same_as"] == [0, 0]
    ebl = rows[4]
    assert ebl["same_as"] == [0, 1] and ebl["summary"] == ["20 nm", "15 nm"]
    assert rows[5]["present"] == [True, False] and rows[6]["present"] == [False, True] and rows[6]["in_main"] is False
    # par défaut : tout de la principale, rien de ce qu'elle n'a pas
    assert [row["chosen"] for row in rows] == [0, 0, 0, 0, 0, 0, None]


def test_steps_are_picked_one_by_one(client):
    signup_with_microproject(client, "compose-pick@example.com", "Marché")
    # l'EBL de B (à la place de celle de A), et le contact de B en plus
    result = _compose(client, [A, B], [0, 0, 0, 0, 1, 0, 1])
    process = result["process"]
    assert [step["name"] for step in process["steps"]] == ["Buffer", "Puits", "Barrière", "EBL", "p-GaN", "Contact"]
    # l'EBL de B garde l'id de la ligne chez A : c'est la même étape, d'autres valeurs
    assert process["steps"][3]["thickness"]["value"] == 15 and process["steps"][3]["id"] == fixed_step_id(4)
    assert process["steps"][4]["id"] == fixed_step_id(5) and "id" not in process["steps"][5]
    assert [(b["name"], b["step_indexes"]) for b in process["bricks"]] == [
        ("Zone active", [1, 2]),
        ("EBL", [3]),
        ("p-GaN", [4]),
        ("Contact ITO", [5]),
    ]
    assert process["layer_labels"] == {}  # l'étiquette était sur l'EBL de A
    # mélanger une brique : le puits de A, la barrière de B (identique : aucune différence)
    mixed = _compose(client, [A, B], [0, 0, 0, 1, 0, 0, None])["process"]
    assert [b["step_indexes"] for b in mixed["bricks"]][0] == [1, 2]
    assert_ok(client.post("/api/simulations", json=process))


def test_a_step_can_be_left_out(client):
    signup_with_microproject(client, "compose-drop@example.com", "Marché")
    process = _compose(client, [A, B], [0, None, 0, 0, 0, None, None])["process"]
    assert [step["name"] for step in process["steps"]] == ["Puits", "Barrière", "EBL"]


def test_a_step_replaces_another_in_its_place_and_brick(client):
    signup_with_microproject(client, "compose-replace@example.com", "Marché")
    wet = _process(
        [deposition("Buffer", "GaN", thickness_nm=100), etch("Gravure humide", recipe="Isotropic wet", depth_nm=5)],
        [_brick("brick-w", "Gravure", 1)],
    )
    dry = _process(
        [deposition("Buffer", "GaN", thickness_nm=100), etch("Gravure ICP", depth_nm=5), deposition("Capot", "SiO2", thickness_nm=10)],
        [_brick("brick-d", "Gravure", 1)],
        ids=True,
    )
    rows = _compose(client, [dry, wet])["rows"]
    assert [row["name"] for row in rows] == ["Substrat", "Buffer", "Gravure ICP", "Capot", "Gravure humide"]
    choices = [0, 0, 0, 0, {"source": 1, "replaces": _key(rows, "Gravure ICP")}]
    result = _compose(client, [dry, wet], choices)
    process = result["process"]
    assert [step["name"] for step in process["steps"]] == ["Buffer", "Gravure humide", "Capot"]
    assert [(b["name"], b["step_indexes"]) for b in process["bricks"]] == [("Gravure", [1])]
    assert result["rows"][4]["replaces"] == _key(rows, "Gravure ICP")


def test_sources_without_bricks_align_by_step_id(client):
    signup_with_microproject(client, "compose-nobrick@example.com", "Marché")
    plain_a = _process([deposition("Oxyde", thickness_nm=20), deposition("Nitrure", "Si3N4", thickness_nm=30)], [], ids=True)
    # une évolution de A : la même première étape (même id) renommée et épaissie, une étape ajoutée
    # (rien ne la suit chez elle : en haut)
    plain_b = _process(
        [{"id": fixed_step_id(1), **deposition("Oxyde épais", thickness_nm=40)}, deposition("Recuit", "SiO2", thickness_nm=1)], []
    )
    rows = _compose(client, [plain_a, plain_b])["rows"]
    assert [row["name"] for row in rows] == ["Substrat", "Oxyde", "Nitrure", "Recuit"]
    assert rows[1]["present"] == [True, True] and rows[1]["same_as"] == [0, 1]
    process = _compose(client, [plain_a, plain_b], [0, 1, 0, 1])["process"]
    assert [(s["name"], s.get("id")) for s in process["steps"]] == [("Oxyde épais", fixed_step_id(1)), ("Nitrure", fixed_step_id(2)), ("Recuit", None)]


def test_refusals(client):
    signup_with_microproject(client, "compose-refuse@example.com", "Marché")
    rows = _compose(client, [A, B])["rows"]
    # une étape choisie chez une source qui ne l'a pas, un mauvais nombre de choix, le substrat omis
    assert _compose(client, [A, B], [0, 0, 0, 0, 0, 1, None], status=422)["code"] == "bad_choices"
    assert _compose(client, [A, B], [0, 0], status=422)["code"] == "bad_choices"
    assert _compose(client, [A, B], [None, 0, 0, 0, 0, 0, None], status=422)["code"] == "bad_choices"
    # remplacer : vers soi-même, vers le substrat, depuis une ligne non reprise, deux fois la même
    contact, pgan = _key(rows, "Contact"), _key(rows, "p-GaN")
    for choices in (
        [0, 0, 0, 0, 0, 0, {"source": 1, "replaces": contact}],
        [0, 0, 0, 0, 0, 0, {"source": 1, "replaces": "substrat"}],
        [0, 0, 0, 0, 0, 0, {"source": None, "replaces": pgan}],
        [0, 0, 0, 0, {"source": 1, "replaces": pgan}, 0, {"source": 1, "replaces": pgan}],
    ):
        assert _compose(client, [A, B], choices, status=422)["code"] == "bad_choices"
    assert client.post("/api/compositions", json={"sources": [A]}).status_code == 422
