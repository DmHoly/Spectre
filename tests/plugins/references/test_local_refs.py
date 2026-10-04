"""Les refs locales d'avant les références (des étiquettes Follow nommées à la main) deviennent des
références à la première lecture : regroupées par nom normalisé entre µprojets (le cas de
« epitaxie-standard », posée dans les deux µprojets de la démo), chaque étiquette une version dans
l'ordre des dates ; les noms automatiques « ref vX.Y.Z » restent locaux ; rien n'est réécrit dans
les dépôts Follow, et l'import ne se fait qu'une fois."""

from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi.testclient import TestClient

from support.experiments import create_ref, evolve, launch, launch_campaign
from support.experiments import get_version as get_version_of_study
from support.microprojects import create_microproject, signup_with_microproject
from support.references import get_version, published_from, references, version_graph
from support.structures import steps


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
    même piste, et une ref posée sur une campagne."""
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


def test_local_refs_are_grouped_into_references(client, data_dir):
    single, mqw, base, other = _two_microprojects(client)
    before = _follow_files(data_dir)

    listed = {r["slug"]: r for r in references(client)}
    # les refs automatiques (« ref v1.0.0 » de la première étude de chaque µprojet) restent locales ;
    # une campagne n'est pas un procédé dessiné : sa ref reste locale
    assert set(listed) == {"epitaxie-standard", "recette-approuvee", "recette-approuvee-2"}

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

    # deux étiquettes d'un même nom sur une piste : la seconde descend de la première
    recipe = version_graph(client, "recette-approuvee")["nodes"]
    assert [(n["number"], n["parent"], n["parent_inferred"], n["change_level"]) for n in recipe] == [
        ("1.0", None, False, "initial"),
        ("1.1", "1.0", False, "minor"),
    ]

    # les étiquettes restent en place, aucun objet Follow n'est réécrit
    assert _follow_files(data_dir) == before
    assert "epitaxie-standard" in get_version_of_study(client, single, base["id"], base["version_id"])["ref_names"]
    assert [p["number"] for p in published_from(client, mqw)] == ["1.1"]
    assert get_version(client, "epitaxie-standard", "1.1")["process"]["steps"]


def test_the_import_happens_once(app, client, data_dir):
    _two_microprojects(client)
    first = references(client)
    again = references(client)
    assert again == first
    with TestClient(app) as restarted:
        restarted.cookies = client.cookies
        assert references(restarted) == first

    # un µprojet créé ensuite est lu une fois, vide : une ref locale nommée plus tard reste locale
    late = create_microproject(client, "Tardif")["slug"]
    references(client)
    study = launch(client, late, title="Epitaxie", intent="x", steps=steps(40))
    create_ref(client, late, study["id"], "epitaxie-standard")
    assert [n["number"] for n in version_graph(client, "epitaxie-standard")["nodes"]] == ["1.0", "1.1"]


def test_a_local_ref_joins_an_existing_reference_of_the_same_name(client):
    slug = signup_with_microproject(client, "join@example.com", "Epi")
    study = launch(client, slug, title="Epitaxie", intent="x", steps=steps(20))
    create_ref(client, slug, study["id"], "Épitaxie Standard")
    # la première lecture importe l'étiquette : la référence porte son nom
    response = client.post("/api/references", json={"name": "epitaxie standard"})
    assert response.status_code == 409 and response.json()["code"] == "reference_name_taken"
    assert [(r["name"], r["version_count"]) for r in references(client)] == [("Épitaxie Standard", 1)]

    # un µprojet pas encore lu : son étiquette du même nom rejoint la référence existante
    other = create_microproject(client, "Autre")["slug"]
    launched = launch(client, other, title="Epitaxie", intent="x", steps=steps(30))
    create_ref(client, other, launched["id"], "epitaxie-standard")
    nodes = version_graph(client, "epitaxie-standard")["nodes"]
    assert [(n["number"], n["change_level"], n["parent_inferred"]) for n in nodes] == [("1.0", "initial", False), ("1.1", "minor", True)]
