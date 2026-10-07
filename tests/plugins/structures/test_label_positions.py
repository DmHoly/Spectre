"""Placer une étiquette de couche à la main : son texte, glissé sur le dessin du constructeur, garde
de combien il a quitté sa place automatique (``LayerLabel.offset``, en unités du dessin). Le
serveur le dessine là, le trait le suit, le cadre s'agrandit pour le contenir ; la place est
enregistrée avec l'étiquette mais ne change pas la version de la structure."""

from __future__ import annotations

import re

from support.accounts import signup
from support.experiments import evolve, launch, process, versions
from support.microprojects import signup_with_microproject
from support.structures import deposition, identified, label_texts, layer_label, simulate, substrate

STACK = [
    deposition("n-GaN", "GaN", recipe="MOCVD Epitaxial", thickness_nm=400),
    deposition("p-GaN", "GaN", recipe="MOCVD Epitaxial", thickness_nm=150),
]


def _svg(client, labels: dict) -> str:
    response = simulate(client, {"substrate": substrate("Sapphire", width_nm=1000, thickness_nm=300), "steps": STACK, "layer_labels": labels})
    assert response.status_code == 200, response.text
    return response.json()["frames"][-1]["svg"]


def _label(svg: str, step: int) -> dict:
    """Ce que dessine l'étiquette de l'étape ``step`` : le x de son texte, son haut, son trait."""
    group = re.search(rf'<g class="sp-layer-label" data-top="([-\d.]+)"[^>]* data-step="{step}"[^>]*>(.*?)</g></g>', svg, re.S)
    assert group, svg
    return {
        "top": float(group.group(1)),
        "x": float(re.search(r'<text x="([-\d.]+)"', group.group(2)).group(1)),
        "leader": re.search(r'points="([^"]+)" class="sp-layer-leader"', group.group(2)).group(1),
        "offset": re.search(r'data-offset="([^"]+)"', group.group(0)),
    }


def _viewbox(svg: str) -> list[float]:
    return [float(v) for v in re.match(r'<svg[^>]* viewBox="([^"]+)"', svg).group(1).split()]


def test_a_moved_label_is_drawn_where_it_was_put_and_its_line_follows(client):
    signup(client, "move-label@example.com")
    auto = _svg(client, {"0": layer_label("n"), "1": layer_label("p")})
    moved = _svg(client, {"0": layer_label("n"), "1": {**layer_label("p"), "offset": [30, 25]}})
    before, after = _label(auto, 1), _label(moved, 1)
    assert (after["x"] - before["x"], after["top"] - before["top"]) == (30, 25)
    assert after["offset"].group(1) == "30 25" and before["offset"] is None
    # le trait part du même point de la couche et finit au texte déplacé
    assert after["leader"].split()[0] == before["leader"].split()[0]
    assert after["leader"].split()[-1] != before["leader"].split()[-1]
    # l'autre étiquette n'a pas bougé
    assert _label(moved, 0)["x"] == _label(auto, 0)["x"]
    assert label_texts(moved) == label_texts(auto)


def test_a_label_moved_out_of_the_frame_grows_it_and_a_null_move_is_no_move(client):
    signup(client, "grow-label@example.com")
    auto = _svg(client, {"1": layer_label("p")})
    moved = _svg(client, {"1": {**layer_label("p"), "offset": [-600, -300]}})
    x, y, width, height = _viewbox(moved)
    assert x < 0 and y < 0 and width >= _viewbox(auto)[2]
    # posé à gauche du point d'accroche : le trait va droit au bord droit du texte, sans coude
    assert len(_label(moved, 1)["leader"].split()) == 2
    # la vue sans étiquettes reste celle du dessin seul
    assert re.search(r'data-bare-viewbox="([^"]+)"', moved).group(1) == re.search(r'data-bare-viewbox="([^"]+)"', auto).group(1)
    assert _svg(client, {"1": {**layer_label("p"), "offset": [0, 0]}}) == auto


def test_a_move_out_of_bounds_is_refused(client):
    signup(client, "bounds-label@example.com")
    body = {"substrate": substrate(), "steps": STACK}
    for offset in ([5000, 0], [0, -2001], [1], "loin"):
        response = simulate(client, {**body, "layer_labels": {"0": {**layer_label("x"), "offset": offset}}})
        assert response.status_code == 422, offset


def test_the_place_of_a_label_is_recorded_without_changing_the_version(client):
    slug = signup_with_microproject(client, "place-label@example.com", "Places")
    steps = identified(STACK)
    study = launch(client, slug, steps=steps, layer_labels={"1": layer_label("p", "thickness")})
    placed = {"1": {**layer_label("p", "thickness"), "offset": [12.5, -8]}}
    moved = evolve(client, slug, study["id"], title="Essai", intent="Placer", steps=steps, layer_labels=placed)
    assert 'data-offset="12.5 -8"' in moved["structure_svg"]
    assert process(client, slug, study["id"])["layer_labels"]["1"] == {"text": "p", "values": ["thickness"], "offset": [12.5, -8]}
    assert [v["change_level"] for v in versions(client, slug, study["id"])] == ["initial", "none"]
