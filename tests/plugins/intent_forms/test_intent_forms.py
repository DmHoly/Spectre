"""Formulaires d'intention (spectre.plugins.intent_forms) : une bibliothèque de modèles
follow.storage.commit_form.CommitForm (partagée, ou propre à un µprojet), dont un µprojet active une
copie - son commit_form.yml Follow, exigé par Follow lui-même à chaque commit.
"""

from __future__ import annotations

import json

import pytest

from support.accounts import signup, switch_user
from support.experiments import conclude, evolve, get_experiment, launch, tag
from support.http import assert_handler_404
from support.intent_forms import (
    SIMPLE_FORM_YAML,
    activate_intent_form,
    activate_simple_form,
    active_path,
    assert_no_active_intent_form,
    create_intent_form,
    deactivate_intent_form,
    delete_intent_form,
    get_active_intent_form,
    get_intent_form,
    list_intent_forms,
    update_intent_form,
)
from support.microprojects import create_microproject, join_as, signup_with_microproject
from support.structures import steps

_TWO_FIELDS_YAML = SIMPLE_FORM_YAML + """
  - name: equipement
    label: Équipement
    type: string
    required: true
"""


def _rejected(call, *args, **kwargs) -> str:
    """Le message d'échec d'une aide de support.experiments (qui exige un 201) : un appel refusé."""
    with pytest.raises(AssertionError) as failure:
        call(*args, **kwargs)
    return str(failure.value)


# --- bibliothèque -----------------------------------------------------------------------------


def test_create_and_list_intent_form(client):
    slug = signup_with_microproject(client, "forms-list@example.com", name="Alice")
    created = create_intent_form(client, slug)
    assert created["name"] == "Simple"
    assert created["scope"] == "microproject"
    assert created["microproject"] == slug
    assert created["created_by"]["name"] == created["updated_by"]["name"] == "Alice"
    assert created["created_by"] == created["updated_by"]
    assert created["form"]["title"] == "Formulaire simple"
    assert created["can_edit"] is True

    items = list_intent_forms(client, microproject=slug)
    assert [(item["id"], item["scope"]) for item in items] == [(created["id"], "microproject")]
    assert items[0]["form"]["title"] == "Formulaire simple"
    assert list_intent_forms(client, microproject=slug, scope="shared") == []
    assert list_intent_forms(client, microproject=slug, scope="builtin") == []
    assert list_intent_forms(client) == []  # sans µprojet : la bibliothèque partagée seule
    assert get_intent_form(client, created["id"]) == created


def test_the_shared_library_is_listed_with_each_microproject(client):
    slug = signup_with_microproject(client, "forms-shared@example.com")
    shared = create_intent_form(client, name="Commun")
    own = create_intent_form(client, slug, name="Local")
    assert shared["scope"] == "shared" and shared["microproject"] is None

    assert [item["id"] for item in list_intent_forms(client, microproject=slug)] == [shared["id"], own["id"]]
    assert [item["id"] for item in list_intent_forms(client)] == [shared["id"]]
    assert [item["id"] for item in list_intent_forms(client, microproject=slug, scope="microproject")] == [own["id"]]


def test_unknown_form_is_404(client):
    signup(client, "forms-404@example.com")
    assert_handler_404(client.get("/api/intent-forms/inconnu"), "introuvable")
    assert_handler_404(client.patch("/api/intent-forms/inconnu", json={"name": "X"}), "introuvable")
    assert_handler_404(client.delete("/api/intent-forms/inconnu"), "introuvable")


def test_invalid_yaml_is_rejected(client):
    slug = signup_with_microproject(client, "forms-invalid@example.com")
    response = client.post("/api/intent-forms", json={"name": "Cassé", "yaml": "not: [valid", "scope": "microproject", "microproject": slug})
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_input"
    assert list_intent_forms(client, microproject=slug) == []


def test_invalid_scope_is_rejected(client):
    slug = signup_with_microproject(client, "forms-scope@example.com")
    body = {"name": "X", "yaml": SIMPLE_FORM_YAML}
    assert client.post("/api/intent-forms", json={**body, "scope": "builtin"}).status_code == 422
    assert client.post("/api/intent-forms", json={**body, "scope": "microproject"}).status_code == 422
    assert client.get("/api/intent-forms", params={"scope": "microproject"}).status_code == 422
    assert client.get("/api/intent-forms", params={"microproject": slug, "scope": "autre"}).status_code == 422


def test_duplicate_name_conflicts(client):
    slug = signup_with_microproject(client, "forms-dup@example.com")
    create_intent_form(client, slug)
    response = client.post("/api/intent-forms", json={"name": "Simple", "yaml": SIMPLE_FORM_YAML, "scope": "microproject", "microproject": slug})
    assert response.status_code == 409
    # une autre étagère n'est pas en conflit
    create_intent_form(client, name="Simple")


def test_renaming_onto_a_taken_name_conflicts_instead_of_overwriting(client):
    slug = signup_with_microproject(client, "forms-rename@example.com")
    first = create_intent_form(client, slug, name="Premier")
    second = create_intent_form(client, slug, name="Second", yaml=_TWO_FIELDS_YAML)

    response = client.patch(f"/api/intent-forms/{second['id']}", json={"name": "Premier"})
    assert response.status_code == 409
    assert {item["name"]: item["id"] for item in list_intent_forms(client, microproject=slug)} == {"Premier": first["id"], "Second": second["id"]}

    renamed = update_intent_form(client, second["id"], name="Deux / bis")
    assert renamed["name"] == "Deux / bis" and renamed["id"] == second["id"]
    assert len(renamed["form"]["fields"]) == 2
    assert get_intent_form(client, second["id"])["name"] == "Deux / bis"


def test_patch_without_change_keeps_the_entry(client):
    slug = signup_with_microproject(client, "forms-noop@example.com")
    created = create_intent_form(client, slug)
    assert update_intent_form(client, created["id"], name="Simple", yaml=SIMPLE_FORM_YAML) == created


def test_deleting_an_entry_returns_204(client):
    slug = signup_with_microproject(client, "forms-del@example.com")
    created = create_intent_form(client, slug)
    delete_intent_form(client, created["id"])
    assert list_intent_forms(client, microproject=slug) == []
    assert_handler_404(client.get(f"/api/intent-forms/{created['id']}"))


# --- droits -----------------------------------------------------------------------------------


def test_a_shared_entry_is_modified_by_its_author_or_an_admin_only(client):
    signup(client, "admin@example.com", name="Admin")  # le premier compte est admin
    switch_user(client, "auteur@example.com", name="Auteur")
    shared = create_intent_form(client, name="Commun")
    assert shared["created_by"]["name"] == "Auteur" and shared["can_edit"] is True

    switch_user(client, "autre@example.com", name="Autre")
    assert list_intent_forms(client)[0]["can_edit"] is False
    assert client.patch(f"/api/intent-forms/{shared['id']}", json={"name": "Pris"}).status_code == 403
    assert client.delete(f"/api/intent-forms/{shared['id']}").status_code == 403
    assert get_intent_form(client, shared["id"])["name"] == "Commun"

    switch_user(client, "admin@example.com")
    renamed = update_intent_form(client, shared["id"], name="Commun (revu)")
    assert renamed["created_by"]["name"] == "Auteur" and renamed["updated_by"]["name"] == "Admin"
    assert renamed["updated_by"]["id"] != renamed["created_by"]["id"]

    switch_user(client, "auteur@example.com")
    delete_intent_form(client, shared["id"])


def test_a_viewer_reads_the_microproject_library_but_does_not_write_it(client):
    slug = signup_with_microproject(client, "owner-forms@example.com")
    own = create_intent_form(client, slug)
    join_as(client, slug, "viewer-forms@example.com", owner="owner-forms@example.com", role="viewer")

    assert [item["id"] for item in list_intent_forms(client, microproject=slug)] == [own["id"]]
    assert list_intent_forms(client, microproject=slug)[0]["can_edit"] is False
    body = {"name": "Autre", "yaml": SIMPLE_FORM_YAML, "scope": "microproject", "microproject": slug}
    assert client.post("/api/intent-forms", json=body).status_code == 403
    assert client.patch(f"/api/intent-forms/{own['id']}", json={"name": "X"}).status_code == 403
    assert client.delete(f"/api/intent-forms/{own['id']}").status_code == 403
    assert client.put(active_path(slug), json={"intent_form_id": own["id"]}).status_code == 403
    assert client.delete(active_path(slug)).status_code == 403


def test_a_non_member_sees_neither_the_library_nor_the_active_form(client):
    slug = signup_with_microproject(client, "owner-private@example.com")
    own = create_intent_form(client, slug)
    activate_intent_form(client, slug, own["id"])

    switch_user(client, "stranger@example.com")
    assert client.get("/api/intent-forms", params={"microproject": slug}).status_code == 403
    # l'entrée d'un µprojet dont on n'est pas membre est introuvable, comme dans process_library
    assert_handler_404(client.get(f"/api/intent-forms/{own['id']}"), "introuvable")
    assert_handler_404(client.patch(f"/api/intent-forms/{own['id']}", json={"name": "X"}), "introuvable")
    assert_handler_404(client.delete(f"/api/intent-forms/{own['id']}"), "introuvable")
    assert client.get(active_path(slug)).status_code == 403
    assert list_intent_forms(client) == []


def test_another_microprojects_entry_cannot_be_activated(client):
    slug = signup_with_microproject(client, "forms-two@example.com")
    other = create_microproject(client, "Autre")["slug"]
    foreign = create_intent_form(client, other)
    assert_handler_404(client.put(active_path(slug), json={"intent_form_id": foreign["id"]}), "introuvable")


# --- formulaire actif -------------------------------------------------------------------------


def test_launching_without_an_active_form_needs_no_answers(client):
    slug = signup_with_microproject(client, "forms-none@example.com")
    launch(client, slug)
    assert_no_active_intent_form(client, slug)


def test_activating_a_form_requires_its_fields_on_launch(client):
    slug = signup_with_microproject(client, "forms-required@example.com")
    activated = activate_simple_form(client, slug)
    assert activated["form"]["title"] == "Formulaire simple"
    assert activated["origin"]["name"] == "Simple" and activated["outdated"] is False
    assert get_active_intent_form(client, slug) == activated

    missing = _rejected(launch, client, slug)
    assert "422 au lieu de 201" in missing
    assert "operateur" in missing

    ok = launch(client, slug, form_answers={"operateur": "Alice"})
    assert get_experiment(client, slug, ok["id"])["form_answers"] == {"operateur": "Alice"}


def test_lightweight_actions_carry_forward_form_answers_unchanged(client):
    slug = signup_with_microproject(client, "forms-carry@example.com")
    activate_simple_form(client, slug)
    launched = launch(client, slug, form_answers={"operateur": "Alice"})

    tagged = tag(client, slug, launched["id"], ["a-suivre"])
    assert tagged["form_answers"] == {"operateur": "Alice"}


def test_evolving_requires_reanswering_the_form(client):
    slug = signup_with_microproject(client, "forms-evolve@example.com")
    activate_simple_form(client, slug)
    launched = launch(client, slug, form_answers={"operateur": "Alice"})

    refused = _rejected(evolve, client, slug, launched["id"], title="Suite", intent="x", steps=steps(30))
    assert "422 au lieu de 201" in refused and "operateur" in refused

    ok = evolve(client, slug, launched["id"], title="Suite", intent="x", steps=steps(30), form_answers={"operateur": "Bob"})
    assert ok["form_answers"] == {"operateur": "Bob"}


def test_activating_a_form_after_launch_does_not_block_lightweight_writes(client):
    # les réponses d'une écriture légère sont reportées, pas saisies : un formulaire activé après
    # coup ne bloque ni une étiquette ni la conclusion - seulement la prochaine vraie évolution.
    slug = signup_with_microproject(client, "forms-late@example.com")
    launched = launch(client, slug)
    activate_simple_form(client, slug)

    tag(client, slug, launched["id"], ["a-suivre"])
    concluded = conclude(client, slug, launched["id"], summary="Fini")
    assert concluded["status"] == "concluded" and concluded["form_answers"] == {}
    assert "operateur" in _rejected(evolve, client, slug, launched["id"], title="Suite", intent="x", steps=steps(30))


def test_deleting_the_library_entry_keeps_the_active_copy(client):
    slug = signup_with_microproject(client, "forms-delete@example.com")
    activated = activate_simple_form(client, slug)

    delete_intent_form(client, activated["origin"]["form_id"])
    assert get_active_intent_form(client, slug) == activated  # rien ne pointe dans le vide : c'est une copie

    assert "operateur" in _rejected(launch, client, slug)
    launch(client, slug, form_answers={"operateur": "Alice"})


def test_editing_the_active_entry_only_applies_once_reactivated(client):
    slug = signup_with_microproject(client, "forms-snapshot@example.com")
    activated = activate_simple_form(client, slug)
    form_id = activated["origin"]["form_id"]

    update_intent_form(client, form_id, yaml=_TWO_FIELDS_YAML)
    active = get_active_intent_form(client, slug)
    assert active["outdated"] is True
    assert [field["name"] for field in active["form"]["fields"]] == ["operateur"]
    launch(client, slug, form_answers={"operateur": "Alice"})  # l'ancien formulaire s'applique encore

    reactivated = activate_intent_form(client, slug, form_id)
    assert reactivated["outdated"] is False
    assert [field["name"] for field in reactivated["form"]["fields"]] == ["operateur", "equipement"]
    assert "equipement" in _rejected(launch, client, slug, form_answers={"operateur": "Alice"})


def test_renaming_the_active_entry_does_not_make_it_outdated(client):
    slug = signup_with_microproject(client, "forms-rename-active@example.com")
    activated = activate_simple_form(client, slug)
    update_intent_form(client, activated["origin"]["form_id"], name="Renommé")
    assert get_active_intent_form(client, slug)["outdated"] is False


def test_deactivating_a_form_stops_requiring_it(client):
    slug = signup_with_microproject(client, "forms-deactivate@example.com")
    activate_simple_form(client, slug)

    deactivate_intent_form(client, slug)
    assert_no_active_intent_form(client, slug)
    deactivate_intent_form(client, slug)  # sans formulaire actif : rien à retirer, toujours 204

    launch(client, slug)


def test_commit_form_yml_is_the_only_truth(client, data_dir):
    slug = signup_with_microproject(client, "forms-truth@example.com")
    activated = activate_simple_form(client, slug)
    commit_form = data_dir / "microprojects" / slug / "follow" / "commit_form.yml"
    assert "Formulaire simple" in commit_form.read_text(encoding="utf-8")
    assert not (data_dir / "microprojects" / slug / "formulaire_intention_actif.json").exists()

    # un formulaire posé à la main dans le dépôt est le formulaire actif, sans origine
    commit_form.write_text("title: À la main\nfields:\n  - name: lot\n    label: Lot\n", encoding="utf-8")
    active = get_active_intent_form(client, slug)
    assert active["form"]["title"] == "À la main" and active["origin"] is None and active["outdated"] is False
    assert "lot" in _rejected(launch, client, slug, form_answers={"operateur": "Alice"})

    commit_form.unlink()
    assert_no_active_intent_form(client, slug)
    assert activated["origin"]["form_id"] in [item["id"] for item in list_intent_forms(client, microproject=slug)]


# --- migration des fichiers d'avant les identifiants --------------------------------------------


def test_legacy_name_keyed_files_are_migrated(data_dir):
    from fastapi.testclient import TestClient

    from spectre.kernel.app import create_app

    form = {"title": "Ancien", "fields": [{"name": "operateur", "label": "Opérateur", "type": "string", "required": True}]}
    legacy_entry = {"name": "Ancien", "form": form, "created_at": "2025-01-01T00:00:00+00:00"}
    microproject = data_dir / "microprojects" / "projet"
    (microproject / "follow").mkdir(parents=True)
    (data_dir / "formulaires_intention_partagees.json").write_text(json.dumps({"forms": {"Commun": {**legacy_entry, "name": "Commun"}}}), encoding="utf-8")
    (microproject / "formulaires_intention.json").write_text(json.dumps({"forms": {"Ancien": legacy_entry}}), encoding="utf-8")
    (microproject / "formulaire_intention_actif.json").write_text(json.dumps({"name": "Ancien", "partagee": False}), encoding="utf-8")
    (microproject / "follow" / "commit_form.yml").write_text("title: Ancien\nfields:\n  - name: operateur\n    label: Opérateur\n", encoding="utf-8")

    with TestClient(create_app()) as client:
        slug = signup_with_microproject(client, "legacy@example.com")
        assert slug == "projet"
        items = list_intent_forms(client, microproject=slug)
        assert [(item["name"], item["scope"], item["created_at"]) for item in items] == [
            ("Commun", "shared", "2025-01-01T00:00:00+00:00"),
            ("Ancien", "microproject", "2025-01-01T00:00:00+00:00"),
        ]
        active = get_active_intent_form(client, slug)
        assert active["origin"] == {"form_id": items[1]["id"], "name": "Ancien"}
        assert active["outdated"] is False

    assert not (data_dir / "formulaires_intention_partagees.json").exists()
    assert not (microproject / "formulaires_intention.json").exists()
    assert not (microproject / "formulaire_intention_actif.json").exists()
