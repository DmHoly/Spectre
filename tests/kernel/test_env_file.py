from __future__ import annotations

import os

from spectre.kernel import env


def test_parse_handles_comments_quotes_and_export():
    text = "# c\nA=1\nexport B = 'x y'\nC=\"z\"\nD=v # note\n\nbad line\n"
    assert env.parse(text) == {"A": "1", "B": "x y", "C": "z", "D": "v"}


def test_load_env_sets_missing_variables_only(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text("PRISM_PASSWORD=from-file\nPRISM_USER=file-user\n", encoding="utf-8")
    monkeypatch.setenv("SPECTRE_ENV_FILE", str(f))
    monkeypatch.delenv("PRISM_PASSWORD", raising=False)
    monkeypatch.setenv("PRISM_USER", "real-env")
    assert env.load_env() == ["PRISM_PASSWORD"]
    assert os.environ["PRISM_PASSWORD"] == "from-file"
    assert os.environ["PRISM_USER"] == "real-env"
    monkeypatch.delenv("PRISM_PASSWORD")


def test_missing_file_is_fine(tmp_path, monkeypatch):
    monkeypatch.setenv("SPECTRE_ENV_FILE", str(tmp_path / "nope"))
    assert env.load_env() == []
