"""GET /api/atlas: the cross-project bird's-eye view (spectre.api.atlas / spectre.core.atlas).
Nodes are branch tips (not every version ever committed - see test_experience_list_shows_branch_tips.py
for why that matters) plus the physical entities tracked on them, and edges are condensed down to
tip-to-tip links so a fork or a merge still shows without drawing every intermediate commit.
"""

from __future__ import annotations


def _substrate():
    return {"material": "Si", "domain_width": {"value": 200, "unit": "nm"}, "thickness": {"value": 50, "unit": "nm"}}


def _steps(thickness=20):
    return [
        {"kind": "deposition", "name": "Oxyde", "material": "SiO2", "recipe": "CVD Conformal", "thickness": {"value": thickness, "unit": "nm"}}
    ]


def _register_and_project(client, email, project_name="Projet"):
    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={"email": email, "password": "supersecret", "name": "T"})
    return client.post("/api/projects", json={"name": project_name}).json()["slug"]


def test_atlas_lists_only_the_current_user_own_projects(client):
    slug_a = _register_and_project(client, "atlas-a@example.com", "Projet A")
    client.post(
        f"/api/projects/{slug_a}/experiences",
        json={"substrate": _substrate(), "steps": _steps(), "title": "Etude A", "intent": "Depart"},
    )

    slug_b = _register_and_project(client, "atlas-b@example.com", "Projet B")
    client.post(
        f"/api/projects/{slug_b}/experiences",
        json={"substrate": _substrate(), "steps": _steps(), "title": "Etude B", "intent": "Depart"},
    )

    # atlas-b's session is the last one logged in on the shared client - only their own project shows.
    atlas = client.get("/api/atlas").json()
    slugs = [p["slug"] for p in atlas["projects"]]
    assert slug_b in slugs
    assert slug_a not in slugs


def test_atlas_shows_one_experience_node_per_branch_tip_with_entities_and_objectives(client):
    slug = _register_and_project(client, "atlas-tips@example.com")
    launched = client.post(
        f"/api/projects/{slug}/experiences",
        json={
            "substrate": _substrate(),
            "steps": _steps(),
            "title": "Etude",
            "intent": "Depart",
            "objectives": [{"name": "Rugosité", "metric": "rugosite", "direction": "minimize", "target": 1.0}],
            "entities": [{"sample_id": "placeholder"}],
        },
    ).json()
    with_entity = client.post(
        f"/api/projects/{slug}/experiences/{launched['id']}/entites",
        json={"entities": [{"sample_id": "W1-A1", "location": "congélateur B"}]},
    ).json()
    concluded = client.post(
        f"/api/projects/{slug}/experiences/{with_entity['id']}/conclure",
        json={
            "status": "concluded",
            "objective_results": [{"objective": "Rugosité", "status": "met", "reasoning": "0.5nm mesuré."}],
        },
    ).json()

    atlas = client.get("/api/atlas").json()
    project = next(p for p in atlas["projects"] if p["slug"] == slug)
    assert len(project["experiences"]) == 1  # one card per branch tip, not one per version
    exp = project["experiences"][0]
    assert exp["id"] == concluded["id"]
    assert exp["status"] == "concluded"
    assert exp["entities"] == [{"index": 0, "sample_id": "W1-A1", "location": "congélateur B"}]
    assert exp["objectives"] == [{"name": "Rugosité", "status": "met"}]


def test_atlas_skips_physical_tracking_entries_with_no_sample_id_or_location(client):
    slug = _register_and_project(client, "atlas-empty-entity@example.com")
    launched = client.post(
        f"/api/projects/{slug}/experiences",
        json={
            "substrate": _substrate(),
            "steps": _steps(),
            "title": "Etude",
            "intent": "Depart",
            "entities": [{"sample_id": "placeholder"}],
        },
    ).json()
    client.post(f"/api/projects/{slug}/experiences/{launched['id']}/entites", json={"entities": [{}]})

    atlas = client.get("/api/atlas").json()
    project = next(p for p in atlas["projects"] if p["slug"] == slug)
    assert project["experiences"][0]["entities"] == []


def test_atlas_entity_index_survives_a_partially_tracked_campaign(client):
    """A campaign variant left untracked must not shift the *index* of the ones after it - that
    index is the addressing spectre.core.links (and the attachment upload form) both rely on, so
    a naive "filter then enumerate the result" would silently point a link/attachment at the
    wrong sample the moment a middle variant is skipped.
    """
    slug = _register_and_project(client, "atlas-partial-tracking@example.com")
    campaign = client.post(
        f"/api/projects/{slug}/experiences/campagne",
        json={
            "substrate": _substrate(),
            "steps": _steps(),
            "plan": {"factors": [{"step_index": 0, "field": "thickness", "values": [10, 20, 30]}]},
            "title": "Campagne",
            "intent": "Balayer l'épaisseur",
            "objectives": [],
            "entities": [{"sample_id": "placeholder"}],
        },
    ).json()
    # 3 variants, only the first and last tracked - the middle one stays blank.
    client.post(
        f"/api/projects/{slug}/experiences/{campaign['id']}/entites",
        json={"entities": [{"sample_id": "V0"}, {}, {"sample_id": "V2"}]},
    )

    atlas = client.get("/api/atlas").json()
    project = next(p for p in atlas["projects"] if p["slug"] == slug)
    entities = project["experiences"][0]["entities"]
    assert {(e["index"], e["sample_id"]) for e in entities} == {(0, "V0"), (2, "V2")}


def test_atlas_condenses_a_fork_and_merge_into_tip_to_tip_edges(client):
    slug = _register_and_project(client, "atlas-merge@example.com")
    root = client.post(
        f"/api/projects/{slug}/experiences",
        json={
            "substrate": _substrate(),
            "steps": _steps(10),
            "title": "Reference",
            "intent": "Depart",
            "entities": [{"sample_id": "W1"}],
        },
    ).json()
    # branch_a stays on the default branch, branch_b forks onto its own - so combiner (which
    # always advances `ref`'s own branch, see experiments.py::combine_experiences) supersedes
    # branch_a but leaves branch_b's branch as its own still-current tip.
    branch_a = client.post(
        f"/api/projects/{slug}/experiences/{root['id']}/evoluer",
        json={"substrate": _substrate(), "steps": _steps(15), "title": "Piste A", "intent": "Suite A"},
    ).json()
    branch_b = client.post(
        f"/api/projects/{slug}/experiences/{root['id']}/evoluer",
        json={
            "substrate": _substrate(),
            "steps": _steps(30),
            "title": "Piste B",
            "intent": "Suite B",
            "new_branch": "piste-b",
        },
    ).json()
    merged = client.post(
        f"/api/projects/{slug}/experiences/{branch_a['id']}/combiner",
        json={"other_id": branch_b["id"], "title": "Fusion", "intent": "Reunir A et B"},
    ).json()

    atlas = client.get("/api/atlas").json()
    project = next(p for p in atlas["projects"] if p["slug"] == slug)
    # root and branch_a were both superseded on the same (default) branch by the merge commit ;
    # branch_b's own branch was never advanced, so it's still a separate, live node.
    node_ids = {exp["id"] for exp in project["experiences"]}
    assert node_ids == {merged["id"], branch_b["id"]}

    edges = {(e["from"], e["to"]) for e in project["edges"]}
    assert edges == {(branch_b["id"], merged["id"])}  # not one edge per commit in the collapsed history
