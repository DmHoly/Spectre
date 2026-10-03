"""La migration des fichiers d'avant les collections à plat : ``{"structures": {nom: …}}`` devient
``{"items": [...]}``, chaque élément avec un ``id`` et un auteur inconnu."""

from __future__ import annotations

import json

from spectre.plugins.process_library import migrations
from support.accounts import signup, switch_user
from support.microprojects import signup_with_microproject
from support.process_library import by_name, delete_item, list_items, step_preset, update_item


def _legacy_preset(name: str) -> dict:
    return {**step_preset(name), "notes": None, "created_at": "2025-01-01T00:00:00+00:00"}


def test_legacy_files_get_ids_and_an_unknown_author(client, data_dir):
    signup(client, "admin@example.com")  # le premier compte est administrateur
    slug = signup_with_microproject(client, "editor@example.com")
    shared = data_dir / "presets_etapes_partages.json"
    own = data_dir / "microprojects" / slug / "presets_etapes.json"
    shared.write_text(json.dumps({"presets": {"Ancien": _legacy_preset("Ancien")}}), encoding="utf-8")
    own.write_text(json.dumps({"presets": {"Interne": _legacy_preset("Interne")}}), encoding="utf-8")

    migrations.add_ids()
    migrations.add_ids()  # déjà migrés : rien ne change

    items = json.loads(shared.read_text(encoding="utf-8"))["items"]
    assert [(raw["name"], raw["created_by"], raw["updated_by"]) for raw in items] == [("Ancien", None, None)]
    assert items[0]["id"]

    listed = list_items(client, "step-presets", microproject=slug)
    old_shared, old_own = by_name(listed, "Ancien"), by_name(listed, "Interne")
    assert (old_shared["scope"], old_shared["created_by"], old_shared["can_edit"]) == ("shared", None, False)
    # un élément de µprojet sans auteur reste modifiable par les éditeurs du µprojet
    assert update_item(client, "step-presets", old_own["id"], notes="repris")["notes"] == "repris"
    assert client.delete(f"/api/step-presets/{old_shared['id']}").status_code == 403

    # sans auteur connu, seul un administrateur peut modifier ou supprimer un élément partagé
    switch_user(client, "admin@example.com")
    delete_item(client, "step-presets", old_shared["id"])
