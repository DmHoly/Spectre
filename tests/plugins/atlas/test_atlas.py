"""GET /api/areas/{area_slug}/atlas : la vue graphe d'un projet corporate (plugin atlas). Un nœud par
piste d'étude, montrée à sa pointe (pas une par version), les entités physiques qu'elle suit, et des
arêtes condensées de pointe à pointe - une fourche ou une fusion se voit sans dessiner chaque version.
Les liens viennent du plugin links et désignent la piste, comme les nœuds.
"""

from __future__ import annotations

from support.areas import create_area
from support.atlas import atlas, atlas_microproject
from support.experiments import combine, conclude, evolve, launch, launch_campaign, tag, track_entities
from support.http import ROUTER_NOT_FOUND, assert_handler_404
from support.links import entity, link_entities, link_microprojects
from support.microprojects import create_microproject, move_microproject, signup_with_microproject
from support.structures import steps


def test_the_atlas_lists_only_the_viewer_own_microprojects(client):
    slug_a = signup_with_microproject(client, "atlas-a@example.com", "Projet A")
    launch(client, slug_a, title="Etude A", intent="Depart")

    slug_b = signup_with_microproject(client, "atlas-b@example.com", "Projet B")
    launch(client, slug_b, title="Etude B", intent="Depart")

    # atlas-b est le dernier connecté sur le client partagé : seul son µprojet apparaît
    body = atlas(client)
    assert body["area"] == {"slug": "non-classe", "name": "Non classé"}
    assert [p["slug"] for p in body["microprojects"]] == [slug_b]


def test_one_node_per_piste_with_its_entities_and_objectives(client):
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

    [experiment] = atlas_microproject(client, slug)["experiments"]  # une piste, pas une bulle par version
    assert experiment["experiment_id"] == launched["id"]
    assert experiment["version_id"] == concluded["version_id"]
    assert experiment["status"] == "concluded"
    assert experiment["decision"] == "promote"  # la nuance « Concluante » / « À poursuivre » du badge
    assert experiment["entities"] == [{"index": 0, "sample_id": "W1-A1", "location": "congélateur B"}]
    assert experiment["objectives"] == [{"name": "Rugosité", "status": "met"}]
    assert "attachments" not in experiment  # champ mort, retiré


def test_entries_with_no_sample_id_or_location_get_no_node(client):
    slug = signup_with_microproject(client, "atlas-empty-entity@example.com")
    launched = launch(client, slug, title="Etude", intent="Depart", entities=[{"sample_id": "placeholder"}])
    track_entities(client, slug, launched["id"], [{}])

    assert atlas_microproject(client, slug)["experiments"][0]["entities"] == []


def test_the_entity_index_survives_a_partially_tracked_campaign(client):
    """Une variante laissée sans suivi ne décale pas l'index des suivantes : c'est l'adressage des
    liens d'entités, qu'un « filtrer puis numéroter » ferait pointer sur le mauvais échantillon."""
    slug = signup_with_microproject(client, "atlas-partial-tracking@example.com")
    campaign = launch_campaign(client, slug, objectives=[], entities=[{"sample_id": "placeholder"}])
    track_entities(client, slug, campaign["id"], [{"sample_id": "V0"}, {}, {"sample_id": "V2"}])

    entities = atlas_microproject(client, slug)["experiments"][0]["entities"]
    assert {(e["index"], e["sample_id"]) for e in entities} == {(0, "V0"), (2, "V2")}


def test_a_fork_and_a_combination_condense_into_edges_between_pistes(client):
    slug = signup_with_microproject(client, "atlas-merge@example.com")
    root = launch(client, slug, title="Reference", intent="Depart", steps=steps(10))
    # la piste racine continue (Piste A), piste-b en part ; la combinaison crée piste-c, issue des
    # deux, qui restent vivantes à leur pointe
    evolved = evolve(client, slug, root["id"], title="Piste A", intent="Suite A", steps=steps(15))
    branch_b = launch(
        client, slug, title="Piste B", intent="Suite B", steps=steps(30), branch="piste-b",
        from_version={"experiment_id": root["id"], "version_id": root["version_id"]},
    )
    combined = combine(client, slug, root["id"], branch_b["id"], branch="piste-c")

    microproject = atlas_microproject(client, slug)
    nodes = {(e["experiment_id"], e["version_id"]) for e in microproject["experiments"]}
    assert nodes == {(root["id"], evolved["version_id"]), ("piste-b", branch_b["version_id"]), ("piste-c", combined["version_id"])}
    # pas une arête par version : les deux parents de la combinaison, de pointe à pointe
    assert sorted(microproject["edges"], key=lambda e: (e["from"], e["to"])) == [
        {"from": "piste-b", "to": "piste-c"},
        {"from": root["id"], "to": "piste-c"},
    ]


def test_the_atlas_of_an_unknown_area_is_404(client):
    signup_with_microproject(client, "atlas-badtheme@example.com")
    assert_handler_404(client.get("/api/areas/ne-existe-pas/atlas"))


def test_the_old_atlas_route_is_gone(client):
    signup_with_microproject(client, "atlas-old@example.com")
    response = client.get("/api/atlas?theme=non-classe")
    assert response.status_code == 404 and response.json()["detail"] == ROUTER_NOT_FOUND


def test_the_atlas_only_shows_the_microprojects_of_its_area(client):
    slug = signup_with_microproject(client, "atlas-theme-scope@example.com", "Projet thématique")
    launch(client, slug, title="Etude", intent="Depart")
    created = create_area(client, "Fiabilité")
    move_microproject(client, created["slug"], slug)

    # toujours membre, mais sorti de « non-classe »
    assert slug not in {p["slug"] for p in atlas(client)["microprojects"]}

    own_area = atlas(client, created["slug"])
    assert own_area["area"] == {"slug": created["slug"], "name": "Fiabilité"}
    assert slug in {p["slug"] for p in own_area["microprojects"]}


def test_the_atlas_carries_the_links_of_its_area(client):
    slug_a = signup_with_microproject(client, "atlas-links@example.com", "Projet A")
    slug_b = create_microproject(client, "Projet B")["slug"]
    link = link_microprojects(client, slug_a, slug_b, "Même famille")

    body = atlas(client)
    assert body["microproject_links"] == [link]
    assert body["entity_links"] == []


def test_an_entity_link_still_resolves_after_writes_on_both_studies(client):
    """Bug B7 : un lien d'entités désignait une version, et disparaissait de l'atlas à la première
    écriture sur l'une des deux études."""
    slug_a = signup_with_microproject(client, "atlas-b7@example.com", "Projet A")
    exp_a = launch(client, slug_a, title="Etude A", intent="Depart", entities=[{"sample_id": "W-A1"}])
    slug_b = create_microproject(client, "Projet B")["slug"]
    exp_b = launch(client, slug_b, title="Etude B", intent="Depart", entities=[{"sample_id": "W-B1"}])
    link = link_entities(client, entity(slug_a, exp_a["id"]), entity(slug_b, exp_b["id"]))

    conclude(client, slug_a, exp_a["id"], decision="promote")
    tag(client, slug_b, exp_b["id"], ["suivi"])

    body = atlas(client)
    assert body["entity_links"] == [link]
    nodes = {
        (p["slug"], e["experiment_id"], entity_["index"])
        for p in body["microprojects"]
        for e in p["experiments"]
        for entity_ in e["entities"]
    }
    for side in (link["a"], link["b"]):
        assert (side["microproject"], side["experiment_id"], side["entity_index"]) in nodes
