"""Les refs locales d'avant les références (des étiquettes Follow nommées à la main) : seuls les noms
portés dans au moins deux µprojets deviennent des références (le cas de « epitaxie-standard », posée
dans les deux µprojets de la démo), chaque étiquette une version dans l'ordre des dates ; les autres
refs nommées restent des repères locaux, publiables à la main ; les noms automatiques
« ref vX.Y.Z » restent locaux ; le partage se décide sur tous les µprojets ; ce que l'ancienne règle
avait importé d'un seul µprojet est retiré s'il n'a ni publication à la main ni usage ; rien n'est
réécrit dans les dépôts Follow."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from support.accounts import login
from support.experiments import create_ref, evolve, launch, launch_campaign, refs
from support.experiments import get_version as get_version_of_study
from support.microprojects import create_microproject, signup_with_microproject
from support.references import (
    create_reference,
    get_version,
    origin,
    publish,
    published_from,
    references,
    version_graph,
)
from support.structures import steps

ROOT = Path(__file__).resolve().parents[3]


def _follow_files(data_dir: Path) -> dict[str, str]:
    """Le contenu de chaque fichier des dépôts Follow (objets et ``refs.json``), par chemin."""
    return {
        str(path.relative_to(data_dir)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((data_dir / "microprojects").rglob("follow/**/*"))
        if path.is_file()
    }


def _two_microprojects(client):
    """Comme la démo : deux µprojets, chacun avec la ref « epitaxie-standard » sur la même
    structure ; le premier a aussi deux refs d'un même nom (casse et accents mis à part) sur une
    même piste, une autre ref nommée et une ref posée sur une campagne."""
    single = signup_with_microproject(client, "seed@example.com", "Puits simple")
    base = launch(client, single, title="Epitaxie", intent="Depart", steps=steps(20))
    create_ref(client, single, base["id"], "epitaxie-standard")
    evolved = evolve(client, single, base["id"], title="Epitaxie", intent="Suite", steps=steps(25))
    create_ref(client, single, base["id"], "Recette Approuvée", version_id=base["version_id"])
    create_ref(client, single, base["id"], "recette-approuvee-2", version_id=evolved["version_id"])
    create_ref(client, single, base["id"], "recette approuvée!", version_id=evolved["version_id"])  # même nom normalisé que la première
    campaign = launch_campaign(client, single)
    create_ref(client, single, campaign["id"], "campagne-de-reference")

    mqw = create_microproject(client, "MQW")["slug"]
    other = launch(client, mqw, title="Epitaxie MQW", intent="Depart", steps=steps(20))
    create_ref(client, mqw, other["id"], "epitaxie-standard")
    return single, mqw, base, other


def _ref_names(client, slug: str) -> set[str]:
    return {name for ref in refs(client, slug)["refs"] for name in ref["names"]}


def test_only_names_shared_by_two_microprojects_become_references(client, data_dir):
    single, mqw, base, other = _two_microprojects(client)
    before = _follow_files(data_dir)

    listed = {r["slug"]: r for r in references(client)}
    # « recette-approuvee » et « recette-approuvee-2 » ne sont que dans un µprojet : repères locaux ;
    # les refs automatiques (« ref v1.0.0 ») et celle d'une campagne restent locales aussi
    assert set(listed) == {"epitaxie-standard"}

    epi = version_graph(client, "epitaxie-standard")
    assert epi["reference"]["name"] == "epitaxie-standard"
    nodes = epi["nodes"]
    assert [(n["number"], n["source"]["microproject"]["slug"], n["source"]["local_tag"], n["imported"]) for n in nodes] == [
        ("1.0", single, "epitaxie-standard", True),
        ("1.1", mqw, "epitaxie-standard", True),
    ]
    # l'étiquette du second µprojet ne descend d'aucune version du premier : rattachement déduit ;
    # même structure, gardée : change_level « none »
    assert (nodes[1]["parent"], nodes[1]["parent_inferred"], nodes[1]["change_level"]) == ("1.0", True, "none")
    assert nodes[0]["published_by"] is None and nodes[0]["published_at"]
    assert epi["edges"] == [{"parent": "1.0", "child": "1.1", "kind": "parent", "inferred": True}]
    assert (nodes[0]["source"]["version_id"], nodes[1]["source"]["version_id"]) == (base["version_id"], other["version_id"])
    # créée au nom du créateur du µprojet de sa première version
    assert listed["epitaxie-standard"]["created_by"]["name"] == "T"

    # les étiquettes restent en place, aucun objet Follow n'est réécrit
    assert _follow_files(data_dir) == before
    assert "epitaxie-standard" in get_version_of_study(client, single, base["id"], base["version_id"])["ref_names"]
    assert {"Recette Approuvée", "recette-approuvee-2", "recette approuvée!", "campagne-de-reference"} <= _ref_names(client, single)
    assert [p["number"] for p in published_from(client, mqw)] == ["1.1"]
    assert [p["number"] for p in published_from(client, single)] == ["1.0"]
    assert get_version(client, "epitaxie-standard", "1.1")["process"]["steps"]

    # une ref locale restée locale se publie à la main : son nom (slug compris) est libre
    assert create_reference(client, "Recette approuvée")["slug"] == "recette-approuvee"
    assert publish(client, "recette-approuvee", single, base["id"], version_id=base["version_id"])["number"] == "1.0"
    nodes = version_graph(client, "recette-approuvee")["nodes"]
    assert [(n["number"], n["imported"], n["source"]["local_tag"]) for n in nodes] == [("1.0", False, None)]


def test_the_import_happens_once(app, client, data_dir):
    _two_microprojects(client)
    first = references(client)
    again = references(client)
    assert again == first
    with TestClient(app) as restarted:
        restarted.cookies = client.cookies
        assert references(restarted) == first

    # un µprojet créé ensuite est lu une fois, vide : une ref locale posée après dans un µprojet lu
    # n'est pas importée tant qu'aucun regroupement ne passe
    late = create_microproject(client, "Tardif")["slug"]
    references(client)
    study = launch(client, late, title="Epitaxie", intent="x", steps=steps(40))
    create_ref(client, late, study["id"], "epitaxie-standard")
    assert [n["number"] for n in version_graph(client, "epitaxie-standard")["nodes"]] == ["1.0", "1.1"]


def test_a_name_shared_later_imports_the_tags_of_every_microproject(client, data_dir):
    first = signup_with_microproject(client, "later@example.com", "Premier")
    study = launch(client, first, title="Epitaxie", intent="x", steps=steps(20))
    create_ref(client, first, study["id"], "Recette X")
    # un seul µprojet porte le nom : repère local ; le µprojet est lu
    assert references(client) == []

    # un µprojet créé ensuite porte le même nom : le regroupement suivant importe aussi l'étiquette
    # du premier, déjà lu
    second = create_microproject(client, "Second")["slug"]
    launched = launch(client, second, title="Epitaxie", intent="x", steps=steps(30))
    create_ref(client, second, launched["id"], "recette-x")
    graph = version_graph(client, "recette-x")
    assert graph["reference"]["name"] == "Recette X"
    assert [(n["number"], n["source"]["microproject"]["slug"], n["source"]["local_tag"], n["change_level"], n["parent_inferred"]) for n in graph["nodes"]] == [
        ("1.0", first, "Recette X", "initial", False),
        ("1.1", second, "recette-x", "minor", True),
    ]

    # deux µprojets déjà lus partagent un nom après coup : le regroupement suivant (l'arrivée d'un
    # µprojet) le relit sur tous les µprojets
    create_ref(client, first, study["id"], "Base Y")
    create_ref(client, second, launched["id"], "base-y")
    before = _follow_files(data_dir)
    assert [r["slug"] for r in references(client)] == ["recette-x"]
    create_microproject(client, "Troisième")
    assert [n["source"]["local_tag"] for n in version_graph(client, "base-y")["nodes"]] == ["Base Y", "base-y"]
    assert [n["number"] for n in version_graph(client, "recette-x")["nodes"]] == ["1.0", "1.1"]
    assert _follow_files(data_dir) == before


def test_a_local_ref_joins_an_existing_reference_of_the_same_name(client):
    slug = signup_with_microproject(client, "join@example.com", "Epi")
    study = launch(client, slug, title="Epitaxie", intent="x", steps=steps(20))
    create_ref(client, slug, study["id"], "Épitaxie Standard")
    # un seul µprojet : l'étiquette reste locale, le nom est libre
    created = create_reference(client, "epitaxie standard")
    assert [(r["name"], r["version_count"]) for r in references(client)] == [("epitaxie standard", 0)]

    # un second µprojet porte le nom : les deux étiquettes rejoignent la référence existante
    other = create_microproject(client, "Autre")["slug"]
    launched = launch(client, other, title="Epitaxie", intent="x", steps=steps(30))
    create_ref(client, other, launched["id"], "epitaxie-standard")
    nodes = version_graph(client, created["slug"])["nodes"]
    assert [(n["number"], n["source"]["local_tag"], n["change_level"], n["parent_inferred"]) for n in nodes] == [
        ("1.0", "Épitaxie Standard", "initial", False),
        ("1.1", "epitaxie-standard", "minor", True),
    ]


# -- une installation où l'ancienne règle a tourné ---------------------------------------------------


def _as_under_the_old_rule(user_id: int) -> None:
    """L'état d'une installation où l'ancienne règle a tourné : chaque ref nommée (un procédé dessiné)
    de chaque µprojet est une version de la référence de son nom, tous les µprojets sont lus, la
    règle du 2026-10-05 n'est pas encore passée. « puits-simple-reference » a en plus une version
    publiée à la main, et « a-renommer » a été renommée."""
    from spectre.kernel.db import get_conn
    from spectre.plugins.microprojects import service as microprojects
    from spectre.plugins.references import local_refs, service

    everything = sorted(microprojects.list_all(), key=lambda mp: mp.id)
    candidates = sorted(
        (c for mp in everything for c in local_refs.candidates_of(mp)), key=lambda c: (c.version.created_at, c.microproject.id, c.name)
    )
    with get_conn() as conn:
        imported: dict = {}
        for candidate in candidates:
            local_refs.import_candidate(conn, candidate, imported)
        conn.executemany(
            "INSERT INTO reference_import_scans (microproject_id, scanned_at) VALUES (?, ?)", [(mp.id, service.now()) for mp in everything]
        )
        manual = next(c for c in candidates if c.name == "epitaxie-standard")
        reference = service.find_by_name(conn, "puits-simple-reference")
        imported_version = service.versions_of(conn, reference.id)[0]
        service.insert_version(
            conn,
            reference,
            number=(2, 0),
            parent=imported_version,
            parent_inferred=False,
            microproject=manual.microproject,
            experiment_id=manual.experiment_id,
            version_id=manual.version.id,
            local_tag=None,
            snapshot=manual.snapshot,
            change_level="major",
            note="",
            published_by=user_id,
            published_at=service.now(),
        )
        conn.execute(
            "UPDATE structure_references SET name = 'Renommée à la main', updated_at = ? WHERE slug = 'a-renommer'", (service.now(),)
        )


def test_the_old_rule_imports_from_a_single_microproject_are_retired(app, client, data_dir):
    from spectre.kernel.db import get_conn

    single, mqw, base, other = _two_microprojects(client)
    create_ref(client, single, base["id"], "puits-simple-reference")
    create_ref(client, single, base["id"], "a-renommer")
    me = client.get("/api/users/me").json()
    # une étude du MQW est partie de « recette-approuvee-2 » 1.0 (un usage)
    launch(client, mqw, title="Depuis la recette", intent="x", steps=steps(25), reference_origin=origin("recette-approuvee-2", "1.0"))
    _as_under_the_old_rule(me["id"])
    before = _follow_files(data_dir)

    listed = references(client)
    # retirée : « recette-approuvee » (deux versions, un seul µprojet, ni publication ni usage) ;
    # gardées : la référence partagée, celle qui a un usage, celle qui a une publication à la main et
    # celle qu'on a renommée
    assert sorted(r["slug"] for r in listed) == ["a-renommer", "epitaxie-standard", "puits-simple-reference", "recette-approuvee-2"]
    assert [n["number"] for n in version_graph(client, "puits-simple-reference")["nodes"]] == ["1.0", "2.0"]
    assert [n["number"] for n in version_graph(client, "epitaxie-standard")["nodes"]] == ["1.0", "1.1"]
    # son slug n'est pas réservé : aucune étude n'en était partie
    with get_conn() as conn:
        assert conn.execute("SELECT slug FROM retired_reference_slugs").fetchall() == []
    # ses étiquettes restent des repères locaux, aucun fichier Follow n'est touché
    assert {"Recette Approuvée", "recette approuvée!"} <= _ref_names(client, single)
    assert _follow_files(data_dir) == before

    # idempotent : relu, redémarré, ou la règle repassée, rien ne change
    assert references(client) == listed
    with TestClient(app) as restarted:
        restarted.cookies = client.cookies
        assert references(restarted) == listed
    with get_conn() as conn:
        conn.execute("DELETE FROM reference_import_rules")
    assert references(client) == listed
    assert _follow_files(data_dir) == before
    assert create_reference(client, "Recette approuvée")["slug"] == "recette-approuvee"


# -- la démo -------------------------------------------------------------------------------------------


def test_the_demo_shares_only_epitaxie_standard(data_dir):
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(ROOT), os.environ.get("PYTHONPATH", "")]), "PYTHONIOENCODING": "utf-8"}
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "seed_demo.py"), "--data-dir", str(data_dir)], check=True, cwd=ROOT, env=env, capture_output=True
    )
    before = _follow_files(data_dir)

    from spectre.kernel.app import create_app

    with TestClient(create_app()) as client:
        login(client, "demo@spectre.local", "demo1234")
        single, mqw = "nanofils-gan-puits-quantique-simple", "nanofils-gan-puits-quantiques-multiples-mqw"
        assert [r["slug"] for r in references(client)] == ["epitaxie-standard"]
        nodes = version_graph(client, "epitaxie-standard")["nodes"]
        assert [(n["number"], n["source"]["microproject"]["slug"], n["parent_inferred"]) for n in nodes] == [
            ("1.0", single, False),
            ("1.1", mqw, True),
        ]
        # les refs d'un seul µprojet restent des repères locaux
        assert {"epitaxie-standard", "puits-simple-reference"} <= _ref_names(client, single)
        assert {"epitaxie-standard", "mqw-ebl-reference", "mqw-dopage-optimise"} <= _ref_names(client, mqw)
        assert [p["reference"]["slug"] for p in published_from(client, single)] == ["epitaxie-standard"]
        assert [p["reference"]["slug"] for p in published_from(client, mqw)] == ["epitaxie-standard"]
    assert _follow_files(data_dir) == before
