"""Les refs locales d'avant les références (des étiquettes Follow nommées à la main), regroupées
**une fois** par la migration ``0005_local_refs_imported_once`` (``references.local_refs``) : seuls
les noms portés dans au moins deux µprojets deviennent des références (le cas de
« epitaxie-standard », posée dans les deux µprojets de la démo), chaque étiquette une version dans
l'ordre des dates ; les autres refs nommées restent des repères locaux, publiables à la main ; les
noms automatiques « ref vX.Y.Z » restent locaux ; ce que l'ancienne règle avait importé d'un seul
µprojet est retiré s'il n'a ni publication à la main ni usage, ni version d'un µprojet supprimé ;
les étiquettes dont un admin avait retiré la référence ne reviennent pas ; rien n'est réécrit dans
les dépôts Follow ; après la migration, plus rien n'est regroupé. La migration ayant déjà tourné sur
la base (vide) du test, chaque test la rejoue sur ce qu'il a posé (``_migrate``)."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from support.accounts import login
from support.experiments import evolve, launch, launch_campaign, legacy_tag, legacy_tags
from support.microprojects import (
    create_microproject,
    delete_microproject,
    signup_with_microproject,
)
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
TRACKING_TABLES = ("reference_import_scans", "reference_import_rules", "dismissed_local_refs")


def _follow_files(data_dir: Path) -> dict[str, str]:
    """Le contenu de chaque fichier des dépôts Follow (objets et ``refs.json``), par chemin."""
    return {
        str(path.relative_to(data_dir)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((data_dir / "microprojects").rglob("follow/**/*"))
        if path.is_file()
    }


def _two_microprojects(client):
    """Comme la démo d'avant : deux µprojets, chacun avec la ref « epitaxie-standard » sur la même
    structure ; le premier a aussi deux refs d'un même nom (casse et accents mis à part) sur une
    même piste, une autre ref nommée et une ref posée sur une campagne."""
    single = signup_with_microproject(client, "seed@example.com", "Puits simple")
    base = launch(client, single, title="Epitaxie", intent="Depart", steps=steps(20))
    legacy_tag(client, single, base["id"], "epitaxie-standard")
    evolved = evolve(client, single, base["id"], title="Epitaxie", intent="Suite", steps=steps(25))
    legacy_tag(client, single, base["id"], "Recette Approuvée", version_id=base["version_id"])
    legacy_tag(client, single, base["id"], "recette-approuvee-2", version_id=evolved["version_id"])
    legacy_tag(client, single, base["id"], "recette approuvée!", version_id=evolved["version_id"])  # même nom normalisé que la première
    campaign = launch_campaign(client, single)
    legacy_tag(client, single, campaign["id"], "campagne-de-reference")

    mqw = create_microproject(client, "MQW")["slug"]
    other = launch(client, mqw, title="Epitaxie MQW", intent="Depart", steps=steps(20))
    legacy_tag(client, mqw, other["id"], "epitaxie-standard")
    return single, mqw, base, other


def _ref_names(client, slug: str) -> set[str]:
    return legacy_tags(slug)


def _migrate() -> list[str]:
    """Rejoue le regroupement de la migration sur la base du test."""
    from spectre.kernel.db import get_conn
    from spectre.plugins.references.local_refs import import_shared_local_refs

    with get_conn() as conn:
        return import_shared_local_refs(conn)


def _tables() -> set[str]:
    from spectre.kernel.db import get_conn

    with get_conn() as conn:
        return {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


def test_the_migration_has_run_and_dropped_the_tracking_tables(client):
    from spectre.kernel.db import get_conn

    assert not set(TRACKING_TABLES) & _tables()
    with get_conn() as conn:
        applied = {row["migration_id"] for row in conn.execute("SELECT migration_id FROM schema_migrations WHERE plugin = 'references'")}
    assert "0005_local_refs_imported_once" in applied


def test_only_names_shared_by_two_microprojects_become_references(client, data_dir):
    single, mqw, base, other = _two_microprojects(client)
    before = _follow_files(data_dir)
    assert references(client) == []  # lire les références ne regroupe plus rien

    assert sorted(set(_migrate())) == ["epitaxie-standard"]
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
    assert "epitaxie-standard" in _ref_names(client, single)
    assert {"Recette Approuvée", "recette-approuvee-2", "recette approuvée!", "campagne-de-reference"} <= _ref_names(client, single)
    assert [p["number"] for p in published_from(client, mqw)] == ["1.1"]
    assert [p["number"] for p in published_from(client, single)] == ["1.0"]
    assert get_version(client, "epitaxie-standard", "1.1")["process"]["steps"]

    # une ref locale restée locale se publie à la main : son nom (slug compris) est libre
    assert create_reference(client, "Recette approuvée")["slug"] == "recette-approuvee"
    assert publish(client, "recette-approuvee", single, base["id"], version_id=base["version_id"])["number"] == "1.0"
    nodes = version_graph(client, "recette-approuvee")["nodes"]
    assert [(n["number"], n["imported"], n["source"]["local_tag"]) for n in nodes] == [("1.0", False, None)]


def test_the_import_is_done_once_and_nothing_is_grouped_afterwards(client, data_dir):
    _two_microprojects(client)
    _migrate()
    first = references(client)
    assert _migrate() == []  # idempotent : rien de nouveau à importer
    assert references(client) == first

    # une ref nommée posée après (un dépôt copié d'ailleurs) reste un repère local
    late = create_microproject(client, "Tardif")["slug"]
    study = launch(client, late, title="Epitaxie", intent="x", steps=steps(40))
    legacy_tag(client, late, study["id"], "epitaxie-standard")
    assert references(client) == first
    assert [n["number"] for n in version_graph(client, "epitaxie-standard")["nodes"]] == ["1.0", "1.1"]
    assert "epitaxie-standard" in _ref_names(client, late)


def test_a_local_ref_joins_an_existing_reference_of_the_same_name(client):
    slug = signup_with_microproject(client, "join@example.com", "Epi")
    study = launch(client, slug, title="Epitaxie", intent="x", steps=steps(20))
    legacy_tag(client, slug, study["id"], "Épitaxie Standard")
    created = create_reference(client, "epitaxie standard")  # déclarée à la main, sans version
    other = create_microproject(client, "Autre")["slug"]
    launched = launch(client, other, title="Epitaxie", intent="x", steps=steps(30))
    legacy_tag(client, other, launched["id"], "epitaxie-standard")

    # le nom est porté par deux µprojets : les deux étiquettes rejoignent la référence existante
    _migrate()
    assert [(r["name"], r["version_count"]) for r in references(client)] == [("epitaxie standard", 2)]
    nodes = version_graph(client, created["slug"])["nodes"]
    assert [(n["number"], n["source"]["local_tag"], n["change_level"], n["parent_inferred"]) for n in nodes] == [
        ("1.0", "Épitaxie Standard", "initial", False),
        ("1.1", "epitaxie-standard", "minor", True),
    ]


# -- une installation d'avant la migration -------------------------------------------------------------


def _tracking_tables_as_before_the_migration() -> None:
    """Les tables que la migration supprime, telles qu'elles étaient (migrations 0001, 0003, 0004)."""
    from spectre.kernel.db import get_conn
    from spectre.plugins.references import migrations

    with get_conn() as conn:
        for script in (migrations.SCHEMA, migrations.IMPORT_RULES, migrations.DISMISSED_TAGS):
            conn.executescript(script)


def _as_under_the_old_rule(user_id: int) -> None:
    """L'état d'une installation où l'ancienne règle a tourné : chaque ref nommée (un procédé dessiné)
    de chaque µprojet est une version de la référence de son nom, tous les µprojets sont lus, la
    règle du 2026-10-05 n'est pas encore passée. « puits-simple-reference » a en plus une version
    publiée à la main, et « a-renommer » a été renommée."""
    from spectre.kernel.db import get_conn
    from spectre.plugins.microprojects import service as microprojects
    from spectre.plugins.references import local_refs, service

    _tracking_tables_as_before_the_migration()
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


def _run_the_migration() -> None:
    from spectre.kernel.db import get_conn
    from spectre.plugins.references.migrations import MIGRATIONS

    migration = next(m for m in MIGRATIONS if m.id == "0005_local_refs_imported_once")
    with get_conn() as conn:
        migration.apply(conn)


def test_the_old_rule_imports_from_a_single_microproject_are_retired(client, data_dir):
    from spectre.kernel.db import get_conn

    single, mqw, base, other = _two_microprojects(client)
    legacy_tag(client, single, base["id"], "puits-simple-reference")
    legacy_tag(client, single, base["id"], "a-renommer")
    me = client.get("/api/users/me").json()
    # une étude du MQW est partie de « recette-approuvee-2 » 1.0 (un usage)
    launch(client, mqw, title="Depuis la recette", intent="x", steps=steps(25), reference_origin=origin("recette-approuvee-2", "1.0"))
    _as_under_the_old_rule(me["id"])
    before = _follow_files(data_dir)

    _run_the_migration()
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
    # ses étiquettes restent des repères locaux, aucun fichier Follow n'est touché, les tables de
    # suivi du regroupement sont parties
    assert {"Recette Approuvée", "recette approuvée!"} <= _ref_names(client, single)
    assert _follow_files(data_dir) == before
    assert not set(TRACKING_TABLES) & _tables()
    # rejouée (ce que le démarrage ne fait jamais), rien ne change
    _run_the_migration()
    assert references(client) == listed
    assert create_reference(client, "Recette approuvée")["slug"] == "recette-approuvee"


def test_the_old_rule_keeps_references_whose_microprojects_were_deleted(client):
    from spectre.kernel.db import get_conn

    single, mqw, base, other = _two_microprojects(client)
    legacy_tag(client, single, base["id"], "puits-simple-reference")
    legacy_tag(client, single, base["id"], "a-renommer")
    me = client.get("/api/users/me").json()
    _as_under_the_old_rule(me["id"])
    # les deux µprojets sont supprimés avant que la règle passe : les versions de leurs références
    # n'ont plus de µprojet (microproject_id vide), leur instantané est la seule copie qui reste
    assert delete_microproject(client, single, "Puits simple").status_code == 204
    assert delete_microproject(client, mqw, "MQW").status_code == 204
    with get_conn() as conn:
        before = sorted(row["slug"] for row in conn.execute("SELECT slug FROM structure_references"))
    assert "epitaxie-standard" in before and "recette-approuvee" in before
    _run_the_migration()
    assert sorted(r["slug"] for r in references(client)) == before
    assert [n["number"] for n in version_graph(client, "epitaxie-standard")["nodes"]] == ["1.0", "1.1"]


def test_tags_dismissed_by_an_admin_before_the_migration_are_not_imported(client):
    from spectre.kernel.db import get_conn
    from spectre.plugins.microprojects import service as microprojects

    single, mqw, base, other = _two_microprojects(client)
    _tracking_tables_as_before_the_migration()
    # l'admin avait retiré la référence « epitaxie-standard » regroupée d'avant : ses étiquettes ne
    # comptent plus pour le partage (dismissed_local_refs), la règle est passée
    with get_conn() as conn:
        conn.executemany(
            "INSERT INTO dismissed_local_refs (microproject_id, local_tag, dismissed_at) VALUES (?, ?, ?)",
            [(microprojects.get_by_slug(slug).id, "epitaxie-standard", "2026-10-06T00:00:00") for slug in (single, mqw)],
        )
        conn.execute("INSERT INTO reference_import_rules (rule, applied_at) VALUES ('shared-names-2026-10-05', '2026-10-06T00:00:00')")
    _run_the_migration()
    assert references(client) == []
    assert "epitaxie-standard" in _ref_names(client, single) and "epitaxie-standard" in _ref_names(client, mqw)


# -- la démo -------------------------------------------------------------------------------------------


@pytest.mark.slow
def test_the_demo_publishes_its_references_without_local_refs(data_dir):
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(ROOT), os.environ.get("PYTHONPATH", "")]), "PYTHONIOENCODING": "utf-8"}
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "seed_demo.py"), "--data-dir", str(data_dir)], check=True, cwd=ROOT, env=env, capture_output=True
    )
    before = _follow_files(data_dir)

    from spectre.kernel.app import create_app

    with TestClient(create_app()) as client:
        login(client, "demo@spectre.local", "demo1234")
        single, mqw = "nanofils-gan-puits-quantique-simple", "nanofils-gan-puits-quantiques-multiples-mqw"
        # les points de départ de la démo sont des références publiées, aucune ref locale n'est posée
        assert {r["slug"] for r in references(client)} == {"epitaxie-standard", "puits-simple-reference", "mqw-ebl-reference", "mqw-dopage-optimise"}
        assert _ref_names(client, single) == _ref_names(client, mqw) == set()
        assert all(not n["imported"] for n in version_graph(client, "epitaxie-standard")["nodes"])
        assert {p["reference"]["slug"] for p in published_from(client, single)} == {"epitaxie-standard", "puits-simple-reference"}
        assert {"mqw-ebl-reference", "mqw-dopage-optimise"} <= {p["reference"]["slug"] for p in published_from(client, mqw)}
    assert _follow_files(data_dir) == before
