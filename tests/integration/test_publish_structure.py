"""« Publier dans la bibliothèque » (page « Évolution des structures ») : le front lit le procédé
d'une version (``GET .../experiments/{exp}/process?version=``) et l'enregistre en structure
partagée (``POST /api/saved-structures``) avec son origine - la version, sa piste, sa ref. Aucune
dépendance entre les deux plugins côté serveur : c'est le parcours que fait la page."""

from __future__ import annotations

from support.experiments import create_ref, evolve, launch, process
from support.microprojects import create_microproject, signup_with_microproject
from support.process_library import create_item, get_item, list_items, names
from support.structures import steps


def test_a_ref_published_to_the_library_keeps_its_origin(client):
    slug = signup_with_microproject(client, "publish@example.com")
    launched = launch(client, slug, title="Empilement", intent="Depart", steps=steps(20))
    evolve(client, slug, launched["id"], title="Empilement", steps=steps(35))
    ref = create_ref(client, slug, launched["id"], "omega", version_id=launched["version_id"])

    origin = {"microproject": slug, "experiment_id": launched["id"], "version_id": ref["version_id"], "ref": "omega"}
    body = {"name": "Empilement omega", **process(client, slug, launched["id"], version=launched["version_id"]), "derived_from": origin}
    saved = create_item(client, "saved-structures", body, scope="shared")
    assert saved["scope"] == "shared"
    assert saved["derived_from"] == origin
    assert saved["steps"][0]["thickness"]["value"] == 20  # la version publiée, pas la pointe (35 nm)
    assert get_item(client, "saved-structures", saved["id"])["derived_from"] == origin

    # partagée : visible depuis un autre µprojet
    other = create_microproject(client, "Ailleurs")["slug"]
    assert "Empilement omega" in names(list_items(client, "saved-structures", microproject=other), "shared")


def test_an_incomplete_origin_is_refused(client):
    slug = signup_with_microproject(client, "publish-bad@example.com")
    launched = launch(client, slug, title="Empilement", intent="Depart", steps=steps(20))
    body = {"name": "X", **process(client, slug, launched["id"]), "derived_from": {"microproject": slug}, "scope": "shared"}
    assert client.post("/api/saved-structures", json=body).status_code == 422
