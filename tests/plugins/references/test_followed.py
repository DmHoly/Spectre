"""La référence suivie, côté references : la promotion propose la référence que l'étude suit avant
celle dont elle est partie, et la nouvelle version dérive de la version suivie."""

from __future__ import annotations

from support.experiments import experiment_url, launch
from support.http import assert_ok
from support.microprojects import signup_with_microproject
from support.references import create_reference, origin, preview_promotion, publish
from support.structures import steps


def test_publishing_proposes_the_followed_reference_and_derives_from_its_version(client):
    slug = signup_with_microproject(client, "followed-refs@example.com", "Epi")
    base = launch(client, slug, title="Base", intent="x", steps=steps(20))
    create_reference(client, "Base")
    publish(client, "base", slug, base["id"])
    other = launch(client, slug, title="Autre", intent="x", steps=steps(40))
    create_reference(client, "Autre")
    publish(client, "autre", slug, other["id"])
    publish(client, "autre", slug, launch(client, slug, title="Autre bis", intent="x", steps=steps(42))["id"])  # 1.1

    study = launch(client, slug, title="Depuis la base", intent="x", steps=steps(30), reference_origin=origin("base", "1.0"))
    before = preview_promotion(client, slug, study["id"])
    assert before["suggestion"]["reference"] == "base" and before["source"]["reference_followed"]["is_origin"]

    assert_ok(client.put(f"{experiment_url(slug, study['id'])}/reference", json={"reference": "autre", "version": "1.0", "scope": "study"}))
    after = preview_promotion(client, slug, study["id"])
    assert after["suggestion"] == {"reference": "autre", "parent": "1.0", "why": "l'étude la suit", "name": "Autre"}
    assert after["source"]["reference_followed"] == {"reference": "autre", "version": "1.0", "name": "Autre", "is_origin": False}
    # dérive de la version suivie (1.0), pas de la dernière (1.1) : un changement mineur donne 1.2
    assert after["target"]["reference"]["slug"] == "autre" and after["base"] == "1.0"
