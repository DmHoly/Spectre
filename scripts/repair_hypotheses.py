#!/usr/bin/env python3
"""Restaure les hypothèses effacées par les anciennes évolutions légères (bug B1 de ``REVIEW.md`` :
une étiquette, une preuve, un statut, une conclusion... dérivaient la nouvelle version sans reprendre
l'hypothèse de la précédente).

Pour chaque piste de chaque µprojet dont la dernière version n'a pas d'hypothèse, le script
cherche dans son historique (de la plus récente à la plus ancienne) la dernière hypothèse non
vide, et la reporte sur une nouvelle version de la piste par ``experiments.service.amend`` - le
seul chemin d'écriture, qui reporte tout le reste tel quel et refuse d'écrire si la piste a bougé
entre la lecture et l'écriture.

À blanc par défaut : le script affiche ce qu'il ferait, sans rien écrire. ``--apply`` écrit.
Relisez le rapport avant : une hypothèse retirée volontairement lors d'une vraie évolution
reviendrait elle aussi.

Usage :
    python scripts/repair_hypotheses.py [--data-dir DATA_DIR] [--microproject SLUG] [--apply]

Par défaut, lit ``SPECTRE_DATA_DIR`` (ou ``./data`` si absent). Arrêtez le serveur avant
``--apply`` : le verrou des écritures ne vaut qu'à l'intérieur d'un processus.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path

AUTHOR = "Réparation des hypothèses"


@dataclass(frozen=True)
class Repair:
    microproject: str
    experiment_id: str
    tip_id: str
    source_id: str  # la version dont l'hypothèse est reprise
    source_date: str
    hypothesis: str


def find_repairs(data_dir: Path, only: str | None = None) -> list[Repair]:
    """Les pistes à réparer, dans l'ordre des µprojets puis des pistes."""
    import follow

    repairs: list[Repair] = []
    for follow_dir in sorted((data_dir / "microprojects").glob("*/follow")):
        slug = follow_dir.parent.name
        if only and slug != only:
            continue
        repo = follow.Repository(follow_dir)
        for experiment_id, tip_id in sorted(repo.branches.items()):
            history = repo.log(tip_id)  # de la pointe à la première version
            if (history[0].hypothesis or "").strip():
                continue
            source = next((version for version in history[1:] if (version.hypothesis or "").strip()), None)
            if source is not None:
                repairs.append(
                    Repair(slug, experiment_id, tip_id, source.id, source.created_at.date().isoformat(), source.hypothesis.strip())
                )
    return repairs


def apply(repair: Repair) -> str:
    """Reporte l'hypothèse sur une nouvelle version de la piste - renvoie son id."""
    from spectre.plugins.experiments import service

    def change(builder, parent):
        builder.hypothesis = repair.hypothesis

    return service.amend(repair.microproject, repair.experiment_id, author=AUTHOR, expected_version=repair.tip_id, change=change).id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", type=Path, default=None, help="Répertoire de données Spectre (défaut : SPECTRE_DATA_DIR ou ./data)")
    parser.add_argument("--microproject", default=None, help="Ne traiter que ce µprojet (son slug)")
    parser.add_argument("--apply", action="store_true", help="Écrire les réparations (sinon : à blanc)")
    args = parser.parse_args(argv)

    if args.data_dir is not None:
        os.environ["SPECTRE_DATA_DIR"] = str(args.data_dir)
    data_dir = Path(os.environ.get("SPECTRE_DATA_DIR", "./data")).resolve()
    os.environ["SPECTRE_DATA_DIR"] = str(data_dir)

    repairs = find_repairs(data_dir, args.microproject)
    print(f"Données : {data_dir}")
    print("Mode : écriture (--apply)" if args.apply else "Mode : à blanc - rien n'est écrit (--apply pour écrire)")
    if not repairs:
        print("Aucune hypothèse à restaurer.")
        return 0

    failures = 0
    for repair in repairs:
        print(f"\n{repair.microproject} / {repair.experiment_id}")
        print(f"  hypothèse de la version {repair.source_id} du {repair.source_date} :")
        print(f"  « {repair.hypothesis} »")
        if not args.apply:
            continue
        try:
            print(f"  -> restaurée sur la nouvelle version {apply(repair)}")
        except Exception as exc:  # noqa: BLE001 - une piste qui échoue n'arrête pas les autres
            failures += 1
            print(f"  -> ÉCHEC : {exc}")

    verb = "restaurée(s)" if args.apply else "à restaurer"
    print(f"\n{len(repairs) - failures} hypothèse(s) {verb}" + (f", {failures} échec(s)" if failures else "") + ".")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
