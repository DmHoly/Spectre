"""Le dossier de la bibliothèque appartient à l'instance : créé une fois depuis les fichiers livrés,
puis jamais réécrit par eux (B11 : absent en Docker, une édition bloquait ``git pull``)."""

from __future__ import annotations

from pathlib import Path

from spectre.plugins.library import service

SHIPPED = sorted(path.name for path in service.DEFAULTS_DIR.glob("*.yml"))


def test_a_missing_directory_is_initialised_from_the_shipped_files(tmp_path, monkeypatch):
    target = tmp_path / "nouvelle-instance" / "library"
    monkeypatch.setenv("SPECTRE_LIBRARY_DIR", str(target))

    assert service.library_dir() == target.resolve()
    assert sorted(path.name for path in target.iterdir()) == SHIPPED
    assert (target / "presets.yml").read_text(encoding="utf-8") == (service.DEFAULTS_DIR / "presets.yml").read_text(encoding="utf-8")


def test_an_existing_directory_is_left_alone(tmp_path, monkeypatch):
    target = tmp_path / "library"
    target.mkdir()
    (target / "presets.yml").write_text("presets: []\n", encoding="utf-8")
    monkeypatch.setenv("SPECTRE_LIBRARY_DIR", str(target))

    service.library_dir()
    assert [path.name for path in target.iterdir()] == ["presets.yml"]
    assert (target / "presets.yml").read_text(encoding="utf-8") == "presets: []\n"


def test_without_the_variable_the_library_lives_in_the_data_directory(tmp_path, monkeypatch):
    monkeypatch.delenv("SPECTRE_LIBRARY_DIR")
    monkeypatch.setenv("SPECTRE_DATA_DIR", str(tmp_path / "data"))

    assert service.library_dir() == (tmp_path / "data" / "library").resolve()
    assert Path(tmp_path / "data" / "library" / "materiaux.yml").is_file()


def test_every_shipped_file_is_valid():
    for file in service.library_files():
        service.parse_text(file, (service.DEFAULTS_DIR / file.filename).read_text(encoding="utf-8"))


def test_an_older_install_keeps_its_edits_from_the_repository_library(tmp_path, monkeypatch):
    """Avant <données>/library, l'admin éditait <dépôt>/library : à la création du dossier, ses
    *.yml priment sur les fichiers livrés (les autres viennent des fichiers livrés)."""
    legacy = tmp_path / "depot" / "library"
    legacy.mkdir(parents=True)
    (legacy / "presets.yml").write_text("presets: []\n", encoding="utf-8")
    (legacy / "README.md").write_text("doc\n", encoding="utf-8")
    monkeypatch.setattr(service, "LEGACY_DIR", legacy)
    target = tmp_path / "library"
    monkeypatch.setenv("SPECTRE_LIBRARY_DIR", str(target))

    service.library_dir()
    assert sorted(path.name for path in target.iterdir()) == SHIPPED
    assert (target / "presets.yml").read_text(encoding="utf-8") == "presets: []\n"
    assert (target / "briques.yml").read_text(encoding="utf-8") == (service.DEFAULTS_DIR / "briques.yml").read_text(encoding="utf-8")
    assert not (tmp_path / ".library.tmp").exists()
