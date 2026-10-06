"""La migration des fichiers d'avant les collections à plat : ``{"structures": {nom: …}}`` devient
``{"items": [...]}``, chaque élément avec un ``id`` et un auteur inconnu."""

from __future__ import annotations

import hashlib
import json

from spectre.plugins.process_library import migrations
from support.accounts import signup, switch_user
from support.microprojects import signup_with_microproject
from support.process_library import by_name, delete_item, legacy_step_preset, list_items, update_item


def _legacy_preset(name: str) -> dict:
    return {**legacy_step_preset(name), "notes": None, "created_at": "2025-01-01T00:00:00+00:00"}


def test_legacy_files_get_ids_and_an_unknown_author(client, data_dir):
    signup(client, "admin@example.com")  # le premier compte est administrateur
    slug = signup_with_microproject(client, "editor@example.com")
    shared = data_dir / "presets_etapes_partages.json"
    own = data_dir / "microprojects" / slug / "presets_etapes.json"
    shared.write_text(json.dumps({"presets": {"Ancien": _legacy_preset("Ancien")}}), encoding="utf-8")
    own.write_text(json.dumps({"presets": {"Interne": _legacy_preset("Interne")}}), encoding="utf-8")

    migrations.add_ids()
    migrations.add_ids()  # déjà migrés : rien ne change
    migrations.whole_step_presets()

    items = json.loads(shared.read_text(encoding="utf-8"))["items"]
    assert [(raw["name"], raw["created_by"], raw["updated_by"]) for raw in items] == [("Ancien", None, None)]
    assert items[0]["id"]
    # le préset qui ne nommait qu'une recette est devenu une étape entière qui la nomme
    assert "payload" not in items[0] and items[0]["step"]["recipe"] == "CVD Conformal"

    listed = list_items(client, "step-presets", microproject=slug)
    old_shared, old_own = by_name(listed, "Ancien"), by_name(listed, "Interne")
    assert (old_shared["scope"], old_shared["created_by"], old_shared["can_edit"]) == ("shared", None, False)
    # un élément de µprojet sans auteur reste modifiable par les éditeurs du µprojet
    assert update_item(client, "step-presets", old_own["id"], notes="repris")["notes"] == "repris"
    assert client.delete(f"/api/step-presets/{old_shared['id']}").status_code == 403

    # sans auteur connu, seul un administrateur peut modifier ou supprimer un élément partagé
    switch_user(client, "admin@example.com")
    delete_item(client, "step-presets", old_shared["id"])


def test_an_untouched_shipped_presets_file_is_replaced_by_the_whole_step_one(client, monkeypatch):
    from spectre.plugins.library.service import DEFAULTS_DIR, library_dir

    signup(client, "admin@example.com")
    active = library_dir() / "presets.yml"
    shipped = "presets:\n  - name: MOCVD Epitaxial\n    kind: deposition\n    recipe: MOCVD Epitaxial\n"
    monkeypatch.setattr(migrations, "_SHIPPED_RECIPE_ONLY_PRESETS", {hashlib.sha256(shipped.encode("utf-8")).hexdigest()})

    active.write_text(shipped + "  - name: Ma recette\n    kind: deposition\n    recipe: CVD Conformal\n", encoding="utf-8")
    migrations.ship_whole_step_presets()
    assert "Ma recette" in active.read_text(encoding="utf-8")  # édité : laissé tel quel

    active.write_bytes(shipped.replace("\n", "\r\n").encode("utf-8"))  # les fins de ligne ne comptent pas
    migrations.ship_whole_step_presets()
    assert active.read_bytes() == (DEFAULTS_DIR / "presets.yml").read_bytes()
