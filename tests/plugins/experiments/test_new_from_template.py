from __future__ import annotations

from support.experiments import launch, process
from support.microprojects import signup_with_microproject
from support.structures import steps


def test_reusing_a_structure_as_template_starts_a_fresh_lineage(client):
    slug = signup_with_microproject(client, "tmpl@example.com")

    source = launch(client, slug, title="Reference", intent="Depart", steps=steps(20))

    # the structure builder fetches this to pre-fill, then POSTs a brand-new experiment (no from_version)
    template = process(client, slug, source["id"])
    fresh = launch(
        client,
        slug,
        substrate=template["substrate"],
        steps=template["steps"],
        title="Nouvelle piste independante",
        intent="Reprend la meme structure sans heriter de la lignee",
        entities=[{"sample_id": "W2"}],
    )

    assert fresh["parents"] == []
    assert fresh["id"] != source["id"]
    # same structure content though (same process re-used)
    assert "<svg" in fresh["structure_svg"]
