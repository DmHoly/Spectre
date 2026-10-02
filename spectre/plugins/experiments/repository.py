"""Where a microproject's experiments live: its Follow repository (``<microproject dir>/follow``),
and the reading of an experiment that every view shares - Spectre's own statuses (« hold »,
« continued ») on top of Follow's four, and the current tip of each line of study.
"""

from __future__ import annotations

from pathlib import Path

from ..microprojects.service import microproject_dir


def follow_repo_path(slug: str) -> Path:
    return microproject_dir(slug) / "follow"


def get_repository(slug: str):
    """A fresh ``follow.storage.repository.Repository`` for this microproject, reloaded from disk on
    every call - Spectre serves many microprojects from one process, so nothing is cached in memory
    the way ``follow_api`` (one repository per process) can afford to.
    """
    import follow

    return follow.Repository(follow_repo_path(slug))


RUNNING_STATUSES = {"draft", "running"}
CONCLUDED_STATUSES = {"concluded", "abandoned"}

# Deux statuts propres à Spectre, en plus des quatre de Follow (draft, running, concluded, abandoned) :
# - « hold » (en pause) : posé à la main (POST .../statut). L'étude garde son statut Follow (brouillon ou
#   en cours - elle compte toujours comme non terminée) et porte metadata["hold"] = {since, by, reason} ;
#   la reprendre, la conclure ou en dériver une nouvelle version retire la clé.
# - « continued » (continuée) : déduit, jamais enregistré - un brouillon jamais conclu dont une version
#   suivante a repris le travail (un enfant dans le graphe de filiation).
HOLD_KEY = "hold"


def hold_of(experiment) -> dict | None:
    """The pause on an experiment still in progress (``{"since", "by", "reason"}``), if any."""
    hold = experiment.metadata.get(HOLD_KEY)
    return hold if hold and experiment.conclusion.status in RUNNING_STATUSES else None


def display_status(experiment, *, continued: bool = False) -> str:
    """The status Spectre shows for ``experiment``: Follow's own, « hold » while paused, or
    « continued » for a draft a newer version took up (``continued`` - the caller knows the graph)."""
    if continued and experiment.conclusion.status == "draft":
        return "continued"
    if hold_of(experiment):
        return "hold"
    return experiment.conclusion.status


def branch_tips(repo) -> list:
    """One experiment per branch - its current tip - rather than every version ever committed to
    it. A branch is one line of study: "conclure"/"preuves"/"étiquettes" all record a new,
    otherwise-identical version (experiments are immutable), so without this a single study could
    show up as several cards, its own earlier drafts included, even after being concluded. The
    full version-by-version history is still there on the fiche itself ("Suivi de l'expérience")
    and on the microproject's graph - this only thins out summary lists (the experiences list, microproject
    counts, "comparer avec", "combiner avec").
    """
    seen_ids: set[str] = set()
    tips = []
    for tip_id in repo.branches.values():
        if tip_id in seen_ids:
            continue
        seen_ids.add(tip_id)
        tips.append(repo.get(tip_id))
    return tips


def experiment_counts(slug: str) -> tuple[int, int]:
    """``(running, concluded)`` among the microproject's current lines of study."""
    tips = branch_tips(get_repository(slug))
    running = sum(1 for exp in tips if exp.conclusion.status in RUNNING_STATUSES)
    concluded = sum(1 for exp in tips if exp.conclusion.status in CONCLUDED_STATUSES)
    return running, concluded
