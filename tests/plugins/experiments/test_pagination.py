from __future__ import annotations

from support.experiments import experiments_url, launch, list_experiments
from support.microprojects import signup_with_microproject


def test_experiments_are_paginated(client):
    slug = signup_with_microproject(client, "page@example.com", "Projet pagine", name="P")

    for i in range(5):
        launch(client, slug, title=f"Essai {i}", intent="x", entities=[{"sample_id": f"W{i}"}])

    page1 = list_experiments(client, slug, status="all", offset=0, limit=2)
    assert len(page1["items"]) == 2
    assert page1["total"] == 5
    assert set(page1) == {"items", "total"}

    page2 = list_experiments(client, slug, status="all", offset=2, limit=2)
    assert len(page2["items"]) == 2
    assert {i["id"] for i in page1["items"]}.isdisjoint({i["id"] for i in page2["items"]})

    page3 = list_experiments(client, slug, status="all", offset=4, limit=2)
    assert len(page3["items"]) == 1


def test_pagination_rejects_bad_params(client):
    slug = signup_with_microproject(client, "page2@example.com", name="P2")

    assert client.get(experiments_url(slug), params={"offset": -1}).status_code == 422
    assert client.get(experiments_url(slug), params={"limit": 0}).status_code == 422
    assert client.get(experiments_url(slug), params={"limit": 500}).status_code == 422
