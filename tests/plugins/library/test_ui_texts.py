"""Les textes de la section « Objectifs et intention » du constructeur, sans µprojet."""

from __future__ import annotations

from support.accounts import signup
from support.http import assert_ok


def test_the_intention_texts_need_no_microproject(client):
    signup(client, "reader@example.com")
    texts = assert_ok(client.get("/api/ui-texts/intention"))
    assert texts["section_title"]
    assert [d["value"] for d in texts["objective_directions"]] == ["observe", "maximize", "minimize", "target"]


def test_a_partial_file_is_merged_over_the_builtin_texts(client):
    signup(client, "admin@example.com")  # le premier compte est administrateur
    assert_ok(client.put("/api/library/files/intention", json={"content": "title_label: Nom de l'étude\n"}))

    texts = assert_ok(client.get("/api/ui-texts/intention"))
    assert texts["title_label"] == "Nom de l'étude"
    assert texts["intent_label"] == "Ce que je veux démontrer"
