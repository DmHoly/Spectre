"""Les commentaires d'étape : un texte par étape (son id) d'un µprojet, lu et écrit sous son rôle ;
le constructeur et la fiche d'une étude chargent le plugin, et l'éteindre le retire."""

from __future__ import annotations

import pytest

from support.accounts import signup, switch_user
from support.http import assert_ok, plugins_off
from support.microprojects import create_microproject, join_as, signup_with_microproject
from support.step_report import comments, put_comment
from support.structures import fixed_step_id

STEP = fixed_step_id(1)
OTHER = fixed_step_id(2)
BUILDER = "/microprojets/x/structures/nouvelle"
STUDY = "/microprojets/x/experiences/e"


def test_a_comment_is_written_replaced_and_read_back(client):
    slug = signup_with_microproject(client, "boss@example.com", name="Boss")
    written = assert_ok(put_comment(client, slug, STEP, "  Dépôt lent, à vérifier  "))
    assert (written["step_id"], written["text"], written["updated_by"]) == (STEP, "Dépôt lent, à vérifier", "Boss")

    assert_ok(put_comment(client, slug, STEP, "Vérifié"))
    assert_ok(put_comment(client, slug, OTHER, "Autre étape"))
    assert {k: v["text"] for k, v in comments(client, slug, STEP).items()} == {STEP: "Vérifié"}
    everything = assert_ok(client.get(f"/api/microprojects/{slug}/step-comments"))["comments"]
    assert set(everything) == {STEP, OTHER}
    assert comments(client, slug, fixed_step_id(9)) == {}  # une étape sans commentaire est absente


def test_an_empty_comment_removes_it(client):
    slug = signup_with_microproject(client, "boss@example.com", name="Boss")
    assert_ok(put_comment(client, slug, STEP, "À retirer"))
    assert assert_ok(put_comment(client, slug, STEP, "   ")) == {"step_id": STEP, "text": ""}
    assert comments(client, slug, STEP) == {}


def test_malformed_input_is_refused(client):
    slug = signup_with_microproject(client, "boss@example.com", name="Boss")
    assert put_comment(client, slug, "pas-un-id", "x").status_code == 422
    assert put_comment(client, slug, STEP, "x" * 4001).json()["code"] == "comment_too_long"
    assert client.get(f"/api/microprojects/{slug}/step-comments", params={"step_id": "nope"}).status_code == 422
    too_many = [fixed_step_id(i) for i in range(501)]
    assert client.get(f"/api/microprojects/{slug}/step-comments", params={"step_id": too_many}).json()["code"] == "too_many_steps"


def test_a_comment_belongs_to_its_microproject_and_its_readers(client):
    slug = signup_with_microproject(client, "boss@example.com", "Projet A", name="Boss")
    assert_ok(put_comment(client, slug, STEP, "Secret du projet A"))
    join_as(client, slug, "reader@example.com", owner="boss@example.com", role="viewer", name="Lecteur")

    assert comments(client, slug, STEP)[STEP]["text"] == "Secret du projet A"  # un lecteur lit
    assert put_comment(client, slug, STEP, "Modifié").status_code == 403  # et n'écrit pas

    switch_user(client, "stranger@example.com", name="Autre")
    other = create_microproject(client, "Projet B")["slug"]
    assert comments(client, other, STEP) == {}  # le même id sous un autre µprojet : rien
    assert client.get(f"/api/microprojects/{slug}/step-comments").status_code == 403


@pytest.mark.parametrize(
    "page, asset",
    [
        (BUILDER, "client.js"),
        (BUILDER, "report-html.js"),
        (BUILDER, "report-core.js"),
        (BUILDER, "step-report.js"),
        (BUILDER, "step-report.css"),
        (STUDY, "client.js"),
        (STUDY, "report-html.js"),
        (STUDY, "report-core.js"),
        (STUDY, "study-report.js"),
    ],
)
def test_the_builder_and_the_study_page_load_the_plugin_and_turning_it_off_removes_it(client, page, asset):
    signup(client, "boss@example.com", name="Boss")  # le premier compte est administrateur
    assert f"/static/step_report/{asset}" in client.get(page).text

    assert client.patch("/api/plugins/step_report", json={"enabled": False}).status_code == 200
    off = client.get(page).text
    assert f"/static/step_report/{asset}" not in off and "step_report" in plugins_off(off)
    assert client.get("/api/microprojects/x/step-comments").json()["code"] == "plugin_disabled"

    assert client.patch("/api/plugins/step_report", json={"enabled": True}).json()["active"]
    assert f"/static/step_report/{asset}" in client.get(page).text
