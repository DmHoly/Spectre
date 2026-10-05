"""Les versions d'une référence de structure : publiées depuis une étude d'un µprojet, numérotées
MAJEUR.MINEUR par le serveur (comparées à la version de référence dont elles dérivent), avec un
instantané de la structure qui se dessine, se reprend et se compare sans l'étude source."""

from __future__ import annotations

import threading

from fastapi.testclient import TestClient

from spectre.plugins.references.service import next_number
from support.experiments import evolve, launch
from support.http import assert_handler_404
from support.microprojects import signup_with_microproject
from support.references import (
    create_reference,
    get_reference,
    get_version,
    post_version,
    publish,
    references,
    version_graph,
)
from support.structures import deposition, etch, fixed_step_id, identified, layer_label

STACK = identified([deposition("Tampon AlN", "AlN", thickness_nm=20), deposition("GaN", "GaN", thickness_nm=60)])
THICKER = identified([deposition("Tampon AlN", "AlN", thickness_nm=30), deposition("GaN", "GaN", thickness_nm=60)])
WITH_ETCH = identified([deposition("Tampon AlN", "AlN", thickness_nm=20), deposition("GaN", "GaN", thickness_nm=60), etch(depth_nm=10)])


def test_the_number_rule():
    assert next_number([], None, "initial") == (1, 0)
    assert next_number([(1, 0)], (1, 0), "minor") == (1, 1)
    assert next_number([(1, 0)], (1, 0), "patch") == (1, 1)  # un correctif est un mineur
    assert next_number([(1, 0), (1, 1)], (1, 0), "minor") == (1, 2)  # deux dérivations de 1.0
    assert next_number([(1, 0), (1, 1)], (1, 1), "major") == (2, 0)
    assert next_number([(1, 0), (2, 0), (1, 1)], (1, 1), "major") == (3, 0)  # 2.0 existe déjà
    assert next_number([(1, 0), (2, 0), (1, 1)], (1, 0), "minor") == (1, 2)
    assert next_number([(1, 0), (1, 1)], (1, 1), "none") == (1, 2)  # import d'une version identique


def _aln(thickness_nm: float) -> list[dict]:
    return identified([deposition("Tampon AlN", "AlN", thickness_nm=thickness_nm), deposition("GaN", "GaN", thickness_nm=60)])


def _study(client, slug, process_steps=STACK, **fields):
    return launch(client, slug, title="Epitaxie", intent="Depart", steps=process_steps, **fields)


def test_publish_numbers_each_version_from_its_parent(client):
    slug = signup_with_microproject(client, "ref-numbers@example.com", "Epi")
    study = _study(client, slug)
    reference = create_reference(client, "Epitaxie standard", "Le tampon AlN de base")
    assert (reference["slug"], reference["version_count"], reference["latest_version"]) == ("epitaxie-standard", 0, None)

    first = publish(client, "epitaxie-standard", slug, study["id"], note="Recette approuvée")
    assert (first["number"], first["change_level"], first["parent"]) == ("1.0", "initial", None)
    assert first["note"] == "Recette approuvée"
    assert first["source"]["microproject"]["slug"] == slug
    assert (first["source"]["experiment_id"], first["source"]["version_id"]) == (study["id"], study["version_id"])
    assert first["published_by"]["name"] == "T"

    # même structure : rien à publier
    same = post_version(client, "epitaxie-standard", slug, study["id"])
    assert same.status_code == 409 and same.json()["code"] == "reference_version_identical"

    # un réglage (épaisseur) : mineur
    thicker = evolve(client, slug, study["id"], title="Epitaxie", intent="Plus epais", steps=THICKER)
    minor = publish(client, "epitaxie-standard", slug, study["id"])
    assert (minor["number"], minor["change_level"], minor["parent"]) == ("1.1", "minor", "1.0")
    assert minor["source"]["version_id"] == thicker["version_id"]

    # une étiquette seule (un correctif) : le mineur suivant
    evolve(client, slug, study["id"], title="Epitaxie", intent="Etiquette", steps=THICKER, layer_labels={"0": layer_label("AlN", "thickness")})
    patch = publish(client, "epitaxie-standard", slug, study["id"])
    assert (patch["number"], patch["change_level"]) == ("1.2", "patch")

    # une étape de plus : majeur
    evolve(client, slug, study["id"], title="Epitaxie", intent="Gravure", steps=WITH_ETCH)
    major = publish(client, "epitaxie-standard", slug, study["id"])
    assert (major["number"], major["change_level"], major["parent"]) == ("2.0", "major", "1.2")

    listed = references(client)
    assert [r["slug"] for r in listed] == ["epitaxie-standard"]
    assert listed[0]["version_count"] == 4
    assert listed[0]["latest_version"]["number"] == "2.0"
    assert listed[0]["latest_version"]["source"]["microproject"]["slug"] == slug


def test_parallel_derivations_get_unique_numbers(client):
    slug = signup_with_microproject(client, "ref-branches@example.com", "Epi")
    base = _study(client, slug)
    create_reference(client, "Base")
    publish(client, "base", slug, base["id"])

    # deux études qui partent toutes deux de 1.0
    a = launch(client, slug, title="A", intent="x", steps=THICKER)
    b = launch(client, slug, title="B", intent="x", steps=identified([deposition("Tampon AlN", "AlN", thickness_nm=40), deposition("GaN", "GaN", thickness_nm=60)]))
    assert publish(client, "base", slug, a["id"], parent="1.0")["number"] == "1.1"
    assert publish(client, "base", slug, b["id"], parent="1.0")["number"] == "1.2"

    # un majeur depuis 1.0 : 2.0 ; un autre majeur depuis 1.1, quand 2.0 existe : 3.0
    c = launch(client, slug, title="C", intent="x", steps=WITH_ETCH)
    assert publish(client, "base", slug, c["id"], parent="1.0")["number"] == "2.0"
    d = launch(client, slug, title="D", intent="x", steps=identified([deposition("Tampon AlN", "AlN", thickness_nm=30)]))
    assert publish(client, "base", slug, d["id"], parent="1.1")["number"] == "3.0"

    graph = version_graph(client, "base")
    assert [n["number"] for n in graph["nodes"]] == ["1.0", "1.1", "1.2", "2.0", "3.0"]
    lanes = {n["number"]: n["lane"] for n in graph["nodes"]}
    # 1.1 continue la colonne de 1.0 ; 1.2 et 2.0, ses autres enfants, ouvrent chacun la leur ; 3.0 suit 1.1
    assert lanes == {"1.0": 0, "1.1": 0, "1.2": 1, "2.0": 2, "3.0": 0}
    assert {(e["parent"], e["child"], e["kind"]) for e in graph["edges"]} == {
        ("1.0", "1.1", "parent"),
        ("1.0", "1.2", "branch"),
        ("1.0", "2.0", "branch"),
        ("1.1", "3.0", "parent"),
    }
    assert [lane["head"] for lane in graph["lanes"]] == ["3.0", "1.2", "2.0"]

    unknown = post_version(client, "base", slug, a["id"], parent="9.9")
    assert unknown.status_code == 422 and unknown.json()["code"] == "unknown_parent_version"


def test_concurrent_publications_never_share_a_number(app):
    with TestClient(app) as client:
        slug = signup_with_microproject(client, "ref-race@example.com", "Epi")
        create_reference(client, "Course")
        publish(client, "course", slug, _study(client, slug)["id"])
        studies = [launch(client, slug, title=f"E{i}", intent="x", steps=_aln(21 + i)) for i in range(6)]
        cookies = client.cookies

    results: list[int] = []

    def run(study_id: str) -> None:
        with TestClient(app, cookies=cookies) as other:
            results.append(post_version(other, "course", slug, study_id, parent="1.0").status_code)

    threads = [threading.Thread(target=run, args=(study["id"],)) for study in studies]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert results == [201] * 6
    with TestClient(app, cookies=cookies) as client:
        numbers = [n["number"] for n in version_graph(client, "course")["nodes"]]
    assert sorted(numbers) == ["1.0", "1.1", "1.2", "1.3", "1.4", "1.5", "1.6"]


def test_a_version_shows_its_structure_and_its_process(client):
    slug = signup_with_microproject(client, "ref-snapshot@example.com", "Epi")
    labels = {"1": layer_label("GaN", "thickness")}
    study = _study(client, slug, declared_params={"1": [{"name": "dopage", "value": 3e18, "unit": "cm⁻³"}]}, layer_labels=labels)
    create_reference(client, "Snap")
    publish(client, "snap", slug, study["id"])

    version = get_version(client, "snap", "1.0")
    assert version["reference"] == {"slug": "snap", "name": "Snap"}
    assert version["structure_svg"].startswith("<svg") and "sp-layer-labels" in version["structure_svg"]
    process = version["process"]
    assert [step["id"] for step in process["steps"]] == [fixed_step_id(1), fixed_step_id(2)]
    assert process["layer_labels"] == {"1": {"text": "GaN", "values": ["thickness"]}}
    assert process["declared_params"]["1"][0]["unit"] == "cm⁻³"

    # l'étude source disparaît : la version reste lisible
    assert client.delete(f"/api/microprojects/{slug}/experiments/{study['id']}").status_code == 204
    again = get_version(client, "snap", "1.0")
    assert again["structure_svg"] == version["structure_svg"] and again["process"] == process

    assert_handler_404(client.get("/api/references/snap/versions/4.2"))
    assert_handler_404(client.get("/api/references/inconnue"))


def test_only_a_drawn_process_can_be_published(client):
    slug = signup_with_microproject(client, "ref-campaign@example.com", "Epi")
    from support.experiments import launch_campaign

    campaign = launch_campaign(client, slug)
    create_reference(client, "Campagne")
    response = post_version(client, "campagne", slug, campaign["id"])
    assert response.status_code == 422 and response.json()["code"] == "reference_needs_process"
    assert get_reference(client, "campagne")["version_count"] == 0


def test_publishing_from_an_unknown_microproject_or_study(client):
    slug = signup_with_microproject(client, "ref-unknown@example.com", "Epi")
    create_reference(client, "R")
    response = post_version(client, "r", "nulle-part", "x")
    assert response.status_code == 422 and response.json()["code"] == "unknown_microproject"
    assert_handler_404(post_version(client, "r", slug, "pas-de-piste"))
    assert_handler_404(post_version(client, "inconnue", slug, _study(client, slug)["id"]))
