"""Les étiquettes d'une étude : chaque changement est une version, qui garde le statut ; une entrée
du cahier ou une conclusion les reporte. (Combiner deux études : ``test_combine.py``.)"""

from __future__ import annotations

from support.experiments import conclude, experiment_url, get_experiment, launch, tag
from support.microprojects import signup_with_microproject
from support.notebook import add_manual


def test_setting_and_removing_tags_records_a_new_version_and_preserves_status(client):
    slug = signup_with_microproject(client, "tags@example.com")
    launched = launch(client, slug, title="Reference", intent="Depart")

    response = client.put(f"{experiment_url(slug, launched['id'])}/tags", json={"tags": ["a valider", "prioritaire", "a valider", " "]})
    assert response.status_code == 200
    tagged = response.json()
    assert tagged["tags"] == ["a valider", "prioritaire"]
    assert tagged["version_id"] != launched["version_id"]
    assert tagged["status"] == "draft"  # tagging must not change the status

    assert tag(client, slug, launched["id"], ["prioritaire"])["tags"] == ["prioritaire"]


def test_adding_a_notebook_entry_or_concluding_preserves_existing_tags(client):
    slug = signup_with_microproject(client, "tagscarry@example.com")
    launched = launch(client, slug, title="Reference", intent="Depart")
    tag(client, slug, launched["id"], ["important"])

    add_manual(client, slug, launched["id"], measurements=[{"text": "profilometre"}])
    assert get_experiment(client, slug, launched["id"])["tags"] == ["important"]

    concluded = conclude(client, slug, launched["id"], summary="Fini", objective_results=[])
    assert concluded["tags"] == ["important"]
    assert concluded["status"] == "concluded"


def test_concluding_does_not_reset_status_of_a_later_notebook_entry(client):
    # regression: adding evidence used to leave `conclusion` at its fresh default, silently
    # un-concluding an already-concluded experience the moment evidence was attached to it.
    slug = signup_with_microproject(client, "statuscarry@example.com")
    launched = launch(client, slug, title="Reference", intent="Depart")
    assert conclude(client, slug, launched["id"], summary="Fini", objective_results=[])["status"] == "concluded"

    add_manual(client, slug, launched["id"], "Mesure tardive", measurements=[{"text": "profilometre"}])
    assert get_experiment(client, slug, launched["id"])["status"] == "concluded"
