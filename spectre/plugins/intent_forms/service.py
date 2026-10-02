"""Formulaires d'intention : une bibliothèque de questionnaires nommés qu'un projet choisit comme
formulaire actif - les questions posées systématiquement à chaque nouvelle expérience/évolution
(qui a lancé ce run, sur quel équipement, un risque identifié...) plutôt que confiées à un champ de
texte libre que personne n'est obligé de bien remplir.

Follow n'a rien de nouveau à apprendre ici : :class:`follow.storage.commit_form.CommitForm` (un
YAML de questions structurées - label, type, choix, obligatoire ou non) et
:attr:`follow.storage.repository.Repository.commit_form` existent déjà, génériques, et
explicitement pensés pour "piloter, plus tard, un vrai formulaire d'interface" (voir
``follow/storage/commit_form.py``). Ce qui manquait côté Spectre : un endroit où stocker plusieurs
formulaires nommés (la même bibliothèque partagée/par-projet que les présets d'étape, les
structures sauvegardées et les briques technologiques, via
:class:`~spectre.kernel.json_store.KeyedJsonStore`), et lequel est actuellement actif pour un projet
donné - voir :func:`activate_intent_form`/:func:`get_active_intent_form`/:func:`deactivate_intent_form`,
qui matérialisent le choix en ``commit_form.yml`` dans le dépôt Follow du projet : le seul endroit où
Follow va effectivement le lire.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from follow.storage.commit_form import CommitForm
from pydantic import BaseModel, Field

from ...kernel.db import data_dir
from ...kernel.json_store import KeyedJsonStore
from ..experiments.repository import follow_repo_path
from ..microprojects.service import microproject_dir


class IntentForm(BaseModel):
    name: str
    form: CommitForm
    created_at: str


class IntentFormLibrary(BaseModel):
    forms: dict[str, IntentForm] = Field(default_factory=dict)


def IntentFormStore(path: str | Path) -> KeyedJsonStore[IntentFormLibrary, IntentForm]:
    return KeyedJsonStore(path, IntentFormLibrary, "forms")


def parse_yaml_form(text: str) -> CommitForm:
    """Validate an uploaded commit-form YAML's text against :class:`CommitForm` - the same shape
    :func:`follow.storage.commit_form.load_commit_form` reads from a path, applied directly to
    already-uploaded text (a file picked in the browser) instead of a path on disk.
    """
    payload = yaml.safe_load(text) or {}
    if not isinstance(payload, dict):
        raise ValueError("le fichier doit être un document YAML avec des champs 'title'/'fields'")
    return CommitForm.model_validate(payload)


def dump_yaml_form(form: CommitForm) -> str:
    """The inverse of :func:`parse_yaml_form` - used to write a library entry out as
    ``commit_form.yml`` once a microproject activates it (see :func:`activate_intent_form`).
    """
    return yaml.safe_dump(form.model_dump(mode="json", exclude_none=True), allow_unicode=True, sort_keys=False)


def get_intent_form_store(slug: str) -> KeyedJsonStore:
    return IntentFormStore(microproject_dir(slug) / "formulaires_intention.json")


def get_shared_intent_form_store() -> KeyedJsonStore:
    return IntentFormStore(data_dir() / "formulaires_intention_partagees.json")


def active_intent_form_path(slug: str) -> Path:
    return microproject_dir(slug) / "formulaire_intention_actif.json"


def get_active_intent_form(slug: str) -> dict | None:
    """Which library entry (``{"name": ..., "partagee": bool}``) this microproject currently uses as
    its Follow commit form, if any - just a pointer to the library entry (so the settings page can
    show "formulaire actif : X" and offer to deactivate it) alongside the real materialized copy,
    ``<repo>/commit_form.yml``, which is the only file Follow itself ever reads.
    """
    path = active_intent_form_path(slug)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def activate_intent_form(slug: str, *, name: str, partagee: bool, form) -> None:
    """Materialize ``form`` (a :class:`follow.storage.commit_form.CommitForm`) as this microproject's
    active commit form - written to ``<repo>/commit_form.yml``, which
    ``follow.storage.repository.Repository`` picks up automatically the next time this microproject's
    repository is opened (every :func:`spectre.plugins.experiments.repository.get_repository` call -
    nothing is cached), and remember which library entry it came from.
    """
    repo_path = follow_repo_path(slug)
    repo_path.mkdir(parents=True, exist_ok=True)
    (repo_path / "commit_form.yml").write_text(dump_yaml_form(form), encoding="utf-8")
    active_intent_form_path(slug).write_text(json.dumps({"name": name, "partagee": partagee}), encoding="utf-8")


def deactivate_intent_form(slug: str) -> None:
    (follow_repo_path(slug) / "commit_form.yml").unlink(missing_ok=True)
    active_intent_form_path(slug).unlink(missing_ok=True)
