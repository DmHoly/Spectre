from __future__ import annotations

from support.experiments import get_experience, launch
from support.microprojects import signup_with_microproject
from support.structures import steps


def test_reusing_a_structure_as_template_starts_a_fresh_lineage(client):
    slug = signup_with_microproject(client, "tmpl@example.com")

    source = launch(client, slug, title="Reference", intent="Depart", steps=steps(20))

    # the structure builder fetches this to pre-fill, then POSTs a brand-new /experiences (not /evoluer)
    process = client.get(f"/api/microprojets/{slug}/experiences/{source['id']}/process").json()
    fresh = launch(
        client,
        slug,
        substrate=process["substrate"],
        steps=process["steps"],
        title="Nouvelle piste independante",
        intent="Reprend la meme structure sans heriter de la lignee",
        entities=[{"sample_id": "W2"}],
    )

    detail = get_experience(client, slug, fresh["id"])
    assert detail["parents"] == []
    assert detail["branch"] != source["branch"]
    # same structure content though (same process re-used)
    assert "<svg" in detail["structure_svg"]
