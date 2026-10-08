"""Placer une étiquette de couche à la main : son texte, glissé sur le dessin du constructeur, garde
de combien il a quitté sa place automatique (``LayerLabel.offset``, en unités du dessin). Le
serveur le dessine là, le trait le suit, le cadre s'agrandit pour le contenir ; la place est
enregistrée avec l'étiquette mais ne change pas la version de la structure.
Son point d'accroche aussi se pose à la main (``LayerLabel.anchor``, en fractions du cadre de ce
qu'il désigne) : il suit sa couche quand elle change, il y est ramené s'il en sort (sur la surface
pour une marque d'interface), et seul le trait le suit - aucun texte ne bouge."""

from __future__ import annotations

import re

from support.accounts import signup
from support.experiments import evolve, launch, process, structure_diff, versions
from support.microprojects import signup_with_microproject
from support.structures import deposition, etch, identified, label_texts, layer_label, lithography, simulate, substrate

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


# -- le point d'accroche posé à la main ------------------------------------------------------------


def _group(svg: str, step: int) -> str:
    return re.search(rf'<g class="sp-layer-label"[^>]* data-step="{step}"[^>]*>', svg).group(0)


def _anchor_of(svg: str, step: int) -> tuple[float, float]:
    x, y = re.search(r'data-anchor="([^"]+)"', _group(svg, step)).group(1).split()
    return float(x), float(y)


def _box(svg: str, step: int) -> list[float]:
    return [float(v) for v in re.search(r'data-anchor-box="([^"]+)"', _group(svg, step)).group(1).split()]


def _texts(svg: str) -> list:
    """La place de chaque texte d'étiquette : le haut de chaque étiquette, le x et le y de chaque ligne."""
    return re.findall(r'<g class="sp-layer-label" data-top="([-\d.]+)"', svg) + re.findall(r'<text x="([-\d.]+)" y="([-\d.]+)"', svg)


def test_a_placed_anchor_is_drawn_where_it_was_put_and_only_the_line_follows(client):
    signup(client, "anchor-label@example.com")
    auto = _svg(client, {"0": layer_label("n"), "1": layer_label("p")})
    placed = _svg(client, {"0": layer_label("n"), "1": {**layer_label("p"), "anchor": [0.25, 0.1]}})
    x0, y0, x1, y1 = _box(placed, 1)
    ax, ay = _anchor_of(placed, 1)
    # le cadre va du haut à gauche au bas à droite ; le point, à un quart de la largeur, tout en haut
    assert x0 < x1 and y0 < y1
    assert abs(ax - (x0 + 0.25 * (x1 - x0))) < 0.2 and abs(ay - (y0 + 0.1 * (y1 - y0))) < 0.2
    assert 'data-anchor-placed="0.25 0.1"' in _group(placed, 1) and "data-anchor-placed" not in auto
    # le cadre est celui de la couche, le même avec ou sans point posé ; le point a changé de hauteur
    assert _box(auto, 1) == _box(placed, 1) and _anchor_of(auto, 1)[1] != ay
    # le trait part du point posé ; aucun texte n'a bougé, l'autre étiquette est intacte
    after = _label(placed, 1)
    assert after["leader"].split()[0] == re.search(r'data-anchor="([^"]+)"', _group(placed, 1)).group(1).replace(" ", ",")
    assert _texts(placed) == _texts(auto)
    assert _label(placed, 0)["leader"] == _label(auto, 0)["leader"] and _anchor_of(placed, 0) == _anchor_of(auto, 0)
    # le point et la zone où l'attraper (inerte hors du constructeur) vont ensemble
    assert placed.count('class="sp-layer-anchor"') == 2 and 'class="sp-layer-anchor__hit"' in placed
    assert 'pointer-events="none"' in placed


def test_a_placed_anchor_follows_its_layer_when_the_structure_changes(client):
    signup(client, "anchor-follow@example.com")
    boxes = []
    for n_thickness in (400, 900):
        steps = [deposition("n-GaN", "GaN", recipe="MOCVD Epitaxial", thickness_nm=n_thickness), STACK[1]]
        body = {"substrate": substrate("Sapphire", width_nm=1000, thickness_nm=300), "steps": steps}
        response = simulate(client, {**body, "layer_labels": {"1": {**layer_label("p"), "anchor": [0.5, 0.5]}}})
        assert response.status_code == 200, response.text
        svg = response.json()["frames"][-1]["svg"]
        x0, y0, x1, y1 = _box(svg, 1)
        ax, ay = _anchor_of(svg, 1)
        assert abs(ax - (x0 + x1) / 2) < 0.2 and abs(ay - (y0 + y1) / 2) < 0.2
        boxes.append((y0, y1))
    # la couche n'est plus au même endroit du dessin, le point est toujours en son milieu
    assert boxes[0] != boxes[1]


def test_a_point_put_off_its_layer_is_brought_back_onto_it():
    import math

    from shapely.geometry import Point, Polygon, box
    from shapely.ops import unary_union

    from spectre.plugins.structures import rendering

    def placed(shape, fractions):
        return rendering._placed_anchor(shape, rendering._at_fractions(shape.bounds, fractions), inset=2)

    # une couche en L : le coin en haut à droite de son cadre n'est pas sur elle - ramené dedans,
    # en retrait du bord du rayon du point
    ell = Polygon([(0, 0), (100, 0), (100, 20), (20, 20), (20, 100), (0, 100)])
    x, y = placed(ell, (1.0, 0.0))
    assert ell.contains(Point(x, y)) and ell.exterior.distance(Point(x, y)) >= 2 - 1e-6
    # sur la couche, il reste où il a été posé (de gauche à droite, de haut en bas)
    x, y = placed(ell, (0.5, 0.9))
    assert abs(x - 50) < 1e-6 and abs(y - 10) < 1e-6
    # une couche trop fine pour que le point y tienne : posé sur son bord
    thin = Polygon([(0, 0), (100, 0), (100, 1), (1, 1), (1, 100), (0, 100)])
    assert thin.covers(Point(*placed(thin, (1.0, 0.0))))
    # épaisse par endroits, fine ailleurs (une coquille facettée) : posé à côté de la partie fine, il
    # y reste - il ne saute pas sur la partie épaisse, loin de là
    shell = unary_union([box(0, 90, 40, 100), box(40, 0, 41, 100), box(41, 0, 100, 1)])
    assert math.dist(placed(shell, (0.9, 0.97)), (90, 3)) <= 2 * 2 + 0.01


def test_a_placed_interface_point_lands_on_the_surface_never_on_the_edges_of_the_domain():
    from shapely.geometry import box
    from shapely.ops import unary_union

    from spectre.plugins.structures import rendering

    # un substrat et un plot : posé à gauche du plot, le point va sur son flanc
    below = unary_union([box(0, 0, 100, 50), box(40, 50, 60, 90)])

    def placed(fractions):
        return rendering._placed_interface_anchor(below, rendering._at_fractions(below.bounds, fractions), below.bounds)

    x, y = placed((0.35, 0.3))
    assert abs(x - 40) < 1e-6 and abs(y - 63) < 1e-6
    # posé dans le coin du bas, il remonte sur le dessus du substrat - ni sur le côté ni sur le fond
    x, y = placed((0.0, 1.0))
    assert abs(y - 50) < 1e-6 and 0 < x < 40


def test_a_placed_interface_mark_is_drawn_on_the_surface_it_points_at(client):
    signup(client, "anchor-interface@example.com")
    clean = {"kind": "chemical", "name": "Clean HF", "description": "bain HF", "parameters": {}}
    steps = [deposition("GaN", "GaN", recipe="MOCVD Epitaxial", thickness_nm=200), clean, deposition("AlN", "AlN", recipe="MOCVD Epitaxial", thickness_nm=50)]

    def svg_of(label: dict) -> str:
        response = simulate(client, {"substrate": substrate("Sapphire", width_nm=400, thickness_nm=100), "steps": steps, "layer_labels": {"1": label}})
        assert response.status_code == 200, response.text
        return response.json()["frames"][-1]["svg"]

    auto, placed = svg_of(layer_label("Clean")), svg_of({**layer_label("Clean"), "anchor": [0.25, 0.9]})
    x0, _y0, x1, _y1 = _box(placed, 1)
    (_ax, ay), (px, py) = _anchor_of(auto, 1), _anchor_of(placed, 1)
    # posé dans le substrat, il remonte sur la surface où le nettoyage a eu lieu (le haut du GaN)
    assert abs(py - ay) < 0.5 and abs(px - (x0 + 0.25 * (x1 - x0))) < 0.5
    assert 'data-interface="true"' in _group(placed, 1) and "data-anchor-placed" in _group(placed, 1)


def test_a_brick_label_has_no_point_to_place(client):
    signup(client, "anchor-brick@example.com")
    brick = {"group_id": "b1", "name": "Diode", "step_indexes": [0, 1]}
    labels = {str(i): {**layer_label("", "thickness"), "anchor": [0.1, 0.1]} for i in (0, 1)}
    body = {"substrate": substrate("Sapphire", width_nm=1000, thickness_nm=300), "steps": STACK, "layer_labels": labels, "bricks": [brick]}
    response = simulate(client, body)
    assert response.status_code == 200, response.text
    svg = response.json()["frames"][-1]["svg"]
    # l'accolade est son point : rien à déplacer, le point posé sur une étape de la brique est ignoré
    assert "sp-layer-bracket" in svg and "sp-layer-anchor" not in svg
    assert "data-anchor-box" not in svg and "data-anchor-placed" not in svg


def test_an_anchor_out_of_its_frame_is_refused(client):
    signup(client, "anchor-bounds@example.com")
    body = {"substrate": substrate(), "steps": STACK}
    for anchor in ([1.2, 0], [0.5, -0.1], [0.5], "milieu", [0.5, 0.5, 0.5]):
        response = simulate(client, {**body, "layer_labels": {"0": {**layer_label("x"), "anchor": anchor}}})
        assert response.status_code == 422, anchor


def test_the_place_of_a_label_is_not_what_it_says():
    from spectre.plugins.structures.simulation import LayerLabel, label_without_place

    label = LayerLabel(text="p", values=["thickness"], offset=(3, 4), anchor=(0.1234, 1)).model_dump(mode="json")
    assert label == {"text": "p", "values": ["thickness"], "offset": [3, 4], "anchor": [0.123, 1]}
    assert label_without_place(label) == {"text": "p", "values": ["thickness"]}
    # une étiquette à sa place s'enregistre comme avant : {text, values}
    assert LayerLabel(text="p").model_dump(mode="json") == {"text": "p", "values": []}


def test_the_anchor_of_a_label_is_recorded_without_changing_the_version(client):
    slug = signup_with_microproject(client, "anchor-version@example.com", "Accroches")
    steps = identified(STACK)
    study = launch(client, slug, steps=steps, layer_labels={"1": layer_label("p", "thickness")})
    placed = {"1": {**layer_label("p", "thickness"), "anchor": [0.2, 0.75]}}
    moved = evolve(client, slug, study["id"], title="Essai", intent="Placer", steps=steps, layer_labels=placed)
    assert 'data-anchor-placed="0.2 0.75"' in moved["structure_svg"]
    assert process(client, slug, study["id"])["layer_labels"]["1"] == {"text": "p", "values": ["thickness"], "anchor": [0.2, 0.75]}
    assert [v["change_level"] for v in versions(client, slug, study["id"])] == ["initial", "none"]
    # ni une différence d'étiquette
    assert structure_diff(client, slug, study["id"], version=moved["version_id"], against_version=study["version_id"])["label_changes"] == []


def test_a_point_put_off_a_layer_is_drawn_back_on_it(client):
    """Un oxyde conforme sur un plot de résine : posé dans la résine, le point remonte dans l'oxyde
    qui la couvre, rentré du rayon du point."""
    from spectre.plugins.structures import rendering

    signup(client, "anchor-snap@example.com")
    steps = [lithography("Masque", thickness_nm=40, openings=[(0, 70), (130, 200)]), deposition("Ox", "SiO2", recipe="CVD Conformal", thickness_nm=10)]
    response = simulate(client, {"substrate": substrate("Si", width_nm=200, thickness_nm=50), "steps": steps, "layer_labels": {"1": {**layer_label("ox"), "anchor": [0.5, 0.6]}}})
    assert response.status_code == 200, response.text
    svg = response.json()["frames"][-1]["svg"]
    x0, y0, x1, y1 = _box(svg, 1)
    ax, ay = _anchor_of(svg, 1)
    film = (y1 - y0) / 5  # 10 nm d'oxyde sur un cadre de 50 nm (40 de résine + 10)
    assert abs(ax - (x0 + x1) / 2) < 0.2
    assert abs(ay - (y0 + 0.6 * (y1 - y0))) > 1  # ramené
    assert abs(ay - (y0 + film - rendering.ANCHOR_DOT)) < 0.3  # dans l'oxyde au-dessus de la résine


def test_a_placed_point_lands_at_the_same_place_on_every_frame(client):
    """Le point se pose dans le cadre de la couche sur la structure finale, quelle que soit l'image
    affichée : posé sur le GaN juste après son dépôt (qu'une gravure réduira), il est au même
    endroit sur la structure finale."""
    signup(client, "anchor-frames@example.com")
    steps = [
        deposition("GaN", "GaN", recipe="MOCVD Epitaxial", thickness_nm=60),
        lithography("Masque", thickness_nm=40, openings=[(140, 200)]),
        etch("Gravure", recipe="Anisotropic RIE", depth_nm=60),
        {"kind": "resist_strip", "name": "Retrait", "material": "Photoresist"},
    ]
    response = simulate(client, {"substrate": substrate("Si", width_nm=200, thickness_nm=50), "steps": steps, "layer_labels": {"0": {**layer_label("GaN"), "anchor": [0.5, 0.5]}}})
    assert response.status_code == 200, response.text
    frames = response.json()["frames"]

    def fractions(svg: str) -> tuple[float, float]:
        x0, y0, x1, y1 = _box(svg, 0)
        ax, ay = _anchor_of(svg, 0)
        return round((ax - x0) / (x1 - x0), 2), round((ay - y0) / (y1 - y0), 2)

    after_deposition, final = frames[1]["svg"], frames[-1]["svg"]
    assert fractions(after_deposition) == fractions(final) == (0.5, 0.5)
    # le cadre est celui de la structure finale (le GaN gravé), sur les deux images - à la même
    # échelle : le domaine a la même largeur sur l'une et l'autre
    assert _box(after_deposition, 0) == _box(final, 0)


def test_after_a_flip_a_mark_can_be_put_on_the_interface_it_points_at(client):
    """Retournée, la structure a l'interface d'un nettoyage d'avant sous les couches d'avant lui :
    le losange s'y pose (le fond de ces couches n'est pas le fond du dessin). Avant le
    retournement, le point posé n'est ni suivi ni déplaçable."""
    signup(client, "anchor-flip@example.com")
    clean = {"kind": "chemical", "name": "Clean HF", "description": "bain HF", "parameters": {}}
    steps = [
        deposition("GaN", "GaN", recipe="MOCVD Epitaxial", thickness_nm=100),
        clean,
        deposition("AlN", "AlN", recipe="MOCVD Epitaxial", thickness_nm=50),
        {"kind": "flip", "name": "Retournement"},
        deposition("Ox", "SiO2", thickness_nm=20),
    ]
    body = {"substrate": substrate("Sapphire", width_nm=400, thickness_nm=50), "steps": steps}
    response = simulate(client, {**body, "layer_labels": {"1": {**layer_label("Clean"), "anchor": [0.75, 1.0]}}})
    assert response.status_code == 200, response.text
    frames = response.json()["frames"]
    final = frames[-1]["svg"]
    _x0, y0, _x1, y1 = _box(final, 1)
    _ax, ay = _anchor_of(final, 1)
    assert abs(ay - y1) < 0.5 and abs(ay - y0) > 10  # sur l'interface GaN/AlN, au fond de son cadre
    before_flip = frames[2]["svg"]
    assert "data-anchor-box" not in _group(before_flip, 1) and "data-anchor-placed" not in _group(before_flip, 1)
