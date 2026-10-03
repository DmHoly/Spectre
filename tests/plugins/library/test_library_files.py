"""Les fichiers YAML de la bibliothèque racine : déclarés par leurs plugins, lus par tout compte,
modifiés par un administrateur - et validés avant d'être écrits."""

from __future__ import annotations

import pytest

from spectre.plugins.library.service import library_dir
from support.accounts import signup
from support.http import assert_handler_404, assert_ok
from support.microprojects import create_microproject
from support.process_library import list_items, names
from support.structures import deposition, substrate

FILES = ["materials", "recipes", "step-presets", "tech-bricks", "intention"]


def test_every_declared_file_is_listed_in_order(client):
    signup(client, "admin@example.com")  # le premier compte est administrateur
    files = assert_ok(client.get("/api/library/files"))
    assert [f["key"] for f in files] == FILES
    assert by_key(files, "step-presets")["filename"] == "presets.yml"
    assert all(f["can_edit"] for f in files)

    signup(client, "reader@example.com")
    assert not any(f["can_edit"] for f in assert_ok(client.get("/api/library/files")))


def by_key(files: list[dict], key: str) -> dict:
    return next(f for f in files if f["key"] == key)


def test_a_file_is_read_with_its_content(client):
    signup(client, "reader@example.com")
    detail = assert_ok(client.get("/api/library/files/materials"))
    assert detail["filename"] == "materiaux.yml"
    assert detail["exists"] is True
    assert "GaN" in detail["content"]
    assert_handler_404(client.get("/api/library/files/inconnu"))


def test_only_an_admin_saves_a_file(client):
    signup(client, "admin@example.com")
    signup(client, "reader@example.com")
    content = assert_ok(client.get("/api/library/files/materials"))["content"]
    assert client.put("/api/library/files/materials", json={"content": content}).status_code == 403


def test_an_admin_save_is_read_back_at_once(client):
    signup(client, "admin@example.com")
    yaml_text = "presets:\n  - name: Mon depot\n    kind: deposition\n    recipe: CVD Conformal\n"
    saved = assert_ok(client.put("/api/library/files/step-presets", json={"content": yaml_text}))
    assert saved["content"] == yaml_text

    assert names(list_items(client, "step-presets", scope="builtin")) == ["Mon depot"]
    assert (library_dir() / "presets.yml").read_text(encoding="utf-8") == yaml_text


@pytest.mark.parametrize(
    ("key", "content", "message"),
    [
        ("materials", "materials: [\n", "YAML invalide"),
        ("materials", "- juste une liste\n", "mapping"),
        ("materials", "autre: []\n", "'materials'"),
        ("materials", "materials:\n  - name: X\n    category: inconnue\n", "materials[0]"),
        ("step-presets", "presets:\n  - name: P\n    kind: polissage\n    recipe: X\n", "presets[0]"),
        ("step-presets", "presets:\n  - kind: etch\n    recipe: X\n", "'name'"),
        ("tech-bricks", "bricks:\n  - name: B\n    steps:\n      - kind: inconnu\n", "bricks[0]"),
        ("recipes", "etch:\n  - name: G\n    mode: nimporte\n", "etch[0]"),
    ],
)
def test_an_invalid_file_is_refused_and_nothing_is_written(client, key, content, message):
    signup(client, "admin@example.com")
    before = assert_ok(client.get(f"/api/library/files/{key}"))["content"]

    response = client.put(f"/api/library/files/{key}", json={"content": content})
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_library_file"
    assert message in response.json()["detail"]
    assert assert_ok(client.get(f"/api/library/files/{key}"))["content"] == before


def test_an_invalid_file_edited_by_hand_falls_back_to_the_builtin_set(client):
    signup(client, "reader@example.com")
    (library_dir() / "presets.yml").write_text("presets: [\n", encoding="utf-8")
    assert "MOCVD Epitaxial" in names(list_items(client, "step-presets", scope="builtin"))


def test_the_materials_and_recipes_of_the_library_reach_the_builder(client):
    signup(client, "admin@example.com")
    slug = create_microproject(client, "P")["slug"]
    assert "GZO" in [m["name"] for m in assert_ok(client.get(f"/api/microprojets/{slug}/materials"))]
    recipes = assert_ok(client.get(f"/api/microprojets/{slug}/recettes"))
    assert "Gravure sélective Al2O3" in [r["name"] for r in recipes["etch"]]

    assert_ok(
        client.put(
            "/api/library/files/materials", json={"content": "materials:\n  - name: Unobtainium\n    category: metal\n    color: '#123456'\n"}
        )
    )
    assert [m["name"] for m in assert_ok(client.get(f"/api/microprojets/{slug}/materials"))] == ["Unobtainium"]
    sim = client.post(
        f"/api/microprojets/{slug}/structures/simulate",
        json={"substrate": substrate(), "steps": [deposition("Couche", "Unobtainium", thickness_nm=10)]},
    )
    assert sim.status_code == 200
