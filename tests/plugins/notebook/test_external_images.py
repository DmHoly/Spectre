"""Les images externes du cahier : une mesure manuelle référence des images (TEM, scans) à leur
emplacement sur le disque du serveur, sans les copier, sous la politique du plugin external_images
(racines ``SPECTRE_EXTERNAL_IMAGE_ROOTS``, formats affichables). Une image se lit par l'entrée qui la
référence et son rang, jamais par un chemin reçu du client. Les jeux de l'ancienne galerie
(``data_items``) se lisent comme des entrées du cahier, qui gardent leurs ids, sans qu'aucune version
soit réécrite ; la première écriture dans le cahier les enregistre au nouveau format."""

from __future__ import annotations

import pathlib

import pytest

from spectre.plugins.experiments import service as experiments
from spectre.plugins.experiments.repository import get_repository
from support.accounts import login, signup
from support.experiments import conclude, get_experiment, launch, launch_campaign, versions
from support.external_images import png_files
from support.http import PNG_1PX, assert_handler_404
from support.microprojects import add_member, signup_with_microproject
from support.notebook import (
    add_manual,
    as_input,
    entries,
    entries_by_id,
    get_entry,
    get_external_image,
    legacy_image_set,
    objects_checksums,
    patch_entry,
    post_entry,
    update_entry,
    write_legacy,
)


@pytest.fixture()
def root(tmp_path, monkeypatch):
    """Le dossier autorisé (``SPECTRE_EXTERNAL_IMAGE_ROOTS``) - un autre dossier, à côté, ne l'est pas."""
    allowed = tmp_path / "mesures"
    allowed.mkdir()
    monkeypatch.setenv("SPECTRE_EXTERNAL_IMAGE_ROOTS", str(allowed))
    return allowed


def _setup(client, email="external@example.com"):
    slug = signup_with_microproject(client, email, "Mesures", name="Ada")
    line = launch(client, slug, title="Recuit", intent="Voir la coupe", hypothesis="Le puits fait 3 nm", objectives=[{"name": "Coupe", "metric": "epaisseur"}])["id"]
    return slug, line


def _manual(images: list[dict], **fields) -> dict:
    return {"kind": "manual", "title": "Coupe TEM", "measurements": [{"external_images": images, **fields}]}


def test_a_manual_measurement_references_external_images_served_by_id(client, root):
    slug, line = _setup(client)
    first, second = png_files(root, "tem-1.png", "tem-2.png")
    response = post_entry(client, slug, line, **_manual([{"path": first, "caption": "centre"}, {"path": second}], text="coupe"))
    assert response.status_code == 201
    entry = response.json()
    base = f"/api/microprojects/{slug}/experiments/{line}/notebook-entries/{entry['id']}/external-images"
    [measurement] = entry["measurements"]
    assert [(i["index"], i["name"], i["path"], i["caption"], i["status"], i["url"]) for i in measurement["external_images"]] == [
        (0, "tem-1.png", first, "centre", "ok", f"{base}/0"),
        (1, "tem-2.png", second, None, "ok", f"{base}/1"),
    ]
    assert measurement["text"] == "coupe" and measurement["attachments"] == []
    assert entries_by_id(client, slug, line)[entry["id"]] == entry
    assert get_experiment(client, slug, line)["notebook_count"] == 1

    image = client.get(measurement["external_images"][1]["url"])
    assert image.status_code == 200 and image.content == PNG_1PX and image.headers["content-type"] == "image/png"

    # une version passée garde ses images, lues sur elle
    tip = get_experiment(client, slug, line)["version_id"]
    update_entry(client, slug, line, entry["id"], measurements=[{"text": "sans image"}])
    old = get_entry(client, slug, line, entry["id"], version=tip).json()
    old_url = old["measurements"][0]["external_images"][0]["url"]
    assert old_url == f"{base}/0?version={tip}" and client.get(old_url).content == PNG_1PX
    assert entries_by_id(client, slug, line)[entry["id"]]["measurements"][0]["external_images"] == []
    assert_handler_404(get_external_image(client, slug, line, entry["id"], 0), "introuvable")


def test_images_are_counted_across_the_measurements_of_an_entry(client, root):
    slug = signup_with_microproject(client, "external-steps@example.com")
    line = launch(client, slug)["id"]
    [step] = [s["id"] for s in client.get(f"/api/microprojects/{slug}/experiments/{line}/process").json()["steps"]][:1]
    a, b, c = png_files(root, "a.png", "b.png", "c.png")
    entry = add_manual(client, slug, line, measurements=[{"external_images": [{"path": a}]}, {"step_id": step, "external_images": [{"path": b}, {"path": c}, {"path": b}]}])
    indexes = [[(i["index"], i["name"]) for i in m["external_images"]] for m in entry["measurements"]]
    assert indexes == [[(0, "a.png")], [(1, "b.png"), (2, "c.png")]]  # sans doublon
    assert [get_external_image(client, slug, line, entry["id"], i).status_code for i in range(3)] == [200] * 3


def test_a_path_is_checked_when_written(client, root, tmp_path):
    slug, line = _setup(client)
    outside = png_files(tmp_path / "ailleurs", "secret.png")[0]
    (root / "coupe.tif").write_bytes(b"II*\x00")
    (root / "notes.txt").write_text("pas une image", encoding="utf-8")

    def refused(path):
        response = post_entry(client, slug, line, **_manual([{"path": path}]))
        return response.status_code, response.json()["code"]

    assert refused(outside) == (403, "outside_roots")
    assert refused(str(root / ".." / "ailleurs" / "secret.png")) == (403, "outside_roots")  # « .. » ne fait pas sortir
    assert refused(r"\\serveur-inconnu\partage\coupe.png") == (403, "outside_roots")
    assert refused("mesures/tem.png") == (422, "relative_path")
    assert refused(str(root / "absente.png")) == (422, "file_not_found")
    assert refused(str(root / "notes.txt")) == (422, "not_an_image")
    tiff = post_entry(client, slug, line, **_manual([{"path": str(root / "coupe.tif")}]))
    assert tiff.status_code == 422 and tiff.json()["code"] == "unsupported_format"
    assert "TIFF" in tiff.json()["detail"] and "PNG" in tiff.json()["detail"]
    # une vue PRISM n'a pas d'image externe
    prism = post_entry(
        client, slug, line, kind="prism", title="Vue", measurements=[{"snapshot_id": "x", "component": "table", "external_images": [{"path": png_files(root)[0]}]}]
    )
    assert prism.status_code == 422
    assert entries(client, slug, line) == []
    assert len(versions(client, slug, line)) == 1


def test_an_image_is_only_reached_through_the_entry_that_references_it(client, root, tmp_path):
    slug, line = _setup(client)
    entry = add_manual(client, slug, line, measurements=[{"external_images": [{"path": p} for p in png_files(root)]}])
    secret = png_files(tmp_path / "ailleurs", "secret.png")[0]
    other = png_files(root, "autre.png")[0]
    # un chemin envoyé par le client n'est jamais lu : seuls l'entrée et le rang désignent l'image
    assert get_external_image(client, slug, line, entry["id"], 0, path=secret, chemin=other).content == PNG_1PX
    assert_handler_404(get_external_image(client, slug, line, entry["id"], 2), "introuvable")
    assert_handler_404(get_external_image(client, slug, line, entry["id"], -1), "introuvable")
    assert_handler_404(get_external_image(client, slug, line, "nb_inconnue", 0), "introuvable")
    assert get_external_image(client, slug, line, entry["id"], "secret").status_code == 422
    # une image sous les racines, mais qu'aucune entrée ne référence, ne se lit pas
    plain = add_manual(client, slug, line, measurements=[{"text": "sans image"}])
    assert_handler_404(get_external_image(client, slug, line, plain["id"], 0), "introuvable")


def test_viewers_see_the_images_but_do_not_change_them(client, root):
    signup(client, "admin-external@example.com")  # le premier compte est admin : il a accès à tout µprojet
    signup(client, "viewer-external@example.com", name="V")
    slug, line = _setup(client, "owner-external@example.com")
    entry = add_manual(client, slug, line, measurements=[{"external_images": [{"path": png_files(root)[0]}]}])
    add_member(client, slug, "viewer-external@example.com", "viewer")
    login(client, "viewer-external@example.com")
    assert entries_by_id(client, slug, line)[entry["id"]] == entry
    assert client.get(entry["measurements"][0]["external_images"][0]["url"]).status_code == 200
    assert post_entry(client, slug, line, **_manual([{"path": png_files(root, "autre.png")[0]}])).status_code == 403
    assert patch_entry(client, slug, line, entry["id"], title="Autre").status_code == 403
    # membre (propriétaire, même) d'un autre µprojet, pas de celui-ci
    signup_with_microproject(client, "other-external@example.com", "Ailleurs")
    assert client.get(entry["measurements"][0]["external_images"][0]["url"]).status_code == 403


# -- les jeux de l'ancienne galerie ----------------------------------------------------------------


def _old_gallery(client, root, tmp_path):
    """Une étude d'avant : deux jeux de l'ancienne galerie - l'un épinglé sur sa deuxième image, avec
    une note, dont une image a été déplacée depuis et une autre est un TIFF ; l'autre sans titre, qui
    pointe hors des racines."""
    slug, line = _setup(client)
    first, second = png_files(root, "tem-1.png", "tem-2.png")
    moved = png_files(root, "deplacee.png")[0]
    (root / "ancienne.tiff").write_bytes(b"II*\x00")
    outside = png_files(tmp_path / "ailleurs", "secret.png")[0]

    def old(builder, parent):
        legacy_image_set(builder, "data_" + "1" * 20, [first, second, moved, str(root / "ancienne.tiff")], title="Coupe TEM", note="centre du wafer", pinned_index=1)
        legacy_image_set(builder, "data_" + "2" * 20, [outside])

    old_version = write_legacy(slug, line, old)
    pathlib.Path(moved).unlink()
    return {"slug": slug, "line": line, "first": first, "second": second, "moved": moved, "tiff": str(root / "ancienne.tiff"), "outside": outside, "version": old_version}


def test_an_old_image_set_reads_as_a_notebook_entry_that_keeps_its_id(client, root, tmp_path):
    old = _old_gallery(client, root, tmp_path)
    slug, line = old["slug"], old["line"]
    before = objects_checksums(slug)

    converted = entries_by_id(client, slug, line)
    assert list(converted) == ["data_" + "1" * 20, "data_" + "2" * 20]
    tem = converted["data_" + "1" * 20]
    summary = (tem["kind"], tem["title"], tem["note"], tem["wafers"], tem["applies"], tem["created_by"])
    assert summary == ("manual", "Coupe TEM", "centre du wafer", [], True, "Ada")
    [measurement] = tem["measurements"]
    assert measurement["step_id"] is None and measurement["attachments"] == []
    # l'image épinglée d'abord, puis les autres dans leur ordre ; chacune dit si elle se montre
    assert [(i["path"], i["status"]) for i in measurement["external_images"]] == [
        (old["second"], "ok"),
        (old["first"], "ok"),
        (old["moved"], "missing"),
        (old["tiff"], "unsupported"),
    ]
    assert converted["data_" + "2" * 20]["title"] == "Images de mesure"
    assert converted["data_" + "2" * 20]["measurements"][0]["external_images"][0]["status"] == "forbidden"

    # servies par l'entrée et le rang, la politique revérifiée à chaque lecture
    assert client.get(measurement["external_images"][0]["url"]).content == PNG_1PX
    missing = get_external_image(client, slug, line, tem["id"], 2)
    assert_handler_404(missing, "déplacé")
    assert missing.json()["code"] == "image_missing"
    assert get_external_image(client, slug, line, tem["id"], 3).json()["code"] == "unsupported_format"
    assert get_external_image(client, slug, line, "data_" + "2" * 20, 0).status_code == 403

    # lire ne réécrit rien
    assert objects_checksums(slug) == before
    # le détail les compte, la conclusion peut les citer
    assert get_experiment(client, slug, line)["notebook_count"] == 2
    result = {"objective": "Coupe", "status": "met", "evidence_ids": [tem["id"]]}
    assert conclude(client, slug, line, objective_results=[result])["conclusion"]["objective_results"][0]["evidence_ids"] == [tem["id"]]


def test_the_first_write_records_the_converted_sets_and_drops_the_old_key(client, root, tmp_path):
    old = _old_gallery(client, root, tmp_path)
    slug, line = old["slug"], old["line"]
    converted = entries_by_id(client, slug, line)
    before = objects_checksums(slug)

    tem = converted["data_" + "1" * 20]
    # renvoyer la mesure telle que lue suffit, même avec une image déplacée depuis
    kept = update_entry(client, slug, line, tem["id"], measurements=[as_input(m) for m in tem["measurements"]], title="Coupe TEM revue")
    assert kept["measurements"] == tem["measurements"]

    tip = get_repository(slug).get(get_experiment(client, slug, line)["version_id"])
    assert "data_items" not in tip.metadata
    stored = {entry["id"]: entry for entry in tip.metadata[experiments.NOTEBOOK_KEY]}
    assert list(stored) == ["data_" + "1" * 20, "data_" + "2" * 20]
    assert [i["path"] for i in stored[tem["id"]]["measurements"][0]["external_images"]] == [old["second"], old["first"], old["moved"], old["tiff"]]
    now = entries_by_id(client, slug, line)
    assert now["data_" + "2" * 20] == converted["data_" + "2" * 20]
    assert {**now[tem["id"]], "title": None, "updated_at": None, "updated_by": None} == {**tem, "title": None, "updated_at": None, "updated_by": None}
    # aucun objet Follow réécrit ; l'ancienne version se lit toujours convertie
    after = objects_checksums(slug)
    assert {name: after[name] for name in before} == before
    assert entries_by_id(client, slug, line, old["version"]).keys() == converted.keys()
    # une image ajoutée ensuite est vérifiée, elle
    refused = patch_entry(client, slug, line, tem["id"], measurements=[{"external_images": [{"path": old["moved"]}, {"path": str(root / "neuve.png")}]}])
    assert refused.json()["code"] == "file_not_found"


def test_an_old_set_of_a_campaign_variant_follows_the_variant_wafer(client, root):
    slug = signup_with_microproject(client, "external-campaign@example.com")
    line = launch_campaign(client, slug, entities=[{"sample_id": "W0"}, {"sample_id": "W12-A3"}])["id"]
    paths = png_files(root)

    def old(builder, parent):
        legacy_image_set(builder, "data_" + "3" * 20, paths, title="Variante 2", entity_index=1)
        legacy_image_set(builder, "data_" + "4" * 20, paths, title="Variante 3", entity_index=2)

    write_legacy(slug, line, old)
    converted = entries_by_id(client, slug, line)
    assert converted["data_" + "3" * 20]["wafers"] == ["W12A3"] and converted["data_" + "3" * 20]["applies"] is True
    # une variante sans plaque : l'entrée vaut pour toute la piste, la variante rappelée dans le texte
    unnamed = converted["data_" + "4" * 20]
    assert unnamed["wafers"] == [] and unnamed["measurements"][0]["text"].startswith("Variante n° 3")
