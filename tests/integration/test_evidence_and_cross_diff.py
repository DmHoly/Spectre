from __future__ import annotations

from support.accounts import login, signup
from support.experiments import add_evidence, conclude, evolve, experiment_url, get_experiment, get_version, launch, structure_diff, tag
from support.microprojects import create_microproject, join_as, signup_with_microproject
from support.structures import steps


def test_add_evidence_creates_a_new_version_and_carries_forward(client):
    slug = signup_with_microproject(client, "owner@example.com", name="Owner")
    launched = launch(client, slug)

    body = {
        "description": "Mesure d'epaisseur au profilometre",
        "source": "https://labo.example/mesures/142",
        "metric_name": "thickness_nm",
        "metric_value": 20.3,
        "metric_unit": "nm",
    }
    response = client.post(f"/api/microprojets/{slug}/experiences/{launched['id']}/preuves", json=body)
    assert response.status_code == 201
    added = response.json()
    assert added["id"] == launched["id"]  # la même piste
    assert added["version_id"] != launched["version_id"]  # une nouvelle version

    detail = get_experiment(client, slug, launched["id"])
    assert detail["version_id"] == added["version_id"]
    assert len(detail["evidence"]) == 1
    assert detail["evidence"][0]["description"] == "Mesure d'epaisseur au profilometre"
    assert detail["evidence"][0]["metrics"]["thickness_nm"]["value"] == 20.3

    # a second piece of evidence carries the first one forward
    second = add_evidence(client, slug, launched["id"], "Deuxieme mesure", source="https://labo.example/mesures/143")
    assert len(get_experiment(client, slug, launched["id"])["evidence"]) == 2
    assert len(get_version(client, slug, launched["id"], added["version_id"])["evidence"]) == 1  # la version d'avant reste
    assert second["version_id"] != added["version_id"]


def test_concluding_an_experience_keeps_its_evidence(client):
    slug = signup_with_microproject(client, "owner-concl@example.com", name="Owner")
    launched = launch(client, slug)

    add_evidence(client, slug, launched["id"], "Mesure d'epaisseur au profilometre", source="https://labo.example/mesures/142")
    detail = conclude(client, slug, launched["id"])
    assert len(detail["evidence"]) == 1
    assert detail["evidence"][0]["description"] == "Mesure d'epaisseur au profilometre"


def test_viewer_cannot_add_evidence(client):
    slug = signup_with_microproject(client, "owner2@example.com", name="O")
    launched = launch(client, slug)

    join_as(client, slug, "viewer5@example.com", owner="owner2@example.com", role="viewer")
    response = client.post(
        f"/api/microprojets/{slug}/experiences/{launched['id']}/preuves",
        json={"description": "x", "source": "y"},
    )
    assert response.status_code == 403


def test_evidence_step_index_round_trips_and_is_labeled_in_the_process(client):
    slug = signup_with_microproject(client, "owner-step@example.com", name="Owner")
    launched = launch(client, slug)

    response = client.post(
        f"/api/microprojets/{slug}/experiences/{launched['id']}/preuves",
        json={
            "description": "Mesure de perf apres depot",
            "source": "https://labo.example/mesures/1",
            "metric_name": "perf",
            "metric_value": 12.5,
            "step_index": 0,
        },
    )
    assert response.status_code == 201
    assert get_experiment(client, slug, launched["id"])["evidence"][0]["step_index"] == 0

    # omitting step_index still defaults to None (not tied to any step)
    add_evidence(client, slug, launched["id"], "Preuve generale", source="https://labo.example/mesures/2")
    assert get_experiment(client, slug, launched["id"])["evidence"][-1]["step_index"] is None


def test_evidence_step_index_must_be_within_process_bounds(client):
    slug = signup_with_microproject(client, "owner-bounds@example.com", name="Owner")
    launched = launch(client, slug)  # a single-step process (support.structures.steps)

    response = client.post(
        f"/api/microprojets/{slug}/experiences/{launched['id']}/preuves",
        json={"description": "Hors bornes", "source": "y", "step_index": 5},
    )
    assert response.status_code == 422

    negative = client.post(
        f"/api/microprojets/{slug}/experiences/{launched['id']}/preuves",
        json={"description": "Negatif", "source": "y", "step_index": -1},
    )
    assert negative.status_code == 422


def test_evolving_an_experience_preserves_its_evidence_and_tags(client):
    slug = signup_with_microproject(client, "owner-evolve@example.com", name="Owner")
    launched = launch(client, slug)

    add_evidence(client, slug, launched["id"], "Mesure avant evolution", source="https://labo.example/mesures/1")
    tag(client, slug, launched["id"], ["important"])
    detail = evolve(client, slug, launched["id"], intent="Reduire l'epaisseur", steps=steps(thickness_nm=10))

    assert len(detail["evidence"]) == 1
    assert detail["evidence"][0]["description"] == "Mesure avant evolution"
    assert detail["tags"] == ["important"]


def test_cross_microproject_diff(client):
    signup(client, "cross@example.com", name="Cross")
    slug_a = create_microproject(client, "Projet A")["slug"]
    slug_b = create_microproject(client, "Projet B")["slug"]

    exp_a = launch(client, slug_a, title="Essai A")
    exp_b = launch(client, slug_b, title="Essai B", steps=steps(thickness_nm=40), entities=[{"sample_id": "W2"}])

    body = structure_diff(client, slug_a, exp_a["id"], against_microproject=slug_b, against_experiment=exp_b["id"])
    assert body["target"] == {"experiment_id": exp_b["id"], "version_id": exp_b["version_id"], "title": "Essai B", "microproject": "Projet B"}
    assert len(body["entries"]) >= 1
    # sans l'expérience à comparer, l'autre µprojet ne suffit pas
    missing = client.get(f"{experiment_url(slug_a, exp_a['id'])}/structure-diff", params={"against_microproject": slug_b})
    assert missing.status_code == 422


def test_cross_microproject_diff_requires_access_to_other_microproject(client):
    slug_c = signup_with_microproject(client, "ownerC@example.com", "Projet C", name="C")
    exp_c = launch(client, slug_c, title="Essai C")

    slug_d = signup_with_microproject(client, "ownerD@example.com", "Projet D privé", name="D")
    exp_d = launch(client, slug_d, title="Essai D")

    login(client, "ownerC@example.com")
    response = client.get(
        f"{experiment_url(slug_c, exp_c['id'])}/structure-diff", params={"against_microproject": slug_d, "against_experiment": exp_d["id"]}
    )
    assert response.status_code == 403


def test_evidence_kind_objective_and_interpretation_round_trip(client):
    slug = signup_with_microproject(client, "owner-kind@example.com", name="Owner")
    launched = launch(
        client, slug, objectives=[{"name": "Isolation", "metric": "resistivity_ohm_cm", "direction": "target", "target": 1e6}]
    )

    response = client.post(
        f"/api/microprojets/{slug}/experiences/{launched['id']}/preuves",
        json={
            "description": "Split vs PL",
            "source": "—",
            "kind": "graph",
            "objective": "Isolation",
            "interpretation": "L'isolation augmente avec l'epaisseur, coherent avec le changement",
            "graph_config": {"title": "Split vs PL", "x_label": "Epaisseur (nm)", "y_label": "Intensite PL", "query": "TODO", "data_source_url": None},
        },
    )
    assert response.status_code == 201
    evidence = get_experiment(client, slug, launched["id"])["evidence"][0]
    assert evidence["kind"] == "graph"
    assert evidence["objective"] == "Isolation"
    assert evidence["interpretation"].startswith("L'isolation")
    assert evidence["graph_config"]["query"] == "TODO"


def test_evidence_own_fields_survive_lightweight_and_real_evolutions(client):
    # Spectre's own preuve fields ride in the experience's metadata (not on follow.Evidence, whose
    # fields depend on the installed Follow) - every later version must still show them.
    slug = signup_with_microproject(client, "owner-kind-carry@example.com")
    launched = launch(client, slug, objectives=[{"name": "Isolation", "metric": "r", "direction": "observe"}])
    graph = add_evidence(client, slug, launched["id"], "Split vs PL", kind="graph", objective="Isolation", interpretation="Monte")
    tagged = tag(client, slug, launched["id"], ["a-suivre"])
    other = add_evidence(client, slug, launched["id"], "Autre mesure")
    concluded = conclude(client, slug, launched["id"])
    evolved = evolve(client, slug, launched["id"], steps=steps(40))

    for version in (tagged, other, concluded, evolved):
        evidence = {e["id"]: e for e in get_version(client, slug, launched["id"], version["version_id"])["evidence"]}
        own = evidence[graph["evidence_id"]]
        assert (own["kind"], own["objective"], own["interpretation"]) == ("graph", "Isolation", "Monte")
    assert evidence[other["evidence_id"]]["kind"] == "standard"  # each preuve keeps its own fields


def test_evidence_objective_must_exist_on_the_experience(client):
    slug = signup_with_microproject(client, "owner-badobj@example.com", name="Owner")
    launched = launch(client, slug)

    response = client.post(
        f"/api/microprojets/{slug}/experiences/{launched['id']}/preuves",
        json={"description": "x", "source": "y", "objective": "Objectif inexistant"},
    )
    assert response.status_code == 422


def test_evidence_kind_defaults_to_standard(client):
    slug = signup_with_microproject(client, "owner-default@example.com", name="Owner")
    launched = launch(client, slug)

    response = client.post(
        f"/api/microprojets/{slug}/experiences/{launched['id']}/preuves",
        json={"description": "x", "source": "y"},
    )
    assert response.status_code == 201
    evidence = get_experiment(client, slug, launched["id"])["evidence"][0]
    assert evidence["kind"] == "standard"
    assert evidence["objective"] is None
    assert evidence["image_annotations"] == []
