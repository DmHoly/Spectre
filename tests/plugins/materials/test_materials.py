"""Éditer les matériaux de l'instance depuis la page : le document (matériaux du sélecteur, dégradés de
couleur de l'InGaN et de l'AlGaN), son enregistrement dans ``materiaux.yml`` - validé, sans écraser une
modification faite entre-temps - et ce que le constructeur et le rendu en voient."""

from __future__ import annotations

import yaml
from structureforge.core.materials import indium_gan

from spectre.plugins.library import service as library
from spectre.plugins.structures import library_files, simulation
from support.accounts import signup
from support.materials import editable, material_library, saved, two_stops


def _admin(client) -> dict:
    signup(client, "admin@example.com")
    return material_library(client)


def _rejected(client, document: dict, message: str) -> None:
    response = client.put("/api/material-library", json=document)
    assert response.status_code == 422, response.text
    assert message in response.json()["detail"]


def test_the_document_is_the_materials_and_the_gradients_of_the_file(client):
    document = _admin(client)
    names = [m["name"] for m in document["materials"]]
    assert names[:3] == ["Si", "Sapphire", "SiC"] and "GaN" in names
    assert set(document["gradients"]) == {"InGaN", "AlGaN"}
    assert document["gradients"]["AlGaN"] == two_stops("#d01c8b", "#f6c8e0", 0.3)
    assert document["can_edit"] is True and document["problem"] is None
    # StructureForge en connaît d'autres : on propose ceux qui ne sont pas déjà dans la liste
    available = {m["name"] for m in document["available"]}
    assert "Au" in available and not available & set(names) and not available & {"InGaN", "AlGaN"}


def test_the_shipped_file_carries_the_builtin_gradients(client):
    """Le fichier livré et le repli du code disent la même chose : on peut repartir de l'un ou de l'autre."""
    shipped = library.parse_text(library.get_library_file("materials"), (library.DEFAULTS_DIR / "materiaux.yml").read_text(encoding="utf-8"))
    assert shipped.gradients == library_files.builtin_gradients()


def test_a_file_from_before_the_gradients_keeps_the_builtin_ones(client):
    signup(client, "admin@example.com")
    (library.library_dir() / "materiaux.yml").write_text("materials:\n  - name: GaN\n    category: semiconductor\n", encoding="utf-8")
    assert library_files.gradient("InGaN") == library_files.builtin_gradients()["InGaN"]
    assert material_library(client)["problem"] is None


def test_an_invalid_file_is_shown_by_the_builtin_set_with_its_problem(client):
    signup(client, "admin@example.com")
    (library.library_dir() / "materiaux.yml").write_text("materials:\n  - name: X\n    category: inconnue\n", encoding="utf-8")
    document = material_library(client)
    assert "materials[0]" in document["problem"]
    assert "GaN" in [m["name"] for m in document["materials"]]
    saved(client, editable(document))  # l'enregistrer répare le fichier
    assert material_library(client)["problem"] is None


def test_a_reader_sees_the_document_but_cannot_save_it(client):
    signup(client, "admin@example.com")
    signup(client, "reader@example.com")
    document = material_library(client)
    assert document["can_edit"] is False
    assert client.put("/api/material-library", json=editable(document)).status_code == 403


def test_a_saved_document_is_written_to_the_file_and_read_back(client):
    document = _admin(client)
    gan = next(m for m in document["materials"] if m["name"] == "GaN")
    gan.update(notes="Nitrure de gallium : l'« hôte » - 100 % pur: oui #fort", color="#112233", density_g_cm3=6.15)
    document["materials"].append({"name": "Au", "category": "metal", "color": "#e6c260", "density_g_cm3": None, "refractive_index": None, "notes": None})
    document["materials"].reverse()
    document["gradients"]["InGaN"]["stops"][0]["color"] = "#ABCDEF"

    reread = saved(client, editable(document))

    assert [m["name"] for m in reread["materials"]] == [m["name"] for m in document["materials"]]
    gan = next(m for m in reread["materials"] if m["name"] == "GaN")
    assert gan["notes"] == "Nitrure de gallium : l'« hôte » - 100 % pur: oui #fort" and gan["color"] == "#112233"
    assert reread["gradients"]["InGaN"]["stops"][0]["color"] == "#abcdef"
    assert reread["revision"] != document["revision"]
    assert "Au" not in {m["name"] for m in reread["available"]}
    # ce que lit l'application, c'est le fichier
    assert [m.name for m in library_files.materials()] == [m["name"] for m in document["materials"]]
    text = (library.library_dir() / "materiaux.yml").read_text(encoding="utf-8")
    assert text.startswith("# Bibliothèque de matériaux Spectre") and "\ngradients:\n" in text
    assert yaml.safe_load(text)["materials"][0]["name"] == "Au"


def test_the_comment_header_of_the_file_survives_a_save(client):
    _admin(client)
    path = library.library_dir() / "materiaux.yml"
    body = path.read_text(encoding="utf-8").split("\nmaterials:", 1)[1]
    path.write_text("# Notes de l'équipe\n# deuxième ligne\n\nmaterials:" + body, encoding="utf-8")

    saved(client, editable(material_library(client)))

    assert path.read_text(encoding="utf-8").startswith("# Notes de l'équipe\n# deuxième ligne\n\nmaterials:")


def test_a_save_based_on_an_older_revision_is_refused(client):
    document = _admin(client)
    saved(client, editable({**document, "materials": document["materials"][:-1]}))

    response = client.put("/api/material-library", json=editable(document))
    assert response.status_code == 409 and response.json()["code"] == "library_file_changed"
    assert len(material_library(client)["materials"]) == len(document["materials"]) - 1


def test_an_invalid_document_is_refused_and_nothing_is_written(client):
    document = _admin(client)
    path = library.library_dir() / "materiaux.yml"
    before = path.read_text(encoding="utf-8")
    base = editable(document)

    def with_material(**changes) -> dict:
        return {**base, "materials": [*base["materials"], {"name": "Test", "category": "metal", "color": "#123456", **changes}]}

    def with_gradient(family: str, gradient: dict) -> dict:
        return {**base, "gradients": {**base["gradients"], family: gradient}}

    _rejected(client, {**base, "materials": []}, "ne peut pas être vide")
    _rejected(client, with_material(name="gan"), "déjà présent")
    _rejected(client, with_material(name=""), "le nom est obligatoire")
    _rejected(client, with_material(name="InGaN"), "nitrures à composition")
    _rejected(client, with_material(name="In0.20Ga0.80N"), "nitrures à composition")
    _rejected(client, with_material(color="rouge"), "#rrggbb")
    _rejected(client, with_material(category="plasma"), "catégorie inconnue")
    _rejected(client, with_material(density_g_cm3=-1), "densité")
    _rejected(client, with_material(refractive_index="beaucoup"), "indice de réfraction")
    _rejected(client, with_gradient("AlGaN", {"stops": [{"x": 0, "color": "#000000"}], "generic_x": 0.3}), "au moins deux couleurs")
    _rejected(client, with_gradient("AlGaN", two_stops("#000000", "#ffffff", generic_x=1.5)), "taux du nom nu")
    _rejected(client, with_gradient("InGaN", {"stops": [{"x": 0, "color": "#000000"}, {"x": 1.2, "color": "#ffffff"}], "generic_x": 0.1}), "entre 0 et 1")
    _rejected(client, {**base, "gradients": {"InGaN": base["gradients"]["InGaN"]}}, "deux familles")
    assert path.read_text(encoding="utf-8") == before


def test_the_gradient_of_the_file_colours_the_compositions(client):
    document = _admin(client)
    document["gradients"]["AlGaN"] = two_stops("#000000", "#ffffff", generic_x=0.5)
    document["gradients"]["InGaN"] = {"stops": [{"x": 0.4, "color": "#ff0000"}, {"x": 0.0, "color": "#0000ff"}], "generic_x": 0.2}
    saved(client, editable(document))

    colours = {m.name: m.color for m in simulation.materials_library("Al0.50Ga0.50N", "Al0.20Ga0.80N", "In0.20Ga0.80N", "In0.90Ga0.10N")}
    assert colours["Al0.50Ga0.50N"] == "#808080"
    assert colours["Al0.20Ga0.80N"] == "#333333"
    assert colours["In0.20Ga0.80N"] == "#800080"  # à mi-chemin du bleu et du rouge (les points sont triés)
    assert colours["In0.90Ga0.10N"] == "#ff0000"  # au-delà du dernier point
    # le nom nu prend la couleur du taux que le fichier lui donne
    assert colours["AlGaN"] == "#808080" and colours["InGaN"] == "#800080"


def test_the_untouched_file_colours_the_compositions_as_structureforge_and_before(client):
    signup(client, "reader@example.com")
    colours = {m.name: m.color for m in simulation.materials_library("In0.20Ga0.80N", "Al0.20Ga0.80N")}
    assert colours["In0.20Ga0.80N"] == indium_gan(0.2).color
    assert colours["Al0.20Ga0.80N"] == "#d83e9c"  # le magenta vers le rose pâle, à 20 % d'aluminium


def test_the_page_is_served_and_belongs_to_the_structure_menu(client):
    signup(client, "reader@example.com")
    page = client.get("/materiaux")
    assert page.status_code == 200 and "materials.js" in page.text
    assert 'href="/materiaux"' in client.get("/bibliotheque").text
