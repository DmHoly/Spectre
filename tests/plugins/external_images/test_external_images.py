"""Images externes (plugin external_images) : la politique des chemins et le parcours des dossiers
autorisés. L'accès au disque est borné aux racines de ``SPECTRE_EXTERNAL_IMAGE_ROOTS`` ; les images
elles-mêmes sont un contenu du cahier (voir ``tests/plugins/notebook/test_external_images.py``)."""

from __future__ import annotations

import os
import pathlib

import pytest

from spectre.kernel.errors import Forbidden, InvalidInput
from spectre.plugins.external_images import service

from support.accounts import login, signup
from support.external_images import browse, png_files, roots
from support.http import ROUTER_NOT_FOUND, assert_handler_404
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


def test_browsing_lists_the_images_of_an_allowed_folder(client, root):
    slug = signup_with_microproject(client, "browse@example.com")
    png_files(root, "b.png", "a.jpg")
    (root / "c.tif").write_bytes(b"II*\x00")
    (root / "notes.txt").write_text("x", encoding="utf-8")
    (root / "sous-dossier.png").mkdir()
    response = browse(client, slug, str(root))
    assert response.status_code == 200
    assert [(i["name"], i["displayable"]) for i in response.json()] == [("a.jpg", True), ("b.png", True), ("c.tif", False)]
    assert_handler_404(browse(client, slug, str(root / "absent")), "introuvable")


def test_the_roots_are_listed_as_written_once_each(client, tmp_path, monkeypatch):
    """Les dossiers d'où partir, tels qu'écrits (un même dossier une fois), sans toucher au disque :
    une racine réseau absente se liste aussi."""
    slug = signup_with_microproject(client, "roots@example.com")
    first, second = tmp_path / "tem", tmp_path / "meb"
    first.mkdir()
    unc = r"\\serveur-inconnu\partage"
    monkeypatch.setenv("SPECTRE_EXTERNAL_IMAGE_ROOTS", os.pathsep.join([str(first), f" {first} ", str(second), unc, ""]))
    response = roots(client, slug)
    assert response.status_code == 200
    assert response.json() == [str(first), str(second), os.path.abspath(unc)]


def test_without_roots_the_list_is_empty(client, no_roots):
    slug = signup_with_microproject(client, "roots-off@example.com")
    assert roots(client, slug).json() == []


def test_browsing_stays_inside_the_roots(client, root, tmp_path):
    slug = signup_with_microproject(client, "browse-roots@example.com")
    png_files(tmp_path / "ailleurs", "secret.png")
    assert browse(client, slug, str(tmp_path / "ailleurs")).json()["code"] == "outside_roots"
    assert browse(client, slug, str(root / "..")).json()["code"] == "outside_roots"
    assert browse(client, slug, "mesures").json()["code"] == "relative_path"
    assert browse(client, slug, str(root) + "\x00").json()["code"] == "invalid_path"


def test_a_network_path_outside_the_roots_is_refused_without_touching_it(client, root, monkeypatch):
    slug = signup_with_microproject(client, "browse-unc@example.com")
    touched = []
    for name in ("resolve", "is_file", "is_dir", "stat"):
        original = getattr(pathlib.Path, name)

        def spy(self, *args, _original=original, **kwargs):
            touched.append(str(self))
            return _original(self, *args, **kwargs)

        monkeypatch.setattr(pathlib.Path, name, spy)
    unc = r"\\serveur-inconnu\partage"
    assert browse(client, slug, unc).json()["code"] == "outside_roots"
    with pytest.raises(Forbidden):
        service.checked_image(unc + r"\coupe.png")
    assert service.image_status(unc + r"\coupe.png") == "forbidden"
    assert not [path for path in touched if "serveur-inconnu" in path]


def test_without_roots_browsing_is_disabled_and_network_paths_refused(client, no_roots, tmp_path):
    slug = signup_with_microproject(client, "browse-off@example.com")
    response = browse(client, slug, str(tmp_path))
    assert response.status_code == 503 and response.json()["code"] == "browsing_disabled"
    with pytest.raises(Forbidden):
        service.checked_image(r"\\serveur-inconnu\partage\coupe.png")
    # un chemin local reste accepté
    local = png_files(tmp_path / "local", "coupe.png")[0]
    assert service.checked_image(local) == str(pathlib.Path(local).resolve())


def test_a_referenced_image_must_be_a_displayable_existing_file(root):
    (root / "coupe.tif").write_bytes(b"II*\x00")
    (root / "notes.txt").write_text("pas une image", encoding="utf-8")
    refused = {}
    for name in ("coupe.tif", "notes.txt", "absente.png"):
        with pytest.raises(InvalidInput) as caught:
            service.checked_image(str(root / name))
        refused[name] = caught.value.code
    assert refused == {"coupe.tif": "unsupported_format", "notes.txt": "not_an_image", "absente.png": "file_not_found"}


def test_only_editors_browse(client, root):
    signup(client, "admin-browse@example.com")  # le premier compte est admin : il a accès à tout µprojet
    signup(client, "viewer-browse@example.com", name="V")
    slug = signup_with_microproject(client, "owner-browse@example.com")
    add_member(client, slug, "viewer-browse@example.com", "viewer")
    login(client, "viewer-browse@example.com")
    assert browse(client, slug, str(root)).status_code == 403
    assert roots(client, slug).status_code == 403
    # membre (propriétaire, même) d'un autre µprojet, pas de celui-ci
    signup_with_microproject(client, "other-browse@example.com", "Ailleurs")
    assert browse(client, slug, str(root)).status_code == 403


def test_the_old_routes_are_gone(client, root, tmp_path):
    slug = signup_with_microproject(client, "browse-old@example.com")
    for old in (f"/api/microprojets/{slug}/data/image", f"/api/microprojets/{slug}/data/parcourir"):
        gone = client.get(old, params={"chemin": str(tmp_path), "dossier": str(tmp_path)})
        assert gone.status_code == 404 and gone.json()["detail"] == ROUTER_NOT_FOUND
