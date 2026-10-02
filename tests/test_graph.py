from __future__ import annotations

from support.accounts import signup
from support.experiments import evolve, launch, tag
from support.microprojects import signup_with_microproject
from support.structures import steps


def _owner_microproject(client):
    return signup_with_microproject(client, "owner@example.com", "Salle blanche", name="Owner")


def test_graph_html_on_empty_microproject(client):
    slug = _owner_microproject(client)
    response = client.get(f"/api/microprojets/{slug}/graphe.html")
    assert response.status_code == 200
    assert "Aucune expérience" in response.text


def test_graph_html_with_experiments(client):
    slug = _owner_microproject(client)
    launch(client, slug)
    response = client.get(f"/api/microprojets/{slug}/graphe.html")
    assert response.status_code == 200
    assert "plotly" in response.text.lower()


def test_graph_html_still_renders_with_a_tag_only_commit_collapsed_out(client):
    # the collapsing rules themselves (which commits are kept/removed) are unit-tested in
    # tests/test_versioning.py - this just proves the endpoint is wired up to them without crashing.
    slug = _owner_microproject(client)
    launched = launch(client, slug)
    tagged = tag(client, slug, launched["id"], ["a-suivre"])
    evolve(client, slug, tagged["id"], intent="Doubler l'epaisseur", steps=steps(40), objectives=[])
    response = client.get(f"/api/microprojets/{slug}/graphe.html")
    assert response.status_code == 200
    assert "plotly" in response.text.lower()


def test_graph_page_is_served(client):
    slug = _owner_microproject(client)
    assert client.get(f"/microprojets/{slug}/graphe").status_code == 200


def test_non_member_cannot_see_graph(client):
    slug = _owner_microproject(client)
    signup(client, "stranger@example.com", name="S")
    response = client.get(f"/api/microprojets/{slug}/graphe.html")
    assert response.status_code == 403
