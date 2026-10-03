"""``spectre.kernel.fs.replace`` : le remplacement atomique réessaie quand Windows tient la cible."""

from __future__ import annotations

import pytest

from spectre.kernel import fs


@pytest.fixture(autouse=True)
def _no_wait(monkeypatch):
    monkeypatch.setattr(fs, "REPLACE_DELAY_SECONDS", 0)


def test_a_target_held_for_a_moment_is_replaced_on_a_later_attempt(tmp_path, monkeypatch):
    src, dst = tmp_path / "new", tmp_path / "file"
    src.write_text("nouveau", encoding="utf-8")
    dst.write_text("ancien", encoding="utf-8")
    real_replace = fs.os.replace
    calls = []

    def held_twice(a, b):
        calls.append(a)
        if len(calls) <= 2:
            raise PermissionError(13, "Accès refusé")
        real_replace(a, b)

    monkeypatch.setattr(fs.os, "replace", held_twice)
    fs.replace(src, dst)
    assert len(calls) == 3
    assert dst.read_text(encoding="utf-8") == "nouveau"
    assert not src.exists()


def test_a_target_held_for_good_gives_up_with_the_last_error(tmp_path, monkeypatch):
    calls = []

    def always_held(a, b):
        calls.append(a)
        raise PermissionError(13, "Accès refusé")

    monkeypatch.setattr(fs.os, "replace", always_held)
    with pytest.raises(PermissionError):
        fs.replace(tmp_path / "new", tmp_path / "file")
    assert len(calls) == fs.REPLACE_ATTEMPTS


def test_any_other_error_is_not_retried(tmp_path, monkeypatch):
    calls = []

    def disk_full(a, b):
        calls.append(a)
        raise OSError("disque plein")

    monkeypatch.setattr(fs.os, "replace", disk_full)
    with pytest.raises(OSError, match="disque plein"):
        fs.replace(tmp_path / "new", tmp_path / "file")
    assert len(calls) == 1
