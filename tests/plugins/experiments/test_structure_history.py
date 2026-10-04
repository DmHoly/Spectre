"""L'évolution des structures d'un µprojet (GET .../structure-history) : les versions piste par
piste, telles que la page « Évolution des structures » les dessine - les versions structurelles par
défaut (et celles qui portent une ref, les fusions, le début de chaque piste), toutes avec
``all_versions=true`` ; les fourches et les fusions en arêtes ; des pistes dans un ordre stable."""

from __future__ import annotations

from support.experiments import combine, create_ref, evolve, launch, structure_history, tag, write_old_merge
from support.microprojects import join_as, signup_with_microproject
from support.structures import deposition, etch, steps

OWNER = "history-owner@example.com"


def _microproject(client, email=OWNER):
    return signup_with_microproject(client, email, "Historique", name="Owner")


def _labels(body):
    return [node["label"] for node in body["nodes"]]


def _grow_a_line(client, slug):
    """Une piste : v1.0.0, une étiquette (légère), v1.1.0 (une épaisseur : mineure), v1.1.1 (un
    nom d'étape : correctif), v2.0.0 (une gravure ajoutée : majeure)."""
    launched = launch(client, slug, title="Empilement", intent="Depart", steps=steps(20))
    tagged = tag(client, slug, launched["id"], ["a-suivre"])
    minor = evolve(client, slug, launched["id"], title="Empilement", steps=steps(30))
    patch = evolve(client, slug, launched["id"], title="Empilement", steps=[deposition("Oxyde renomme", thickness_nm=30)])
    major = evolve(client, slug, launched["id"], title="Empilement", steps=[deposition("Oxyde renomme", thickness_nm=30), etch(depth_nm=5)])
    return launched, tagged, minor, patch, major


def test_an_empty_microproject_has_no_history(client):
    slug = _microproject(client)
    assert structure_history(client, slug) == {"lanes": [], "nodes": [], "edges": []}


def test_by_default_only_the_structural_versions_are_shown(client):
    slug = _microproject(client)
    launched, tagged, minor, patch, major = _grow_a_line(client, slug)

    body = structure_history(client, slug)
    assert _labels(body) == ["v1.0.0", "v1.1.0", "v2.0.0"]
    assert [node["change_level"] for node in body["nodes"]] == ["initial", "minor", "major"]
    assert [node["version_id"] for node in body["nodes"]] == [launched["version_id"], minor["version_id"], major["version_id"]]
    # les versions légères cachées, les arêtes passent au travers
    assert [(e["parent"], e["child"], e["kind"]) for e in body["edges"]] == [
        (launched["version_id"], minor["version_id"], "parent"),
        (minor["version_id"], major["version_id"], "parent"),
    ]
    node = body["nodes"][-1]
    assert node["experiment_id"] == launched["id"] and node["lane"] == 0
    assert node["is_tip"] is True and node["is_merge"] is False
    assert node["title"] == "Empilement" and node["author"] == "Owner" and node["created_at"]
    assert node["structure_kind"] == "process" and node["has_process"] is True
    assert body["lanes"] == [
        {
            "experiment_id": launched["id"],
            "index": 0,
            "title": "Empilement",
            "is_active": True,
            "tip_version_id": major["version_id"],
            "tip_label": "v2.0.0",
        }
    ]


def test_all_versions_adds_the_light_ones(client):
    slug = _microproject(client)
    launched, tagged, minor, patch, major = _grow_a_line(client, slug)

    body = structure_history(client, slug, all_versions=True)
    assert _labels(body) == ["v1.0.0", "v1.0.0", "v1.1.0", "v1.1.1", "v2.0.0"]
    assert [node["change_level"] for node in body["nodes"]] == ["initial", "none", "minor", "patch", "major"]
    assert [node["version_id"] for node in body["nodes"]][1] == tagged["version_id"]
    assert len(body["edges"]) == 4 and all(e["kind"] == "parent" for e in body["edges"])
    # explicitement « false » : comme par défaut
    assert _labels(structure_history(client, slug, all_versions=False)) == ["v1.0.0", "v1.1.0", "v2.0.0"]


def test_a_version_carrying_a_ref_is_shown_with_its_refs(client):
    slug = _microproject(client)
    launched, tagged, minor, patch, major = _grow_a_line(client, slug)
    create_ref(client, slug, launched["id"], "omega", version_id=patch["version_id"])

    nodes = {node["version_id"]: node for node in structure_history(client, slug)["nodes"]}
    assert nodes[patch["version_id"]]["refs"] == ["omega"]
    assert nodes[patch["version_id"]]["change_level"] == "patch"
    # la première étude d'un µprojet devient sa première ref
    assert nodes[launched["version_id"]]["refs"] == ["ref v1.0.0"]
    assert nodes[minor["version_id"]]["refs"] == []


def test_a_fork_starts_a_new_lane_even_without_a_structural_change(client):
    slug = _microproject(client)
    launched, tagged, minor, patch, major = _grow_a_line(client, slug)
    # une nouvelle piste depuis v1.1.0, même structure : son début se voit quand même
    fork = launch(
        client, slug, title="Variante", intent="Depuis v1.1.0", steps=steps(30),
        from_version={"experiment_id": launched["id"], "version_id": minor["version_id"]},
    )

    body = structure_history(client, slug)
    assert [lane["experiment_id"] for lane in body["lanes"]] == [launched["id"], fork["id"]]
    start = next(node for node in body["nodes"] if node["version_id"] == fork["version_id"])
    assert (start["lane"], start["experiment_id"], start["label"], start["change_level"]) == (1, fork["id"], "v1.1.0", "none")
    assert {"parent": minor["version_id"], "child": fork["version_id"], "kind": "fork"} in body["edges"]


def test_a_combination_is_a_new_lane_with_two_merge_edges(client):
    slug = _microproject(client)
    a = launch(client, slug, title="A", intent="Depart", steps=steps(20))
    b = launch(
        client, slug, title="B", intent="Variante", steps=steps(40),
        from_version={"experiment_id": a["id"], "version_id": a["version_id"]},
    )
    c = combine(client, slug, a["id"], b["id"], title="C")

    body = structure_history(client, slug)
    assert [lane["experiment_id"] for lane in body["lanes"]] == [a["id"], b["id"], c["id"]]
    node = next(node for node in body["nodes"] if node["version_id"] == c["version_id"])
    assert node["is_merge"] is True and node["lane"] == 2 and node["label"] == "v1.0.0"
    edges = {(e["parent"], e["child"], e["kind"]) for e in body["edges"]}
    assert edges == {
        (a["version_id"], b["version_id"], "fork"),
        (a["version_id"], c["version_id"], "merge"),
        (b["version_id"], c["version_id"], "merge"),
    }


def test_an_old_merge_on_its_line_keeps_a_parent_edge_and_a_merge_edge(client):
    # avant, combiner B dans A ajoutait à A une version à deux parents
    slug = _microproject(client)
    a = launch(client, slug, title="A", intent="Depart", steps=steps(20))
    b = launch(
        client, slug, title="B", intent="Variante", steps=steps(40),
        from_version={"experiment_id": a["id"], "version_id": a["version_id"]},
    )
    merged = write_old_merge(slug, a["id"], b["id"])

    body = structure_history(client, slug)
    node = next(node for node in body["nodes"] if node["version_id"] == merged)
    assert node["is_merge"] is True and node["lane"] == 0
    edges = {(e["parent"], e["child"], e["kind"]) for e in body["edges"]}
    assert edges == {
        (a["version_id"], b["version_id"], "fork"),
        (a["version_id"], merged, "parent"),
        (b["version_id"], merged, "merge"),
    }


def test_lanes_keep_their_order(client):
    slug = _microproject(client)
    a = launch(client, slug, title="A", intent="Depart", steps=steps(20))
    b = launch(client, slug, title="B", intent="Autre depart", steps=steps(30), entities=[{"sample_id": "W2"}])
    before = [lane["experiment_id"] for lane in structure_history(client, slug)["lanes"]]
    assert before == [a["id"], b["id"]]

    # une évolution de la plus ancienne piste ne la déplace pas ; une nouvelle piste vient en dernier
    evolve(client, slug, a["id"], title="A", steps=steps(25))
    c = launch(client, slug, title="C", intent="Encore", steps=steps(10), entities=[{"sample_id": "W3"}])
    for all_versions in (False, True):
        lanes = structure_history(client, slug, all_versions=all_versions)["lanes"]
        assert [lane["experiment_id"] for lane in lanes] == [a["id"], b["id"], c["id"]]
        assert [lane["index"] for lane in lanes] == [0, 1, 2]


def test_a_viewer_reads_the_history_a_stranger_does_not(client):
    slug = _microproject(client)
    launch(client, slug, title="A", intent="Depart", steps=steps(20))

    join_as(client, slug, "history-viewer@example.com", owner=OWNER, role="viewer")
    assert len(structure_history(client, slug)["nodes"]) == 1

    signup_with_microproject(client, "history-stranger@example.com", "Ailleurs")
    assert client.get(f"/api/microprojects/{slug}/structure-history").status_code == 403
