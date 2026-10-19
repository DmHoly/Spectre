"""Le plugin sem_images : les images MEB du G4 d'une plaque, rangées par acquisition, servies rendues à la volée
(vignette, PNG entier, une trame par détecteur) et seulement parmi celles que la recherche a trouvées pour elle ;
les métadonnées lues dans les balises du TIF ; l'index des dossiers tenu à jour à part. La recherche sur le
partage est celle de PRISM (hook ``meb_g4``) : ici une source de test sur de vrais TIF dans un dossier temporaire,
et un test de bout en bout avec le PRISM installé quand il sait chercher par FDL."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, TiffImagePlugin

from spectre.plugins.sem_images import service, source, tiff_meta
from support.accounts import signup

DESCRIPTION = """
ShortDescription:
  Data-Type: Base
ImageDescription:
  Version: 1
  Image-Type: "SEM Digital"
  Image-Parameters:
    Tilt: 2
    Iprobe: 0
    Vacc: 1000
  Field-Of-View:
    mX: 20
    mY: 20
  Wafer-Location:
    mX: 3896.5
    mY: -68093.25
  VC: None
"""

EXTRA = """NewAdditionalInformation:
  mImageAttributesList:
    Number_Of_Elements: 13
    [0]: "waferID: "
    [1]: 27CYH6E6MMC5
    [2]: "defectID: "
    [3]: 10
    [4]: "lotID: "
    [5]: 2026-42070
    [6]: "class: "
    [7]: NewEvent
    [8]: "dieLocX: "
    [9]: 11380.00
    [10]: "dieLocY: "
    [11]: 18150.00
    [12]: "die: 0,-4"
  mComments: ""
  mDate: 1792130444
"""

FOLDER = "Others/l2026-42070_pWLKGSM_sARC_POST_STRIP/w27CYH6E6MMC5"
ARCHIVE = "Archive_Pollen/2026-38090/l2026-38090_pWLKG_sWIRES_WHWD/w27CYH6E6MMC5"


def write_tif(path: Path, frames: int = 3, size: int = 96) -> Path:
    """Un TIF comme ceux du G4 : 8 bits, une trame par détecteur, les balises texte du SEMVision."""
    path.parent.mkdir(parents=True, exist_ok=True)
    info = TiffImagePlugin.ImageFileDirectory_v2()
    info[tiff_meta.IMAGE_DESCRIPTION] = DESCRIPTION
    info[tiff_meta.NEW_ADDITIONAL_INFORMATION] = EXTRA
    info.tagtype[tiff_meta.NEW_ADDITIONAL_INFORMATION] = 2
    images = [Image.new("L", (size, size), 40 * (i + 1)) for i in range(frames)]
    images[0].save(path, save_all=True, append_images=images[1:], tiffinfo=info)
    return path


@pytest.fixture
def share(tmp_path, monkeypatch):
    """Un partage de test et une source qui le lit comme PRISM le ferait (deux acquisitions de la plaque)."""
    root = tmp_path / "Datas"
    files = {
        f"{FOLDER}/d1r1_Class.tif": ("2026-10-17T01:40:00+00:00", 1, 1),
        f"{FOLDER}/d2r1_Class.tif": ("2026-10-17T01:41:00+00:00", 2, 1),
        f"{ARCHIVE}/d1r1_Class2026.tif": ("2026-09-26T08:00:00+00:00", 1, 1),
        f"{ARCHIVE}/d1r2_Class2026.tif": ("2026-09-26T08:01:00+00:00", 1, 2),
    }
    for relative in files:
        write_tif(root / relative)
    calls: list[tuple[str, list[str]]] = []

    def images(lasermark, fdls):
        calls.append((lasermark, list(fdls)))
        if lasermark.upper() != "27CYH6E6MMC5":
            return []
        rows = []
        for relative, (modified, die, rnd) in files.items():
            folder = relative.rsplit("/", 1)[0]
            archive = folder.startswith("Archive")
            rows.append({"wafername": lasermark, "die": die, "round": rnd, "path": str(root / relative), "exists": True,
                         "area": folder.split("/")[0], "lot": "2026-38090" if archive else "2026-42070",
                         "fdl": "2026-38090" if archive else "2026-42070", "process": "WLKG" if archive else "WLKGSM",
                         "step": "WIRES_WHWD" if archive else "ARC_POST_STRIP", "folder": folder, "modified": modified, "size": 10})
        return rows

    index = {"exists": True, "built_at": "2026-10-17T15:09:43+00:00", "checked_at": "2026-10-17T15:10:03+00:00", "wafers": 3938, "folders": 2597}
    refreshed: list[bool] = []
    monkeypatch.setattr(source, "require_root", lambda: root)
    monkeypatch.setattr(source, "images", images)
    monkeypatch.setattr(source, "index_info", lambda: dict(index))
    monkeypatch.setattr(source, "index_age_seconds", lambda: 10.0)
    monkeypatch.setattr(source, "refresh_index", lambda full=False: refreshed.append(full) or dict(index))
    service.forget()
    yield type("Share", (), {"root": root, "calls": calls, "index": index, "refreshed": refreshed})
    service.forget()


BASE = "/api/wafers/27CYH6E6MMC5/sem-images"


def test_the_images_are_grouped_by_acquisition_most_recent_first(client, share):
    signup(client, "boss@example.com")
    data = client.get(BASE).json()
    assert data["count"] == 4 and data["root"] == str(share.root)
    first, second = data["groups"]
    assert (first["step"], first["fdl"], first["process"], first["area_label"], first["count"]) == ("ARC_POST_STRIP", "2026-42070", "WLKGSM", "Autres", 2)
    assert (second["step"], second["area_label"], second["rounds"]) == ("WIRES_WHWD", "Archive Pollen", [1, 2])
    assert [(i["die"], i["round"]) for i in second["images"]] == [(1, 1), (1, 2)]
    assert first["images"][0]["path"] == f"{FOLDER}/d1r1_Class.tif" and first["images"][0]["name"] == "d1r1_Class.tif"
    assert data["index"]["exists"] and not data["index"]["building"]


def test_another_plugin_gets_the_address_of_an_image_of_the_share(share, monkeypatch):
    """La fiche data montre les images du hook meb_g4 par ce plugin : l'adresse d'un chemin absolu du partage, relatif
    à la racine ; rien pour un chemin hors de la racine."""
    monkeypatch.setattr(source, "root", lambda: share.root)
    url = service.url_for("27CYH6E6MMC5", str(share.root / FOLDER / "d1r1_Class.tif"))
    assert url == f"/api/wafers/27CYH6E6MMC5/sem-images/file?path={FOLDER}/d1r1_Class.tif&variant=thumb"
    assert service.url_for("27CYH6E6MMC5", str(share.root / FOLDER / "d1r1_Class.tif"), variant="view", frame=2).endswith("&variant=view&frame=2")
    assert service.url_for("27CYH6E6MMC5", str(share.root.parent / "ailleurs.tif")) is None


def test_the_search_uses_the_typed_fdls_and_the_list_is_kept(client, share):
    signup(client, "boss@example.com")
    client.get(BASE, params={"fdl": ["2026-41155", " 2026-41155 "]})
    assert share.calls[-1] == ("27CYH6E6MMC5", ["2026-41155"])
    client.get(BASE, params={"fdl": ["2026-41155"]})
    assert len(share.calls) == 1                      # gardée en mémoire
    client.get(BASE, params={"fdl": ["2026-41155"], "refresh": "true"})
    assert len(share.calls) == 2                      # relue sur demande


def test_an_image_is_served_rendered_and_cached(client, share):
    signup(client, "boss@example.com")
    path = client.get(BASE).json()["groups"][0]["images"][0]["path"]
    thumb = client.get(f"{BASE}/file", params={"path": path})
    assert thumb.status_code == 200 and thumb.headers["content-type"] == "image/jpeg"
    assert thumb.headers["cache-control"].startswith("private")
    assert client.get(f"{BASE}/file", params={"path": path}, headers={"If-None-Match": thumb.headers["etag"]}).status_code == 304
    view = client.get(f"{BASE}/file", params={"path": path, "variant": "view", "frame": 2})
    assert view.headers["content-type"] == "image/png" and view.content.startswith(b"\x89PNG")
    assert view.headers["etag"] != client.get(f"{BASE}/file", params={"path": path, "variant": "view"}).headers["etag"]
    assert client.get(f"{BASE}/file", params={"path": path, "variant": "raw"}).status_code == 422


def test_only_images_of_the_wafer_list_are_served(client, share, tmp_path):
    signup(client, "boss@example.com")
    client.get(BASE)
    write_tif(share.root / "Others" / "autre" / "secret.tif")
    for path in ("Others/autre/secret.tif", f"{FOLDER}/../../autre/secret.tif", str(share.root / FOLDER / "d1r1_Class.tif")):
        response = client.get(f"{BASE}/file", params={"path": path})
        assert response.status_code == 404 and response.json()["code"] == "sem_image_unknown", path
    # l'image d'une plaque ne se lit pas sous le nom d'une autre
    assert client.get("/api/wafers/AUTRE01/sem-images/file", params={"path": f"{FOLDER}/d1r1_Class.tif"}).status_code == 404


def test_the_tiff_tells_its_scale_position_and_defect(client, share):
    signup(client, "boss@example.com")
    path = client.get(BASE).json()["groups"][0]["images"][0]["path"]
    meta = client.get(f"{BASE}/meta", params={"path": path}).json()
    assert (meta["width"], meta["frames"], meta["fov_um"]) == (96, 3, [20.0, 20.0])
    assert meta["pixel_um"] == pytest.approx(20 / 96)
    assert meta["location_um"] == [3896.5, -68093.25] and meta["die_index"] == "0,-4"
    assert (meta["defect_id"], meta["defect_class"], meta["lot_id"], meta["kv"], meta["tilt"]) == ("10", "NewEvent", "2026-42070", 1.0, 2.0)
    assert meta["acquired"].startswith("2026-10-") and meta["file"].endswith("d1r1_Class.tif")


def test_a_tiff_without_g4_tags_gives_its_size_only(tmp_path):
    plain = tmp_path / "plain.tif"
    Image.new("L", (40, 30)).save(plain)
    from spectre.plugins.sem_images import render

    meta = render.meta(str(plain))
    assert (meta["width"], meta["height"], meta["frames"], meta["fov_um"], meta["defect_id"]) == (40, 30, 1, None, None)


def test_a_missing_file_is_a_404(client, share):
    signup(client, "boss@example.com")
    path = client.get(BASE).json()["groups"][0]["images"][0]["path"]
    (share.root / path).unlink()
    assert client.get(f"{BASE}/file", params={"path": path}).json()["code"] == "sem_image_missing"


def test_without_index_a_wafer_without_images_starts_building_it(client, share, monkeypatch):
    signup(client, "boss@example.com")
    share.index["exists"] = False
    started: list[bool] = []
    monkeypatch.setattr(service, "start_index", lambda full=False: started.append(full) or True)
    data = client.get("/api/wafers/INCONNUE01/sem-images").json()
    assert data["count"] == 0 and data["groups"] == [] and started == [True]
    client.get(BASE)
    assert started == [True]                          # des images trouvées : rien à construire


def test_the_index_is_updated_in_the_background(client, share):
    signup(client, "boss@example.com")
    response = client.post("/api/sem-images/index")
    assert response.status_code == 202 and response.json()["started"] is True
    for _ in range(100):
        if share.refreshed and not client.get("/api/sem-images/index").json()["updating"]:
            break
    assert share.refreshed == [False]


def test_rebuilding_the_whole_index_is_for_admins(client, share):
    signup(client, "boss@example.com")                # le premier compte est administrateur
    signup(client, "user@example.com")
    assert client.post("/api/sem-images/index", params={"full": "true"}).json()["code"] == "admin_only"


def test_a_closed_share_is_said(client, monkeypatch):
    signup(client, "boss@example.com")
    monkeypatch.setattr(source, "root", lambda: Path("Z:/nulle_part/Datas"))
    response = client.get(BASE)
    assert response.status_code == 503 and response.json()["code"] == "sem_root_missing"


def test_the_tag_parser_reads_nested_blocks_and_attribute_pairs():
    info = tiff_meta.parse_block(EXTRA)
    assert tiff_meta.attributes(info) == {"waferID": "27CYH6E6MMC5", "defectID": "10", "lotID": "2026-42070", "class": "NewEvent",
                                          "dieLocX": "11380.00", "dieLocY": "18150.00", "die": "0,-4"}
    assert tiff_meta.parse_block(DESCRIPTION)["ImageDescription"]["Field-Of-View"] == {"mX": "20", "mY": "20"}


def test_end_to_end_with_the_installed_prism(client, tmp_path, monkeypatch):
    """Le hook ``meb_g4`` du PRISM installé, sur un partage de test : sauté tant que ce PRISM ne cherche pas par FDL."""
    meb_g4 = pytest.importorskip("prism.loaders.meb_g4")
    if not hasattr(meb_g4, "refresh_index"):
        pytest.skip("le PRISM installé ne cherche pas encore les images du G4 par FDL")
    root = tmp_path / "Datas"
    write_tif(root / FOLDER / "d1r1_Class.tif")
    monkeypatch.setenv("PRISM_SEM_ROOT", str(root))
    monkeypatch.setenv("PRISM_DATA_DIR", str(tmp_path / "prism"))
    service.forget()
    signup(client, "boss@example.com")
    data = client.get(BASE, params={"fdl": "2026-42070"}).json()
    assert data["count"] == 1 and data["groups"][0]["step"] == "ARC_POST_STRIP"
    path = data["groups"][0]["images"][0]["path"]
    assert client.get(f"{BASE}/file", params={"path": path, "fdl": "2026-42070"}).status_code == 200
    service.forget()
