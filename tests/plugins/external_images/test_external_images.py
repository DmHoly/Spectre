"""Galerie d'images externes (plugin external_images) : des jeux d'images référencées à leur
emplacement d'origine sur le disque du serveur, jamais copiées. Chaque écriture passe par la piste
(``If-Match``, hypothèse conservée) ; l'accès au disque est borné aux racines de
``SPECTRE_EXTERNAL_IMAGE_ROOTS``, et une image se lit par son jeu et son rang, jamais par un chemin
reçu du client."""

from __future__ import annotations

import pathlib

import pytest

from spectre.plugins.experiments import service as experiments
from spectre.plugins.external_images import service

from support.accounts import login, signup
from support.experiments import get_experiment, launch, launch_campaign, tag, versions
from support.external_images import (
    browse,
    create_image_set,
    delete_image_set,
    get_image,
    image_sets,
    patch_image_set,
    pin_image,
    png_files,
    post_image_set,
)
from support.http import PNG_1PX, ROUTER_NOT_FOUND, assert_handler_404
from support.microprojects import add_member, signup_with_microproject


@pytest.fixture()
def root(tmp_path, monkeypatch):
    """Le dossier autorisé (``SPECTRE_EXTERNAL_IMAGE_ROOTS``) - un autre dossier, à côté, ne l'est pas."""
    allowed = tmp_path / "mesures"
    allowed.mkdir()
    monkeypatch.setenv("SPECTRE_EXTERNAL_IMAGE_ROOTS", str(allowed))
    return allowed


@pytest.fixture()
def no_roots(monkeypatch):
    monkeypatch.delenv("SPECTRE_EXTERNAL_IMAGE_ROOTS", raising=False)


def _setup(client, email="gallery@example.com"):
    slug = signup_with_microproject(client, email, "Mesures", name="Ada")
    line = launch(client, slug, title="Recuit", intent="Voir la coupe", hypothesis="Le puits fait 3 nm")["id"]
    return slug, line


def _legacy_set(slug, line, paths):
    """Un jeu écrit avant ces règles (un chemin qu'on ne pourrait plus enregistrer) - directement
    dans les métadonnées de l'étude."""
    record = {"id": "data_" + "0" * 20, "title": None, "note": None, "entity_index": None, "image_paths": paths, "pinned_index": 0}
    experiments.amend(slug, line, author="Ada", change=lambda builder, parent: builder.metadata.update({service.IMAGE_SETS_KEY: [record]}))
    return record["id"]


def test_an_image_set_is_created_pinned_read_and_removed(client, root):
    slug, line = _setup(client)
    paths = png_files(root, "tem-1.png", "tem-2.png")
    response = post_image_set(client, slug, line, paths, title="Coupe TEM", note="centre")
    assert response.status_code == 201
    created = response.json()
    tip = get_experiment(client, slug, line)
    assert response.headers["ETag"] == f'"{tip["version_id"]}"'
    assert created["title"] == "Coupe TEM" and created["pinned_index"] == 0 and created["created_by"] == "Ada"
    base = f"/api/microprojects/{slug}/experiments/{line}/image-sets/{created['id']}/images"
    assert [(i["name"], i["status"], i["url"]) for i in created["images"]] == [
        ("tem-1.png", "ok", f"{base}/0"),
        ("tem-2.png", "ok", f"{base}/1"),
    ]
    assert image_sets(client, slug, line) == [created]
    # le détail de l'étude ne porte plus la galerie : le panneau lit sa propre ressource
    assert "data_items" not in tip

    image = client.get(created["images"][1]["url"])
    assert image.status_code == 200 and image.content == PNG_1PX and image.headers["content-type"] == "image/png"

    pinned = pin_image(client, slug, line, created["id"], 1)
    assert pinned["pinned_index"] == 1 and image_sets(client, slug, line) == [pinned]
    count = len(versions(client, slug, line))
    assert pin_image(client, slug, line, created["id"], 1) == pinned  # sans effet : pas de version
    assert len(versions(client, slug, line)) == count

    removed = delete_image_set(client, slug, line, created["id"])
    assert removed.status_code == 204 and removed.content == b""
    assert image_sets(client, slug, line) == []
    # une version passée garde son jeu, et ses images se lisent sur elle
    old = image_sets(client, slug, line, version=tip["version_id"])
    assert [s["id"] for s in old] == [created["id"]] and old[0]["images"][0]["url"].endswith(f"?version={tip['version_id']}")
    assert client.get(old[0]["images"][0]["url"]).content == PNG_1PX
    assert_handler_404(get_image(client, slug, line, created["id"], 0), "introuvable")


def test_every_write_keeps_the_hypothesis(client, root):
    slug, line = _setup(client)
    created = create_image_set(client, slug, line, png_files(root))
    pin_image(client, slug, line, created["id"], 1)
    delete_image_set(client, slug, line, created["id"])
    assert len(versions(client, slug, line)) == 4
    assert get_experiment(client, slug, line)["hypothesis"] == "Le puits fait 3 nm"


def test_a_stale_if_match_is_refused_on_every_write(client, root):
    slug, line = _setup(client)
    paths = png_files(root)
    created = create_image_set(client, slug, line, paths)
    shown = get_experiment(client, slug, line)["version_id"]
    tag(client, slug, line, ["ailleurs"])  # quelqu'un d'autre a écrit entre-temps
    refused = [
        post_image_set(client, slug, line, paths, if_match=shown),
        patch_image_set(client, slug, line, created["id"], 1, if_match=shown),
        delete_image_set(client, slug, line, created["id"], if_match=shown),
    ]
    assert [(r.status_code, r.json()["code"]) for r in refused] == [(412, "stale_version")] * 3
    assert image_sets(client, slug, line) == [created]
    current = get_experiment(client, slug, line)["version_id"]
    assert pin_image(client, slug, line, created["id"], 1, if_match=current)["pinned_index"] == 1


def test_a_set_is_validated(client, root):
    slug, line = _setup(client)
    paths = png_files(root)
    assert post_image_set(client, slug, line, []).status_code == 422
    assert post_image_set(client, slug, line, paths, pinned_index=2).json()["code"] == "pinned_index_out_of_range"
    assert post_image_set(client, slug, line, ["mesures/tem-1.png"]).json()["code"] == "relative_path"
    assert post_image_set(client, slug, line, [str(root / "absente.png")]).json()["code"] == "file_not_found"
    (root / "notes.txt").write_text("pas une image", encoding="utf-8")
    assert post_image_set(client, slug, line, [str(root / "notes.txt")]).json()["code"] == "not_an_image"
    # une seule variante sur une étude qui n'est pas une campagne
    assert post_image_set(client, slug, line, paths, entity_index=1).json()["code"] == "entity_not_found"
    created = create_image_set(client, slug, line, paths)
    assert patch_image_set(client, slug, line, created["id"], 5).status_code == 422
    assert_handler_404(patch_image_set(client, slug, line, "data_inconnu", 0), "introuvable")
    assert_handler_404(delete_image_set(client, slug, line, "data_inconnu"), "introuvable")


def test_a_set_can_target_one_variant_of_a_campaign(client, root):
    slug = signup_with_microproject(client, "campaign-gallery@example.com")
    line = launch_campaign(client, slug, entities=[{"sample_id": f"W{i}"} for i in range(3)])["id"]
    assert create_image_set(client, slug, line, png_files(root), entity_index=2)["entity_index"] == 2
    assert post_image_set(client, slug, line, png_files(root), entity_index=3).status_code == 422


def test_a_tiff_is_refused_with_a_clear_message(client, root):
    slug, line = _setup(client)
    (root / "coupe.tif").write_bytes(b"II*\x00")
    response = post_image_set(client, slug, line, [str(root / "coupe.tif")])
    assert response.status_code == 422 and response.json()["code"] == "unsupported_format"
    assert "TIFF" in response.json()["detail"] and "PNG" in response.json()["detail"]


def test_an_image_that_cannot_be_shown_says_why(client, root):
    slug, line = _setup(client)
    (root / "ancienne.tiff").write_bytes(b"II*\x00")
    moved, kept = png_files(root, "deplacee.png", "gardee.png")
    set_id = _legacy_set(slug, line, [str(root / "ancienne.tiff"), moved, kept])
    pathlib.Path(moved).unlink()

    statuses = [i["status"] for i in image_sets(client, slug, line)[0]["images"]]
    assert statuses == ["unsupported", "missing", "ok"]
    assert get_image(client, slug, line, set_id, 0).json()["code"] == "unsupported_format"
    missing = get_image(client, slug, line, set_id, 1)
    assert_handler_404(missing, "déplacé")
    assert missing.json()["code"] == "image_missing"
    assert get_image(client, slug, line, set_id, 2).status_code == 200


def test_a_path_outside_the_roots_is_refused(client, root, tmp_path):
    slug, line = _setup(client)
    outside = png_files(tmp_path / "ailleurs", "secret.png")[0]
    response = post_image_set(client, slug, line, [outside])
    assert response.status_code == 403 and response.json()["code"] == "outside_roots"
    # « .. » ne fait pas sortir de la racine
    escaped = str(root / ".." / "ailleurs" / "secret.png")
    assert post_image_set(client, slug, line, [escaped]).json()["code"] == "outside_roots"
    assert browse(client, slug, str(tmp_path / "ailleurs")).json()["code"] == "outside_roots"
    assert browse(client, slug, str(root / "..")).json()["code"] == "outside_roots"

    # un jeu d'avant ces règles qui pointe hors des racines ne se lit plus
    set_id = _legacy_set(slug, line, [outside])
    assert image_sets(client, slug, line)[0]["images"][0]["status"] == "forbidden"
    assert get_image(client, slug, line, set_id, 0).status_code == 403


def test_a_network_path_outside_the_roots_is_refused_without_touching_it(client, root, monkeypatch):
    slug, line = _setup(client)
    touched = []
    for name in ("resolve", "is_file", "is_dir", "stat"):
        original = getattr(pathlib.Path, name)

        def spy(self, *args, _original=original, **kwargs):
            touched.append(str(self))
            return _original(self, *args, **kwargs)

        monkeypatch.setattr(pathlib.Path, name, spy)
    unc = r"\\serveur-inconnu\partage\coupe.png"
    assert post_image_set(client, slug, line, [unc]).json()["code"] == "outside_roots"
    assert browse(client, slug, r"\\serveur-inconnu\partage").json()["code"] == "outside_roots"
    assert not [path for path in touched if "serveur-inconnu" in path]


def test_without_roots_browsing_is_disabled_and_network_paths_refused(client, no_roots, tmp_path):
    slug, line = _setup(client)
    response = browse(client, slug, str(tmp_path))
    assert response.status_code == 503 and response.json()["code"] == "browsing_disabled"
    assert post_image_set(client, slug, line, [r"\\serveur-inconnu\partage\coupe.png"]).json()["code"] == "outside_roots"
    # un chemin local reste accepté
    created = create_image_set(client, slug, line, png_files(tmp_path / "local"))
    assert client.get(created["images"][0]["url"]).status_code == 200


def test_browsing_lists_the_images_of_an_allowed_folder(client, root):
    slug, _ = _setup(client)
    png_files(root, "b.png", "a.jpg")
    (root / "c.tif").write_bytes(b"II*\x00")
    (root / "notes.txt").write_text("x", encoding="utf-8")
    (root / "sous-dossier.png").mkdir()
    response = browse(client, slug, str(root))
    assert response.status_code == 200
    assert [(i["name"], i["displayable"]) for i in response.json()] == [("a.jpg", True), ("b.png", True), ("c.tif", False)]
    assert_handler_404(browse(client, slug, str(root / "absent")), "introuvable")


def test_an_image_is_only_reached_through_its_set(client, root, tmp_path):
    slug, line = _setup(client)
    created = create_image_set(client, slug, line, png_files(root))
    secret = png_files(tmp_path / "ailleurs", "secret.png")[0]
    # un chemin envoyé par le client n'est jamais lu : seuls le jeu et le rang désignent l'image
    assert get_image(client, slug, line, created["id"], 0, chemin=secret, path=secret).content == PNG_1PX
    assert_handler_404(get_image(client, slug, line, created["id"], 2), "introuvable")
    assert_handler_404(get_image(client, slug, line, created["id"], -1), "introuvable")
    assert_handler_404(get_image(client, slug, line, "data_inconnu", 0), "introuvable")
    assert get_image(client, slug, line, created["id"], "secret").status_code == 422
    # les anciennes routes, qui lisaient un chemin reçu, n'existent plus
    for old in (f"/api/microprojets/{slug}/data/image", f"/api/microprojets/{slug}/data/parcourir"):
        gone = client.get(old, params={"chemin": secret, "dossier": str(tmp_path)})
        assert gone.status_code == 404 and gone.json()["detail"] == ROUTER_NOT_FOUND


def test_viewers_see_the_gallery_but_do_not_change_it(client, root):
    signup(client, "admin@example.com")  # le premier compte est admin : il a accès à tout µprojet
    signup(client, "viewer-gallery@example.com", name="V")
    slug, line = _setup(client, "owner-gallery@example.com")
    created = create_image_set(client, slug, line, png_files(root))
    add_member(client, slug, "viewer-gallery@example.com", "viewer")
    login(client, "viewer-gallery@example.com")
    assert image_sets(client, slug, line) == [created]
    assert client.get(created["images"][0]["url"]).status_code == 200
    assert post_image_set(client, slug, line, png_files(root, "autre.png")).status_code == 403
    assert patch_image_set(client, slug, line, created["id"], 1).status_code == 403
    assert delete_image_set(client, slug, line, created["id"]).status_code == 403
    assert browse(client, slug, str(root)).status_code == 403  # parcourir : éditeur


def test_a_viewer_of_another_microproject_is_refused(client, root):
    slug, line = _setup(client, "owner-gallery2@example.com")
    created = create_image_set(client, slug, line, png_files(root))
    # membre (propriétaire, même) d'un autre µprojet, pas de celui-ci
    signup_with_microproject(client, "other-gallery@example.com", "Ailleurs")
    assert client.get(created["images"][0]["url"]).status_code == 403
    assert client.get(f"/api/microprojects/{slug}/experiments/{line}/image-sets").status_code == 403
    assert browse(client, slug, str(root)).status_code == 403
