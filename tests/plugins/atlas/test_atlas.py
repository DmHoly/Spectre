"""GET /api/atlas: the cross-microproject bird's-eye view (spectre.plugins.atlas).
Nodes are branch tips (not every version ever committed - see test_experience_list_shows_branch_tips.py
for why that matters) plus the physical entities tracked on them, and edges are condensed down to
tip-to-tip links so a fork or a merge still shows without drawing every intermediate commit.
"""

from __future__ import annotations

from support.areas import create_area
from support.experiments import conclude, evolve, launch, launch_campaign, merge, track_entities
from support.http import assert_handler_404
from support.microprojects import move_microproject, signup_with_microproject
from support.structures import steps


def _atlas_microproject(client, slug):
    atlas = client.get("/api/atlas?theme=non-classe").json()
    return next(p for p in atlas["microprojects"] if p["slug"] == slug)


def test_atlas_lists_only_the_current_user_own_microprojects(client):
    slug_a = signup_with_microproject(client, "atlas-a@example.com", "Projet A")
    launch(client, slug_a, title="Etude A", intent="Depart")

    slug_b = signup_with_microproject(client, "atlas-b@example.com", "Projet B")
    launch(client, slug_b, title="Etude B", intent="Depart")

    # atlas-b's session is the last one logged in on the shared client - only their own microproject shows.
    atlas = client.get("/api/atlas?theme=non-classe").json()
    slugs = [p["slug"] for p in atlas["microprojects"]]
    assert slug_b in slugs
    assert slug_a not in slugs


def test_atlas_shows_one_experience_node_per_branch_tip_with_entities_and_objectives(client):
    slug = signup_with_microproject(client, "atlas-tips@example.com")
    launched = launch(
        client,
        slug,
        title="Etude",
        intent="Depart",
        objectives=[{"name": "Rugosité", "metric": "rugosite", "direction": "minimize", "target": 1.0}],
        entities=[{"sample_id": "placeholder"}],
    )
    track_entities(client, slug, launched["id"], [{"sample_id": "W1-A1", "location": "congélateur B"}])
    concluded = conclude(
        client,
        slug,
        launched["id"],
        decision="promote",
        objective_results=[{"objective": "Rugosité", "status": "met", "reasoning": "0.5nm mesuré."}],
    )

    microproject = _atlas_microproject(client, slug)
    assert len(microproject["experiences"]) == 1  # one card per branch tip, not one per version
    exp = microproject["experiences"][0]
    assert exp["id"] == concluded["version_id"]
    assert exp["experiment_id"] == launched["id"]  # la piste, ce que vise « Ouvrir la fiche »
    assert exp["status"] == "concluded"
    assert exp["decision"] == "promote"  # for the "Concluante"/"Non concluante"/"À poursuivre" badge nuance
    assert exp["entities"] == [{"index": 0, "sample_id": "W1-A1", "location": "congélateur B"}]
    assert exp["objectives"] == [{"name": "Rugosité", "status": "met"}]


def test_atlas_skips_physical_tracking_entries_with_no_sample_id_or_location(client):
    slug = signup_with_microproject(client, "atlas-empty-entity@example.com")
    launched = launch(client, slug, title="Etude", intent="Depart", entities=[{"sample_id": "placeholder"}])
    track_entities(client, slug, launched["id"], [{}])

    assert _atlas_microproject(client, slug)["experiences"][0]["entities"] == []


def test_atlas_entity_index_survives_a_partially_tracked_campaign(client):
    """A campaign variant left untracked must not shift the *index* of the ones after it - that
    index is the addressing spectre.plugins.links (and the attachment upload form) both rely on, so
    a naive "filter then enumerate the result" would silently point a link/attachment at the
    wrong sample the moment a middle variant is skipped.
    """
    slug = signup_with_microproject(client, "atlas-partial-tracking@example.com")
    campaign = launch_campaign(client, slug, objectives=[], entities=[{"sample_id": "placeholder"}])
    # 3 variants, only the first and last tracked - the middle one stays blank.
    track_entities(client, slug, campaign["id"], [{"sample_id": "V0"}, {}, {"sample_id": "V2"}])

    entities = _atlas_microproject(client, slug)["experiences"][0]["entities"]
    assert {(e["index"], e["sample_id"]) for e in entities} == {(0, "V0"), (2, "V2")}


def test_atlas_condenses_a_fork_and_merge_into_tip_to_tip_edges(client):
    slug = signup_with_microproject(client, "atlas-merge@example.com")
    root = launch(client, slug, title="Reference", intent="Depart", steps=steps(10))
    # piste A continues the root's own line, piste B forks onto its own - so the merge (which
    # always advances the line it is made on) supersedes A but leaves B as its own still-current tip.
    evolve(client, slug, root["id"], title="Piste A", intent="Suite A", steps=steps(15))
    branch_b = launch(
        client, slug, title="Piste B", intent="Suite B", steps=steps(30), branch="piste-b",
        from_version={"experiment_id": root["id"], "version_id": root["version_id"]},
    )
    merged = merge(client, slug, root["id"], branch_b["id"])

    microproject = _atlas_microproject(client, slug)
    # root and piste A were both superseded on the same line by the merge commit ; piste B's own
    # line was never advanced, so it's still a separate, live node.
    node_ids = {exp["id"] for exp in microproject["experiences"]}
    assert node_ids == {merged["version_id"], branch_b["version_id"]}
    assert {exp["experiment_id"] for exp in microproject["experiences"]} == {root["id"], "piste-b"}

    edges = {(e["from"], e["to"]) for e in microproject["edges"]}
    assert edges == {(branch_b["version_id"], merged["version_id"])}  # not one edge per commit in the collapsed history


def test_atlas_requires_a_theme(client):
    signup_with_microproject(client, "atlas-notheme@example.com")
    assert client.get("/api/atlas").status_code == 422


def test_atlas_404s_on_an_unknown_theme(client):
    signup_with_microproject(client, "atlas-badtheme@example.com")
    assert_handler_404(client.get("/api/atlas?theme=ne-existe-pas"))


def test_atlas_only_shows_microprojects_in_the_given_theme(client):
    slug = signup_with_microproject(client, "atlas-theme-scope@example.com", "Projet thématique")
    launch(client, slug, title="Etude", intent="Depart")
    created = create_area(client, "Fiabilité")
    move_microproject(client, created["slug"], slug)

    # still a member, but moved out of "non-classe" - no longer shows there.
    unclassified = client.get("/api/atlas?theme=non-classe").json()
    assert slug not in {p["slug"] for p in unclassified["microprojects"]}

    own_theme = client.get(f"/api/atlas?theme={created['slug']}").json()
    assert own_theme["theme"] == {"slug": created["slug"], "name": "Fiabilité"}
    assert slug in {p["slug"] for p in own_theme["microprojects"]}
