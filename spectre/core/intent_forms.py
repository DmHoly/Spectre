"""Formulaires d'intention : une bibliothèque de questionnaires nommés qu'un projet choisit comme
formulaire actif - les questions posées systématiquement à chaque nouvelle expérience/évolution
(qui a lancé ce run, sur quel équipement, un risque identifié...) plutôt que confiées à un champ de
texte libre que personne n'est obligé de bien remplir.

Follow n'a rien de nouveau à apprendre ici : :class:`follow.storage.commit_form.CommitForm` (un
YAML de questions structurées - label, type, choix, obligatoire ou non) et
:attr:`follow.storage.repository.Repository.commit_form` existent déjà, génériques, et
explicitement pensés pour "piloter, plus tard, un vrai formulaire d'interface" (voir
``follow/storage/commit_form.py``). Ce qui manquait côté Spectre : un endroit où stocker plusieurs
formulaires nommés (la même bibliothèque partagée/par-projet que
:mod:`spectre.core.step_presets`/:mod:`spectre.core.structure_library`/:mod:`spectre.core.
tech_bricks`, via :class:`~spectre.core.keyed_store.KeyedJsonStore`), et lequel est actuellement
actif pour un projet donné - voir :func:`activate`/:func:`active_form`/:func:`deactivate` dans
:mod:`spectre.core.projects`, qui matérialisent le choix en ``commit_form.yml`` dans le dépôt
Follow du projet : le seul endroit où Follow va effectivement le lire.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from follow.storage.commit_form import CommitForm
from pydantic import BaseModel, Field

from .keyed_store import KeyedJsonStore


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
    ``commit_form.yml`` once a project activates it (see ``spectre.core.projects.activate_intent_form``).
    """
    return yaml.safe_dump(form.model_dump(mode="json", exclude_none=True), allow_unicode=True, sort_keys=False)
