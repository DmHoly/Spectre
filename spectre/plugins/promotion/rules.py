"""Les règles d'une promotion : ce qu'on vérifie avant qu'une structure devienne une référence.

Un registre (:func:`register_rule`), comme les sources du comparateur : chaque règle reçoit le
:class:`Candidate` (la source, la référence visée, ce que la publication donnerait) et rend un
:class:`Verdict` - ``ok`` (vérifiée), ``warn`` (on peut promouvoir, en le sachant), ``block`` (on ne
peut pas : le formulaire dit pourquoi, la promotion est refusée avec le statut et le code du verdict)
- ou ``None`` quand elle ne s'applique pas. Le formulaire montre toutes les règles, dans leur ordre,
avant qu'on promeuve ; chaque promotion garde les verdicts rendus ce jour-là.

Choisir une référence suivra un jour d'autres règles (des mesures attendues, une validation par un
responsable, un nombre de plaques...) : une règle de plus est une fonction de plus, enregistrée ici
ou par un autre plugin (``from ..promotion.rules import Rule, Verdict, register_rule``) - ni le
formulaire, ni l'API, ni le domaine des références ne changent. Les règles de base sont en bas de ce
module."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from ...kernel.errors import Conflict, DomainError, Forbidden, InvalidInput
from ..accounts.service import User
from ..experiments.repository import CONCLUDED_STATUSES, display_status
from ..microprojects import service as microprojects
from ..references import service as references
from ..structures import kinds

Level = Literal["ok", "warn", "block"]


@dataclass(frozen=True)
class Verdict:
    """Ce qu'une règle dit d'un candidat. Pour ``block`` : l'erreur levée à la promotion
    (``error`` : sa classe - :class:`Conflict` par défaut - et ``code``)."""

    level: Level
    message: str
    code: str | None = None
    error: type[DomainError] = Conflict

    def as_error(self) -> DomainError:
        return self.error(self.message, code=self.code)


def ok(message: str) -> Verdict:
    return Verdict("ok", message)


def warn(message: str, code: str | None = None) -> Verdict:
    return Verdict("warn", message, code)


def block(message: str, code: str, error: type[DomainError] = Conflict) -> Verdict:
    return Verdict("block", message, code, error)


@dataclass(frozen=True)
class Candidate:
    """Ce qu'une règle lit d'une promotion envisagée : qui promeut, la publication planifiée
    (:class:`references.Publication` : la source, son instantané, la référence visée, la version
    dont elle dériverait, le numéro qu'elle prendrait), le nom d'une nouvelle référence
    (``new_name``, quand ``publication.reference`` est ``None``) et la justification."""

    user: User
    publication: references.Publication
    new_name: str | None
    new_name_taken: bool
    note: str
    extra: dict[str, Any] = field(default_factory=dict)  # pour les règles à venir

    @property
    def source(self) -> references.PublicationSource:
        return self.publication.source


@dataclass(frozen=True)
class Rule:
    """Une règle : ``id`` stable (gardé avec chaque promotion), ``label`` (ce qu'elle vérifie, dans
    le formulaire), ``check`` et sa place (``order``) dans la liste."""

    id: str
    label: str
    check: Callable[[Candidate], Verdict | None]
    order: int = 100


_RULES: dict[str, Rule] = {}


def register_rule(rule: Rule) -> None:
    _RULES[rule.id] = rule


def rules() -> list[Rule]:
    return sorted(_RULES.values(), key=lambda r: (r.order, r.id))


def evaluate(candidate: Candidate) -> list[dict[str, Any]]:
    """Les verdicts de toutes les règles qui s'appliquent, dans leur ordre :
    ``[{rule, label, level, message, code}]`` (ce que montre le formulaire et que garde la
    promotion)."""
    results = []
    for rule in rules():
        verdict = rule.check(candidate)
        if verdict is None:
            continue
        results.append({"rule": rule.id, "label": rule.label, "level": verdict.level, "message": verdict.message, "code": verdict.code, "_verdict": verdict})
    return results


def first_block(results: list[dict[str, Any]]) -> Verdict | None:
    return next((r["_verdict"] for r in results if r["level"] == "block"), None)


def public(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{key: value for key, value in r.items() if not key.startswith("_")} for r in results]


# -- les règles de base ----------------------------------------------------------------------------


def _editor(candidate: Candidate) -> Verdict:
    microproject = candidate.source.microproject
    if microprojects.has_role(candidate.user, microproject, "editor"):
        return ok(f"Vous êtes éditeur du µprojet « {microproject.name} ».")
    return block(f"Promouvoir demande le rôle d'éditeur sur le µprojet « {microproject.name} ».", "forbidden", Forbidden)


def _variant(candidate: Candidate) -> Verdict | None:
    source = candidate.source
    if not source.is_campaign:
        return None
    labels = references.variant_labels(source.version)
    if source.variant is None:
        return block("C'est un split : choisissez la variante (la plaque) qui devient la référence.", "variant_required", InvalidInput)
    name = labels[source.variant] if 0 <= source.variant < len(labels) else f"Variante {source.variant + 1}"
    return ok(f"Variante choisie : {name}.")


def _drawn(candidate: Candidate) -> Verdict | None:
    publication = candidate.publication
    if publication.snapshot is not None:
        return ok("Structure dessinée dans le constructeur : on pourra lancer une étude depuis elle.")
    if publication.snapshot_error is not None:
        return block(str(publication.snapshot_error), publication.snapshot_error.code, InvalidInput)
    source = candidate.source
    if source.is_campaign and source.variant is None:
        return None  # la règle « Variante du split » le dit déjà
    kind = kinds.structure_kind_name(source.version.structure_type)
    why = {"images": "une structure donnée en images", "declared": "une étude sans structure dessinée"}.get(kind, "une structure sans procédé")
    return block(
        f"C'est {why} : une référence est un point de départ du constructeur, il lui faut un procédé dessiné.",
        "reference_needs_process",
        InvalidInput,
    )


def _target(candidate: Candidate) -> Verdict:
    publication = candidate.publication
    if publication.reference is not None:
        return ok(f"Nouvelle version de « {publication.reference.name} ».")
    name = (candidate.new_name or "").strip()
    if not name:
        return block("Choisissez une référence existante, ou nommez la nouvelle référence.", "invalid_reference_name", InvalidInput)
    if candidate.new_name_taken:
        return block(f"Une référence porte déjà le nom « {name} » : choisissez-la, ou un autre nom.", "reference_name_taken")
    return ok(f"Nouvelle référence « {name} » : la structure en sera la version 1.0.")


def _changes(candidate: Candidate) -> Verdict | None:
    publication = candidate.publication
    if publication.snapshot is None or publication.base is None:
        return None
    if publication.level == "none":
        return block(
            f"Cette structure est identique à la version {publication.base.number} de la référence : rien à promouvoir.",
            "reference_version_identical",
        )
    return ok(f"Différente de la version {publication.base.number}.")


def _not_already(candidate: Candidate) -> Verdict | None:
    already = candidate.publication.already
    if already is None:
        return None
    return block(f"Cette structure est déjà la version {already.number} de la référence.", "reference_version_already_published")


def _concluded(candidate: Candidate) -> Verdict:
    version = candidate.source.version
    status = display_status(version)
    if status not in CONCLUDED_STATUSES:
        return warn("L'étude n'est pas conclue : vous pouvez promouvoir, sa conclusion viendra après.", "study_not_concluded")
    decision = version.conclusion.decision
    if decision and decision != "promote":
        return warn("La conclusion de l'étude n'a pas retenu cette structure comme référence.", "decision_differs")
    return ok("L'étude est conclue" + (" : retenue comme référence." if decision == "promote" else "."))


def _justified(candidate: Candidate) -> Verdict:
    if candidate.note.strip():
        return ok("Le pourquoi est écrit : il accompagnera la version.")
    return warn("Dites pourquoi cette structure devient la référence : c'est ce que liront ceux qui partiront d'elle.", "no_justification")


for _rule in (
    Rule("editor", "Droit de promouvoir", _editor, order=10),
    Rule("variant", "Variante du split", _variant, order=20),
    Rule("drawn_process", "Structure utilisable comme point de départ", _drawn, order=30),
    Rule("target", "Référence visée", _target, order=40),
    Rule("changes", "Différente de la version dont elle dérive", _changes, order=50),
    Rule("not_already", "Pas déjà promue", _not_already, order=60),
    Rule("concluded", "Étude conclue", _concluded, order=70),
    Rule("justified", "Justification", _justified, order=80),
):
    register_rule(_rule)
