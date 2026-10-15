"""Les règles d'une promotion de brique : ce qu'on vérifie avant qu'une brique devienne une brique
de référence (voir :mod:`spectre.plugins.process_library.tech_bricks`). Le même mécanisme que les
règles d'une structure (:mod:`.rules` : un registre, des verdicts ``ok`` / ``warn`` / ``block``),
sur un candidat plus simple : la brique, qui la promeut, et le pourquoi. Une règle de plus
s'enregistre ici (:func:`register_brick_rule`) sans que le formulaire ni l'API ne changent."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from ...kernel.errors import Conflict, Forbidden, InvalidInput
from ..accounts.service import User
from ..process_library import service as library
from ..process_library.service import Entry
from ..process_library.tech_bricks import TechBrick
from .rules import Rule, Verdict, block, ok, warn


@dataclass(frozen=True)
class BrickCandidate:
    """Ce qu'une règle lit d'une promotion de brique envisagée : qui promeut, la brique (et où elle
    est rangée), le pourquoi, et si une autre brique partagée porte déjà son nom."""

    user: User
    entry: Entry[TechBrick]
    note: str
    name_taken: bool

    @property
    def brick(self) -> TechBrick:
        return self.entry.item


_RULES: dict[str, Rule] = {}


def register_brick_rule(rule: Rule) -> None:
    _RULES[rule.id] = rule


def brick_rules() -> list[Rule]:
    return sorted(_RULES.values(), key=lambda r: (r.order, r.id))


def evaluate(candidate: BrickCandidate) -> list[dict[str, Any]]:
    """Les verdicts de toutes les règles qui s'appliquent, dans leur ordre (la forme de
    :func:`.rules.evaluate`)."""
    results = []
    for rule in brick_rules():
        verdict = rule.check(candidate)
        if verdict is None:
            continue
        results.append({"rule": rule.id, "label": rule.label, "level": verdict.level, "message": verdict.message, "code": verdict.code, "_verdict": verdict})
    return results


# -- les règles de base ----------------------------------------------------------------------------


def _editor(candidate: BrickCandidate) -> Verdict:
    entry = candidate.entry
    if entry.scope == "builtin":
        return block("Une brique intégrée (livrée avec l'instance) ne se promeut pas : dupliquez-la d'abord.", "builtin_brick", Forbidden)
    if library.can_edit(entry, candidate.user):
        where = f"du µprojet « {entry.microproject.name} »" if entry.microproject else "partagée"
        return ok(f"Vous pouvez modifier cette brique ({where}).")
    if entry.scope == "shared":
        return block("Promouvoir une brique partagée revient à son auteur ou à un administrateur.", "forbidden", Forbidden)
    return block(f"Promouvoir demande le rôle d'éditeur sur le µprojet « {entry.microproject.name} ».", "forbidden", Forbidden)


def _steps(candidate: BrickCandidate) -> Verdict:
    count = len(candidate.brick.steps)
    if not count:
        return block("Une brique de référence a au moins une étape.", "brick_empty", InvalidInput)
    start = " et son substrat (brique de départ)" if candidate.brick.substrate else ""
    return ok(f"{count} étape{'s' if count > 1 else ''}{start}, version {candidate.brick.version}.")


def _not_already(candidate: BrickCandidate) -> Verdict:
    if candidate.brick.is_reference:
        return block("Cette brique est déjà une brique de référence.", "brick_already_reference")
    return ok("Pas encore une brique de référence.")


def _name(candidate: BrickCandidate) -> Verdict:
    if candidate.name_taken:
        return block(f"Une brique partagée porte déjà le nom « {candidate.brick.name} » : renommez celle-ci d'abord.", "brick_name_taken")
    shared = "" if candidate.entry.scope == "shared" else " Elle passera en partagée, visible de tous les µprojets."
    return ok(f"« {candidate.brick.name} » : un nom libre parmi les briques partagées.{shared}")


def _justified(candidate: BrickCandidate) -> Verdict:
    if candidate.note.strip():
        return ok("Le pourquoi est écrit : il restera avec la brique.")
    return warn("Dites pourquoi cette brique devient la référence : c'est ce que liront ceux qui l'inséreront.", "no_justification")


for _rule in (
    Rule("editor", "Droit de promouvoir", _editor, order=10),
    Rule("steps", "Brique utilisable", _steps, order=20),
    Rule("not_already", "Pas déjà une référence", _not_already, order=30),
    Rule("name", "Nom libre", _name, order=40),
    Rule("justified", "Justification", _justified, order=50),
):
    register_brick_rule(_rule)
