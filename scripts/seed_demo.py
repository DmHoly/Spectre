#!/usr/bin/env python3
"""Génère un compte de démonstration avec deux projets déjà remplis, comme si l'équipe utilisait
Spectre depuis un an : un projet "Gâteau au chocolat" (léger, pour montrer que le suivi
d'expérience marche sur n'importe quel procédé, pas seulement la microélectronique) et un projet
"Nanofils GaN" plus proche du métier réel (épitaxie, gravure, croissance sélective, retournement).

Tout passe par les vraies routes HTTP (via ``fastapi.testclient.TestClient``, comme les tests) -
c'est la seule façon d'obtenir des données garanties valides (mêmes vérifications que
l'application réelle). La seule chose que l'API ne permet pas de choisir est la date de création
d'une expérience (toujours "maintenant" - voir ``follow.storage.repository``) : ce script
recale donc ``created_at`` directement dans les fichiers JSON de Follow après coup
(``objects/<id>.json`` - la mise en page sur disque documentée dans ``follow.storage.backends``),
sans toucher à l'``id`` (qui est un hash du contenu, ``created_at`` explicitement exclu).

Usage :
    python scripts/seed_demo.py [--data-dir DATA_DIR]

Par défaut, écrit dans ``SPECTRE_DATA_DIR`` (ou ``./data`` si absent) - les mêmes données que
l'application lira au démarrage. Le script suppose un répertoire de données neuf (ou du moins
sans compte ``demo@spectre.local``/``lea@spectre.local``/``marc@spectre.local`` déjà enregistré) -
pour relancer une génération propre, pointez ``--data-dir`` vers un répertoire vide plutôt que de
réutiliser un répertoire déjà semé.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEMO_EMAIL = "demo@spectre.local"
DEMO_PASSWORD = "demo1234"
DEMO_NAME = "Compte démo"

TEAMMATES = [
    ("lea@spectre.local", "demo1234", "Léa Girard"),
    ("marc@spectre.local", "demo1234", "Marc Dubois"),
]

NOW = datetime.now(timezone.utc)
SCHEDULE: list[tuple[str, datetime]] = []  # (experiment_id, desired created_at) for the backdating pass
_jitter = random.Random(20240115)


def when(days_ago: float) -> datetime:
    """A backdated timestamp, with a small realistic jitter (business hours) so a whole beat's
    commits aren't all suspiciously stamped at the exact same second."""
    return NOW - timedelta(days=days_ago, hours=_jitter.uniform(0, 9), minutes=_jitter.uniform(0, 59))


def record(experiment_id: str, days_ago: float) -> str:
    SCHEDULE.append((experiment_id, when(days_ago)))
    return experiment_id


# --------------------------------------------------------------------------------------------
# Petites fabriques pour rester lisible - un dict par type d'étape, la même forme que
# structure-builder.js envoie (voir spectre/api/static/js/structure-builder/step-kinds.js).
# --------------------------------------------------------------------------------------------


def length(value: float, unit: str = "nm") -> dict:
    return {"value": value, "unit": unit}


def deposition(name, material, *, mode="conformal", angle_deg=0.0, thickness_nm, params=None, estimates=None):
    return {
        "kind": "deposition",
        "name": name,
        "material": material,
        "mode": mode,
        "angle_deg": angle_deg,
        "thickness": length(thickness_nm),
        "process_parameters": params or {},
        "derived_estimates": estimates or [],
    }


def etch(name, *, mode="directional", angle_deg=0.0, default_factor=1.0, selectivity=None, depth_nm):
    return {
        "kind": "etch",
        "name": name,
        "mode": mode,
        "angle_deg": angle_deg,
        "default_factor": default_factor,
        "selectivity_by_material": selectivity or {},
        "depth": length(depth_nm),
    }


def lithography(name, resist, *, thickness_nm, openings):
    return {"kind": "lithography", "name": name, "resist_material": resist, "thickness": length(thickness_nm), "openings": list(openings)}


def resist_strip(name, material="Photoresist"):
    return {"kind": "resist_strip", "name": name, "material": material}


def planarization_level(name, level_nm):
    return {"kind": "planarization", "name": name, "target_level": length(level_nm)}


def selective_growth(name, material, *, thickness_nm, rate_m, rate_sp):
    return {"kind": "selective_growth", "name": name, "material": material, "thickness": length(thickness_nm), "rate_m": rate_m, "rate_sp": rate_sp}


def flip(name="Retournement"):
    return {"kind": "flip", "name": name}


def substrate(material, *, width_nm, thickness_nm):
    return {"material": material, "domain_width": length(width_nm), "thickness": length(thickness_nm)}


def estimate(name, parameter, *, coefficient=1.0, offset=0.0, unit=None):
    return {"name": name, "parameter": parameter, "coefficient": coefficient, "offset": offset, "unit": unit}


def objective(name, metric, direction, *, target=None, rationale=None, verification_method=None):
    return {"name": name, "metric": metric, "direction": direction, "target": target, "rationale": rationale, "verification_method": verification_method}


def objres(objective_name, status, reasoning, observed=None):
    """One line of ``objective_results`` at conclude time - the actual answer to "was this
    objective met" for a given objective, referenced by name. ``inconclusive`` is used honestly
    here whenever a beat didn't carry a measurement bearing on that particular objective, rather
    than silently defaulting every objective to "met" alongside the beat's own headline metric."""
    return {"objective": objective_name, "status": status, "observed": observed, "reasoning": reasoning}


# --------------------------------------------------------------------------------------------
# Client HTTP - une session par compte (chacune garde ses propres cookies), toutes contre la
# même application/mêmes données sur disque.
# --------------------------------------------------------------------------------------------


class Session:
    def __init__(self, client, *, email, password, name=None):
        self.client = client
        self.email = email
        if name is not None:
            r = client.post("/api/auth/register", json={"email": email, "password": password, "name": name})
            if r.status_code != 201:
                raise RuntimeError(f"registration failed for {email}: {r.status_code} {r.text}")
        else:
            r = client.post("/api/auth/login", json={"email": email, "password": password})
            if r.status_code != 200:
                raise RuntimeError(f"login failed for {email}: {r.status_code} {r.text}")

    def post(self, path, **kw):
        r = self.client.post(path, **kw)
        if r.status_code >= 400:
            raise RuntimeError(f"POST {path} -> {r.status_code}: {r.text}")
        return r.json()

    def get(self, path, **kw):
        r = self.client.get(path, **kw)
        if r.status_code >= 400:
            raise RuntimeError(f"GET {path} -> {r.status_code}: {r.text}")
        return r.json()


class Project:
    """One project, driven by whichever Session currently 'owns' each call - keeps the beat
    functions below terse (``proj.launch(...)`` instead of repeating the slug/session juggling).
    """

    def __init__(self, slug: str):
        self.slug = slug

    def launch(self, session: Session, *, title, intent, hypothesis, substrate, steps, objectives, days_ago) -> str:
        result = session.post(
            f"/api/projects/{self.slug}/experiences",
            json={"substrate": substrate, "steps": steps, "title": title, "intent": intent, "hypothesis": hypothesis, "objectives": objectives},
        )
        return record(result["id"], days_ago)

    def evolve(self, session: Session, ref: str, *, title, intent, hypothesis, substrate, steps, objectives=None, new_branch=None, days_ago):
        result = session.post(
            f"/api/projects/{self.slug}/experiences/{ref}/evoluer",
            json={
                "substrate": substrate,
                "steps": steps,
                "title": title,
                "intent": intent,
                "hypothesis": hypothesis,
                "objectives": objectives or [],
                "new_branch": new_branch,
            },
        )
        return record(result["id"], days_ago)

    def campaign(self, session: Session, *, title, intent, substrate, steps, plan, days_ago) -> str:
        result = session.post(
            f"/api/projects/{self.slug}/experiences/campagne",
            json={"substrate": substrate, "steps": steps, "plan": plan, "title": title, "intent": intent, "objectives": []},
        )
        return record(result["id"], days_ago)

    def evidence(self, session: Session, ref: str, *, description, source, metric_name=None, metric_value=None, metric_unit=None, days_ago) -> str:
        result = session.post(
            f"/api/projects/{self.slug}/experiences/{ref}/preuves",
            json={"description": description, "source": source, "metric_name": metric_name, "metric_value": metric_value, "metric_unit": metric_unit},
        )
        return record(result["id"], days_ago)

    def conclude(self, session: Session, ref: str, *, status="concluded", decision=None, summary=None, next_steps=None, objective_results=None, days_ago) -> str:
        result = session.post(
            f"/api/projects/{self.slug}/experiences/{ref}/conclure",
            json={"status": status, "decision": decision, "summary": summary, "next_steps": next_steps, "objective_results": objective_results or []},
        )
        return record(result["id"], days_ago)

    def tag(self, session: Session, ref: str, tags: list[str], *, days_ago) -> str:
        result = session.post(f"/api/projects/{self.slug}/experiences/{ref}/etiquettes", json={"tags": tags})
        return record(result["id"], days_ago)

    def track(self, session: Session, ref: str, *, sample_id, location, days_ago) -> str:
        result = session.post(
            f"/api/projects/{self.slug}/experiences/{ref}/entites",
            json={"entities": [{"sample_id": sample_id, "location": location}]},
        )
        return record(result["id"], days_ago)

    def combine(self, session: Session, ref: str, *, other_id: str, title, intent, days_ago) -> str:
        """Merge two lines of work - keeps `ref`'s structure/steps as-is and links `other_id` in
        as a second parent (a real content merge, if wanted, is a normal evolve() right after -
        see the "Gâteau vegan et glaçage intense"/"Intégration du retournement" beats)."""
        result = session.post(
            f"/api/projects/{self.slug}/experiences/{ref}/combiner",
            json={"other_id": other_id, "title": title, "intent": intent},
        )
        return record(result["id"], days_ago)

    def save_structure(self, session: Session, *, name, substrate, steps, partagee=False, derived_from=None):
        session.post(
            f"/api/projects/{self.slug}/structures-sauvegardees",
            json={"name": name, "substrate": substrate, "steps": steps, "derived_from": derived_from, "partagee": partagee},
        )


# --------------------------------------------------------------------------------------------
# Projet 1 : Gâteau au chocolat
# --------------------------------------------------------------------------------------------


def build_cake_project(demo: Session, lea: Session, marc: Session) -> str:
    created = demo.post("/api/projects", json={"name": "Gâteau au chocolat", "description": "Mise au point de la recette maison - four, dosages, glaçage. Sert surtout à montrer que le suivi d'expérience marche sur n'importe quel procédé, pas seulement en salle blanche."})
    slug = created["slug"]
    for email, _password, _name in [(lea.email, None, None), (marc.email, None, None)]:
        demo.post(f"/api/projects/{slug}/members", json={"email": email, "role": "editor"})
    proj = Project(slug)

    cake_substrate = substrate("Sapphire", width_nm=200, thickness_nm=40)
    OBJ = [
        objective("Moelleux", "moelleux", "maximize", target=80, rationale="Un gâteau sec est immangeable.", verification_method="Test du cure-dent + dégustation"),
        objective("Temps de préparation", "temps_total_min", "minimize", target=70, rationale="Doit rester faisable un soir de semaine.", verification_method="Chronométrage du début à la sortie du four"),
        objective("Note de dégustation", "note_degustation", "maximize", target=8, rationale="Objectif : que toute la famille en reprenne.", verification_method="Vote à table sur 10"),
    ]

    def pate(temp, oeufs, farine_g, sucre_g, beurre_g, cuisson_min, temps_total, thickness_nm=220, extra_params=None):
        params = {"temperature_four_c": temp, "oeufs": oeufs, "farine_g": farine_g, "sucre_g": sucre_g, "beurre_g": beurre_g, "temps_cuisson_min": cuisson_min, "temps_total_min": temps_total}
        if extra_params:
            params.update(extra_params)
        return deposition(
            "Versement de la pâte", "Polyimide", thickness_nm=thickness_nm, params=params,
            estimates=[estimate("moelleux", "temperature_four_c", coefficient=-0.45, offset=149, unit="%")],
        )

    def glacage(cacao_pourcent, thickness_nm=25):
        return deposition(
            "Glaçage au chocolat noir", "BCB", thickness_nm=thickness_nm, params={"cacao_pourcent": cacao_pourcent},
            estimates=[estimate("intensite_gout", "cacao_pourcent", coefficient=0.07, offset=2, unit="/10")],
        )

    # 1. Recette de référence
    b1 = proj.launch(
        demo,
        title="Recette de référence - four à 180°C",
        intent="Avoir une recette de base fiable avant d'essayer d'améliorer quoi que ce soit.",
        hypothesis="Une recette classique à 180°C pendant 35 minutes devrait donner un résultat correct, même si perfectible.",
        substrate=cake_substrate,
        steps=[pate(180, 3, 250, 180, 120, 35, 60), glacage(70)],
        objectives=OBJ,
        days_ago=375,
    )
    b1 = proj.evidence(demo, b1, description="Bords un peu secs, centre encore humide - test du cure-dent limite.", source="Dégustation en famille", metric_name="moelleux", metric_value=64, metric_unit="%", days_ago=372)
    b1 = proj.conclude(
        demo, b1, decision="branch", summary="Bonne base, à ajuster sur la cuisson - trop sec sur les bords.",
        objective_results=[
            objres("Moelleux", "not_met", "64% de moelleux mesuré, loin de la cible de 80% - bords secs.", {"value": 64, "unit": "%"}),
            objres("Temps de préparation", "met", "60 minutes au total, sous la cible de 70."),
            objres("Note de dégustation", "inconclusive", "Pas encore de vote formalisé sur cette version."),
        ],
        days_ago=370,
    )
    b1 = proj.tag(demo, b1, ["recette-de-base"], days_ago=370)
    b1 = proj.track(demo, b1, sample_id="Gâteau-A1", location="Photos + carnet de recette, classeur cuisine", days_ago=370)

    # 2. Cuisson plus douce et plus longue
    b2 = proj.evolve(
        demo, b1,
        title="Cuisson plus douce et plus longue",
        intent="Réduire le dessèchement en surface en baissant la température et en allongeant la cuisson.",
        hypothesis="Une cuisson à 165°C pendant 45 minutes devrait limiter la formation d'une croûte sèche.",
        substrate=cake_substrate,
        steps=[pate(165, 3, 250, 180, 120, 45, 70), glacage(70)],
        days_ago=345,
    )
    b2 = proj.evidence(demo, b2, description="Nettement plus moelleux, bords encore acceptables.", source="Dégustation en famille", metric_name="moelleux", metric_value=73, metric_unit="%", days_ago=343)
    b2 = proj.conclude(
        demo, b2, decision="promote", summary="Amélioration nette, on garde cette base.",
        objective_results=[
            objres("Moelleux", "partially_met", "73% de moelleux, net progrès mais encore sous la cible de 80%."),
            objres("Temps de préparation", "met", "70 minutes au total, pile la cible."),
            objres("Note de dégustation", "inconclusive", "Pas encore de vote formalisé sur cette version."),
        ],
        days_ago=342,
    )
    b2 = proj.tag(demo, b2, ["recette-de-base", "approuvee"], days_ago=342)

    # 3. Un oeuf de plus (abandonné)
    b3 = proj.evolve(
        lea, b2,
        title="Un oeuf de plus pour plus de moelleux",
        intent="Tester si un oeuf supplémentaire améliore encore la texture.",
        hypothesis="Plus d'oeufs, plus de liant, donc une pâte plus moelleuse - au risque d'être plus dense.",
        substrate=cake_substrate,
        steps=[pate(165, 4, 250, 180, 120, 45, 70), glacage(70)],
        days_ago=320,
    )
    b3 = proj.evidence(lea, b3, description="Texture plus dense, presque un peu lourde.", source="Dégustation en famille", metric_name="note_degustation", metric_value=6.5, metric_unit="/10", days_ago=318)
    b3 = proj.conclude(
        lea, b3, status="abandoned", decision="abandon", summary="Trop dense, on revient à 3 oeufs.",
        objective_results=[
            objres("Moelleux", "inconclusive", "Texture jugée plus dense à l'oeil, pas de mesure formelle du moelleux sur cet essai."),
            objres("Temps de préparation", "inconclusive", "Pas de chronométrage réalisé pour cet essai."),
            objres("Note de dégustation", "not_met", "6.5/10, en dessous de la cible de 8 - trop dense."),
        ],
        days_ago=317,
    )
    proj.tag(lea, b3, ["a-eviter"], days_ago=317)

    # 4. Fork sans-gluten (abandonné pour l'instant)
    b4 = proj.evolve(
        marc, b2,
        title="Essai sans gluten (farine de riz)",
        intent="Proposer une version pour les convives intolérants au gluten.",
        hypothesis="Remplacer la farine de blé par de la farine de riz devrait fonctionner à proportions égales.",
        substrate=cake_substrate,
        steps=[pate(165, 3, 0, 180, 120, 45, 70, extra_params={"farine_riz_g": 250}), glacage(70)],
        new_branch="sans-gluten",
        days_ago=300,
    )
    b4 = proj.evidence(marc, b4, description="Texture plus friable, s'effrite un peu à la découpe.", source="Dégustation en famille", metric_name="moelleux", metric_value=58, metric_unit="%", days_ago=298)
    b4 = proj.conclude(
        marc, b4, status="abandoned", decision="inconclusive", summary="À retravailler - manque de liant.",
        objective_results=[
            objres("Moelleux", "not_met", "58%, nettement sous la cible - texture friable sans le gluten.", {"value": 58, "unit": "%"}),
            objres("Temps de préparation", "inconclusive", "Pas de chronométrage dédié pour cette variante."),
            objres("Note de dégustation", "inconclusive", "Pas de vote formalisé, la texture friable a fait hésiter les dégustateurs."),
        ],
        days_ago=297,
    )
    proj.tag(marc, b4, ["sans-gluten", "a-retravailler"], days_ago=297)

    # 5. Campagne four x glaçage
    campaign_steps = [pate(165, 3, 250, 180, 120, 45, 70), glacage(70)]
    b5 = proj.campaign(
        demo,
        title="Campagne four x glaçage - 6 échantillons",
        intent="Balayer systématiquement la cuisson et l'intensité du glaçage pour trouver le meilleur compromis.",
        substrate=cake_substrate,
        steps=campaign_steps,
        plan={"factors": [
            {"step_index": 0, "via_estimate": "moelleux", "values": [70, 80, 90]},
            {"step_index": 1, "via_estimate": "intensite_gout", "values": [6, 8]},
        ]},
        days_ago=280,
    )
    proj.tag(demo, b5, ["campagne"], days_ago=278)

    # 6. Adoption de la meilleure combinaison de la campagne
    b6 = proj.evolve(
        demo, b2,
        title="Adoption de la meilleure combinaison de la campagne",
        intent="Reprendre la combinaison température/glaçage qui a obtenu la meilleure note lors de la campagne.",
        hypothesis="Viser un moelleux à 85% et une intensité de glaçage à 7 devrait plaire au plus grand nombre.",
        substrate=cake_substrate,
        steps=[pate(160, 3, 250, 180, 120, 48, 75), glacage(78)],
        days_ago=260,
    )
    b6 = proj.evidence(demo, b6, description="Résultat très apprécié, meilleur jusqu'ici.", source="Dégustation en famille", metric_name="note_degustation", metric_value=8.7, metric_unit="/10", days_ago=258)
    b6 = proj.conclude(
        demo, b6, decision="promote", summary="Nouvelle recette de référence.",
        objective_results=[
            objres("Moelleux", "inconclusive", "Pas de mesure de moelleux dédiée sur ce run, mais aucun retour négatif sur la texture."),
            objres("Temps de préparation", "inconclusive", "Pas de chronométrage dédié pour cette combinaison."),
            objres("Note de dégustation", "met", "8.7/10, largement au-dessus de la cible de 8.", {"value": 8.7, "unit": "/10"}),
        ],
        days_ago=257,
    )
    b6 = proj.tag(demo, b6, ["recette-approuvee", "meilleure-recette"], days_ago=257)
    b6 = proj.track(demo, b6, sample_id="Gâteau-B2", location="Congélateur, tiroir du haut", days_ago=257)

    # 7. Fork vegan
    b7 = proj.evolve(
        lea, b6,
        title="Essai vegan (huile à la place du beurre et des oeufs)",
        intent="Proposer une alternative vegan pour un anniversaire.",
        hypothesis="Remplacer beurre et oeufs par de l'huile et de la compote devrait garder le moelleux.",
        substrate=cake_substrate,
        steps=[pate(160, 0, 250, 180, 0, 48, 75, extra_params={"huile_g": 90, "compote_g": 80}), glacage(78)],
        new_branch="vegan",
        days_ago=230,
    )
    b7 = proj.evidence(lea, b7, description="Bonne surprise, presque aussi moelleux que l'original.", source="Dégustation en famille", metric_name="moelleux", metric_value=79, metric_unit="%", days_ago=228)
    b7 = proj.conclude(
        lea, b7, decision="promote", summary="Bonne alternative, à garder pour les convives vegan.",
        objective_results=[
            objres("Moelleux", "partially_met", "79%, tout proche de la cible de 80% malgré l'absence de beurre et d'oeufs.", {"value": 79, "unit": "%"}),
            objres("Temps de préparation", "inconclusive", "Pas de chronométrage dédié pour cette variante."),
            objres("Note de dégustation", "inconclusive", "Pas de vote formalisé sur cette variante vegan."),
        ],
        days_ago=227,
    )
    b7 = proj.tag(lea, b7, ["vegan", "recette-approuvee"], days_ago=227)

    # 8. Glaçage plus intense
    b8 = proj.evolve(
        demo, b6,
        title="Glaçage plus intense (85% de cacao)",
        intent="Les retours demandent un goût de chocolat plus prononcé.",
        hypothesis="Passer à un chocolat à 85% de cacao devrait intensifier le goût sans assécher le glaçage.",
        substrate=cake_substrate,
        steps=[pate(160, 3, 250, 180, 120, 48, 75), glacage(85)],
        days_ago=200,
    )
    b8 = proj.evidence(demo, b8, description="Goût plus marqué, très apprécié des amateurs de chocolat noir.", source="Dégustation en famille", metric_name="note_degustation", metric_value=9.1, metric_unit="/10", days_ago=198)
    b8 = proj.conclude(
        demo, b8, decision="promote", summary="Adopté comme glaçage par défaut.",
        objective_results=[
            objres("Moelleux", "inconclusive", "Pas de nouvelle mesure de moelleux, seul le glaçage a changé."),
            objres("Temps de préparation", "inconclusive", "Pas de chronométrage dédié, temps de préparation inchangé par rapport à la base."),
            objres("Note de dégustation", "met", "9.1/10, la meilleure note obtenue jusqu'ici.", {"value": 9.1, "unit": "/10"}),
        ],
        days_ago=197,
    )
    b8 = proj.tag(demo, b8, ["recette-approuvee"], days_ago=197)

    # 8.5. Fusion : réunir la piste vegan (b7) et le glaçage intense (b8) dans une seule recette -
    # combine() ne fait que lier b7 comme second parent en gardant les étapes de b8 telles
    # quelles ; l'evolve() juste après applique la vraie combinaison des deux ajustements.
    b11 = proj.combine(
        demo, b8, other_id=b7,
        title="Gâteau vegan et glaçage intense",
        intent="Réunir la version vegan et le glaçage à 85% de cacao dans une seule recette.",
        days_ago=180,
    )
    b11 = proj.evolve(
        demo, b11,
        title="Gâteau vegan et glaçage intense",
        intent="Réunir la version vegan et le glaçage à 85% de cacao dans une seule recette.",
        hypothesis="Les deux ajustements (huile/compote et cacao à 85%) devraient bien se combiner sans interaction négative.",
        substrate=cake_substrate,
        steps=[pate(160, 0, 250, 180, 0, 48, 75, extra_params={"huile_g": 90, "compote_g": 80}), glacage(85)],
        days_ago=175,
    )
    b11 = proj.evidence(demo, b11, description="Combinaison réussie, aucun compromis nécessaire sur le goût ou la texture.", source="Dégustation en famille", metric_name="note_degustation", metric_value=8.9, metric_unit="/10", days_ago=173)
    b11 = proj.conclude(
        demo, b11, decision="promote", summary="Les deux pistes se combinent bien - recette vegan à glaçage intense adoptée.",
        objective_results=[
            objres("Moelleux", "partially_met", "79% de moelleux mesuré sur la piste vegan avant fusion, non re-testé avec le glaçage intense mais aucun retour négatif."),
            objres("Temps de préparation", "inconclusive", "Pas de chronométrage dédié pour la version combinée."),
            objres("Note de dégustation", "met", "8.9/10, largement au-dessus de la cible malgré la combinaison des deux ajustements.", {"value": 8.9, "unit": "/10"}),
        ],
        days_ago=171,
    )
    b11 = proj.tag(demo, b11, ["vegan", "recette-approuvee", "fusion"], days_ago=171)
    proj.track(demo, b11, sample_id="Gâteau-Vegan85-1", location="Congélateur, tiroir du haut", days_ago=171)

    # 9. Format familial
    b9 = proj.evolve(
        marc, b8,
        title="Format familial pour anniversaire (moule plus grand)",
        intent="Adapter la recette à un moule deux fois plus grand pour un anniversaire.",
        hypothesis="Il faudra allonger la cuisson pour compenser l'épaisseur, sans dépasser 55 minutes sous peine d'assécher les bords.",
        substrate=substrate("Sapphire", width_nm=320, thickness_nm=40),
        steps=[pate(160, 6, 500, 360, 240, 52, 85, thickness_nm=280), glacage(85, thickness_nm=35)],
        days_ago=150,
    )
    b9 = proj.evidence(marc, b9, description="Cuisson à coeur correcte, un peu long à préparer mais résultat à la hauteur.", source="Dégustation famille élargie", metric_name="temps_total_min", metric_value=88, metric_unit="min", days_ago=148)
    b9 = proj.conclude(
        marc, b9, decision="replicate", summary="Bon résultat pour les grandes tablées.",
        objective_results=[
            objres("Moelleux", "inconclusive", "Pas de mesure dédiée pour ce format, la cuisson à coeur a simplement été jugée correcte."),
            objres("Temps de préparation", "not_met", "88 minutes au total pour ce grand format, au-dessus de la cible de 70 - attendu vu la taille, mais à noter.", {"value": 88, "unit": "min"}),
            objres("Note de dégustation", "inconclusive", "Pas de vote chiffré, seulement un retour qualitatif positif."),
        ],
        days_ago=147,
    )
    b9 = proj.tag(marc, b9, ["format-familial", "recette-approuvee"], days_ago=147)
    proj.track(marc, b9, sample_id="Gâteau-Familial-1", location="Photos, dossier partagé famille", days_ago=147)

    # 10. Version finale documentée
    b10 = proj.evolve(
        demo, b8,
        title="Version finale documentée",
        intent="Figer la recette définitive avec toutes les quantités précises pour la partager à l'équipe.",
        hypothesis=None,
        substrate=cake_substrate,
        steps=[pate(160, 3, 250, 180, 120, 45, 72), glacage(85)],
        days_ago=40,
    )
    b10 = proj.evidence(demo, b10, description="Version testée trois fois de suite avec un résultat constant.", source="Dégustation en famille", metric_name="note_degustation", metric_value=9.3, metric_unit="/10", days_ago=38)
    b10 = proj.conclude(
        demo, b10, decision="promote",
        summary="Recette finale validée, prête à être partagée - un an d'essais pour arriver à cette version, moelleuse, avec un glaçage intense, faisable en semaine.",
        objective_results=[
            objres("Moelleux", "met", "Version testée trois fois avec un résultat moelleux constant, cohérent avec les 79-80% déjà mesurés sur cette base.", {"value": 80, "unit": "%"}),
            objres("Temps de préparation", "met", "45 minutes de cuisson, temps total sous la cible de 70 minutes.", {"value": 72, "unit": "min"}),
            objres("Note de dégustation", "met", "9.3/10, la meilleure note de l'année, confirmée sur trois essais consécutifs.", {"value": 9.3, "unit": "/10"}),
        ],
        days_ago=35,
    )
    b10 = proj.tag(demo, b10, ["recette-du-mois", "recette-approuvee", "version-finale"], days_ago=35)
    proj.track(demo, b10, sample_id="Gâteau-Final-1", location="Photos + recette imprimée, classeur cuisine", days_ago=35)

    proj.save_structure(demo, name="Gâteau au chocolat - recette finale", substrate=cake_substrate, steps=[pate(160, 3, 250, 180, 120, 45, 72), glacage(85)])

    return slug


# --------------------------------------------------------------------------------------------
# Projet 2 : Nanofils GaN sur saphir
# --------------------------------------------------------------------------------------------


def build_nanowire_project(demo: Session, lea: Session, marc: Session) -> str:
    created = demo.post("/api/projects", json={"name": "Nanofils GaN", "description": "Nanofils GaN à pointe semipolaire pour LED - épitaxie, gravure, croissance sélective, contact face arrière."})
    slug = created["slug"]
    for email in (lea.email, marc.email):
        demo.post(f"/api/projects/{slug}/members", json={"email": email, "role": "editor"})
    proj = Project(slug)

    domain_width = 300.0
    cx = domain_width / 2
    pillar_half_width = 30.0
    epi_substrate = lambda material="Sapphire": substrate(material, width_nm=domain_width, thickness_nm=20)

    OBJ = [
        objective("Rugosité de surface", "rugosite_rms_nm", "minimize", target=1.0, rationale="Une surface rugueuse dégrade la qualité de l'épitaxie suivante.", verification_method="Mesure AFM sur 5x5 µm"),
        objective("Diamètre de pointe", "diametre_pointe_nm", "minimize", target=15, rationale="Une pointe plus fine améliore le confinement optique visé.", verification_method="Mesure MEB en coupe"),
        objective("Longueur d'onde d'émission estimée", "longueur_onde_nm", "target", target=450, rationale="Cible : émission dans le bleu pour l'application LED.", verification_method="Calcul à partir de la composition d'indium, à confirmer en photoluminescence"),
        objective("Résistance de contact face arrière", "resistance_contact", "minimize", target=1.0, rationale="Une résistance de contact trop élevée limite le courant utile de la LED.", verification_method="Mesure 4 pointes après métallisation"),
    ]

    def epi_stack(aln_nm):
        return [
            deposition("Tampon AlN", "AlN", thickness_nm=aln_nm),
            deposition("Croissance GaN", "GaN", thickness_nm=60, params={"temperature_croissance_c": 1050, "pression_torr": 100}),
        ]

    litho_etch = [
        lithography("Masque des piliers", "Photoresist", thickness_nm=80, openings=[(0.0, cx - pillar_half_width), (cx + pillar_half_width, domain_width)]),
        etch("Gravure ICP Cl2 des piliers", mode="directional", angle_deg=0.0, selectivity={"GaN": 1.0, "AlGaN": 1.0, "InGaN": 1.0, "AlN": 1.0}, default_factor=0.05, depth_nm=60),
        resist_strip("Retrait du masque"),
    ]

    growth_taper = [
        selective_growth("Croissance sélective 1", "GaN", thickness_nm=10, rate_m=0.4, rate_sp=0.15),
        selective_growth("Croissance sélective 2", "GaN", thickness_nm=10, rate_m=0.4, rate_sp=0.15),
        selective_growth("Croissance sélective 3", "GaN", thickness_nm=8, rate_m=0.35, rate_sp=0.12),
    ]

    def active_region(indium_pourcent):
        return [
            deposition(
                "Puits quantique InGaN", "InGaN", thickness_nm=3, params={"indium_pourcent": indium_pourcent},
                estimates=[estimate("longueur_onde_nm", "indium_pourcent", coefficient=9.5, offset=280, unit="nm")],
            ),
            deposition("Capot GaN", "GaN", thickness_nm=8),
        ]

    ito_contact = [deposition("Contact ITO", "ITO", mode="directional", angle_deg=0.0, thickness_nm=15)]

    # 1. Épitaxie de référence
    b1 = proj.launch(
        demo,
        title="Épitaxie de référence AlN/GaN sur saphir",
        intent="Établir une épitaxie GaN de référence sur saphir avant d'aller plus loin.",
        hypothesis="Un tampon AlN de 10nm devrait suffire à amorcer une croissance GaN correcte, avec une rugosité autour de 1-1.5nm.",
        substrate=epi_substrate(), steps=epi_stack(10), objectives=OBJ, days_ago=350,
    )
    b1 = proj.evidence(demo, b1, description="Imagerie AFM : rugosité RMS mesurée à 1.2nm, quelques dislocations visibles.", source="AFM salle blanche", metric_name="rugosite_rms_nm", metric_value=1.2, metric_unit="nm", days_ago=347)
    b1 = proj.conclude(
        demo, b1, decision="branch", summary="Bon point de départ, tampon un peu fin.",
        objective_results=[
            objres("Rugosité de surface", "not_met", "1.2nm de rugosité RMS mesurée, au-dessus de la cible de 1.0nm.", {"value": 1.2, "unit": "nm"}),
            objres("Diamètre de pointe", "inconclusive", "Pas encore de piliers à ce stade, pas de pointe à mesurer."),
            objres("Longueur d'onde d'émission estimée", "inconclusive", "Zone active pas encore déposée."),
            objres("Résistance de contact face arrière", "inconclusive", "Contact face arrière pas encore abordé à ce stade."),
        ],
        days_ago=345,
    )
    b1 = proj.tag(demo, b1, ["epitaxie", "wafer-lot-A"], days_ago=345)
    b1 = proj.track(demo, b1, sample_id="W-A1", location="Boîte à wafers, salle blanche, tiroir 1", days_ago=345)

    # 2. Tampon AlN plus épais
    b2 = proj.evolve(
        lea, b1,
        title="Tampon AlN plus épais (15nm)",
        intent="Réduire la densité de dislocations en épaississant le tampon.",
        hypothesis="Un tampon AlN à 15nm devrait mieux filtrer les dislocations issues du désaccord de maille avec le saphir.",
        substrate=epi_substrate(), steps=epi_stack(15), days_ago=320,
    )
    b2 = proj.evidence(lea, b2, description="Rugosité RMS réduite à 0.6nm - nette amélioration.", source="AFM salle blanche", metric_name="rugosite_rms_nm", metric_value=0.6, metric_unit="nm", days_ago=318)
    b2 = proj.conclude(
        lea, b2, decision="promote", summary="Tampon 15nm adopté comme standard.",
        objective_results=[
            objres("Rugosité de surface", "met", "0.6nm de rugosité RMS, sous la cible de 1.0nm.", {"value": 0.6, "unit": "nm"}),
            objres("Diamètre de pointe", "inconclusive", "Pas encore de piliers définis."),
            objres("Longueur d'onde d'émission estimée", "inconclusive", "Zone active pas encore déposée."),
            objres("Résistance de contact face arrière", "inconclusive", "Pas encore abordé."),
        ],
        days_ago=317,
    )
    b2 = proj.tag(lea, b2, ["epitaxie", "recette-approuvee"], days_ago=317)

    # 3. Piliers par lithographie + gravure
    b3 = proj.evolve(
        demo, b2,
        title="Définition du réseau de piliers par lithographie + gravure ICP",
        intent="Passer d'un empilement plan à un réseau de piliers, première étape vers les nanofils.",
        hypothesis="Une gravure Cl2 ICP-RIE à travers un masque de résine devrait donner des piliers bien verticaux, sélectifs par rapport au masque.",
        substrate=epi_substrate(), steps=epi_stack(15) + litho_etch, days_ago=295,
    )
    b3 = proj.evidence(demo, b3, description="Piliers bien définis au MEB, flancs verticaux, diamètre proche de la cible.", source="MEB salle blanche", metric_name="diametre_pointe_nm", metric_value=60, metric_unit="nm", days_ago=293)
    b3 = proj.conclude(
        demo, b3, decision="promote", summary="Gravure validée pour la suite.",
        objective_results=[
            objres("Rugosité de surface", "inconclusive", "Pas de nouvelle mesure AFM après la gravure des piliers."),
            objres("Diamètre de pointe", "not_met", "60nm mesurés au sommet des piliers, loin de la cible de 15nm - attendu avant la croissance sélective.", {"value": 60, "unit": "nm"}),
            objres("Longueur d'onde d'émission estimée", "inconclusive", "Zone active pas encore déposée."),
            objres("Résistance de contact face arrière", "inconclusive", "Pas encore abordé."),
        ],
        days_ago=291,
    )
    b3 = proj.tag(demo, b3, ["gravure", "wafer-lot-A"], days_ago=291)

    # 4. Croissance sélective - pointe semipolaire
    b4 = proj.evolve(
        demo, b3,
        title="Croissance sélective - amorce de la pointe semipolaire",
        intent="Faire converger le sommet des piliers en pointe semipolaire par croissance sélective successive.",
        hypothesis="Une série de croissances sélectives avec un rapport C>M>SP suffisamment marqué devrait refermer le sommet en quelques étapes.",
        substrate=epi_substrate(), steps=epi_stack(15) + litho_etch + growth_taper, days_ago=270,
    )
    b4 = proj.evidence(demo, b4, description="Pointe bien refermée, diamètre résiduel mesuré au MEB.", source="MEB salle blanche", metric_name="diametre_pointe_nm", metric_value=18, metric_unit="nm", days_ago=268)
    b4 = proj.conclude(
        demo, b4, decision="promote", summary="Pointe semipolaire obtenue, proche de l'objectif.",
        objective_results=[
            objres("Rugosité de surface", "inconclusive", "Pas de nouvelle mesure AFM sur cette étape."),
            objres("Diamètre de pointe", "partially_met", "18nm résiduels, proche de la cible de 15nm après trois croissances sélectives successives.", {"value": 18, "unit": "nm"}),
            objres("Longueur d'onde d'émission estimée", "inconclusive", "Zone active pas encore déposée."),
            objres("Résistance de contact face arrière", "inconclusive", "Pas encore abordé."),
        ],
        days_ago=266,
    )
    b4 = proj.tag(demo, b4, ["croissance-selective", "wafer-lot-A"], days_ago=266)

    # 5. Fork substrat SiC
    b5 = proj.evolve(
        marc, b2,
        title="Essai sur substrat SiC",
        intent="Comparer la qualité d'épitaxie sur SiC, plus cher mais mieux accordé en maille que le saphir.",
        hypothesis="Le meilleur accord de maille SiC/GaN devrait donner une rugosité encore plus faible que sur saphir.",
        substrate=epi_substrate("SiC"), steps=epi_stack(15), new_branch="substrat-sic", days_ago=250,
    )
    b5 = proj.evidence(marc, b5, description="Rugosité RMS à 0.4nm, meilleure que sur saphir, mais coût du substrat très supérieur.", source="AFM salle blanche", metric_name="rugosite_rms_nm", metric_value=0.4, metric_unit="nm", days_ago=248)
    b5 = proj.conclude(
        marc, b5, decision="inconclusive", summary="Qualité supérieure confirmée, réservé aux lots critiques vu le coût.",
        objective_results=[
            objres("Rugosité de surface", "met", "0.4nm sur SiC, meilleure valeur obtenue jusqu'ici, mais coût du substrat très supérieur - réservé aux lots critiques.", {"value": 0.4, "unit": "nm"}),
            objres("Diamètre de pointe", "inconclusive", "Pas de piliers gravés sur cet essai, comparaison limitée au tampon."),
            objres("Longueur d'onde d'émission estimée", "inconclusive", "Zone active pas abordée sur cette variante."),
            objres("Résistance de contact face arrière", "inconclusive", "Pas abordé."),
        ],
        days_ago=247,
    )
    proj.tag(marc, b5, ["substrat-sic", "a-verifier"], days_ago=247)

    # 6. Zone active InGaN/GaN
    b6 = proj.evolve(
        demo, b4,
        title="Puits quantique InGaN + capot GaN",
        intent="Ajouter la zone active (puits quantique InGaN) sur la pointe semipolaire pour viser l'émission bleue.",
        hypothesis="Un puits InGaN de 3nm avec une composition d'indium modérée devrait viser une émission autour de 450nm.",
        substrate=epi_substrate(), steps=epi_stack(15) + litho_etch + growth_taper + active_region(18), days_ago=230,
    )
    b6 = proj.evidence(demo, b6, description="Composition d'indium confirmée par EDX à 17-19%, cohérent avec la cible.", source="EDX salle blanche", metric_name="longueur_onde_nm", metric_value=451, metric_unit="nm", days_ago=228)
    b6 = proj.conclude(
        demo, b6, decision="branch", summary="Zone active en place, à caractériser en photoluminescence.",
        objective_results=[
            objres("Rugosité de surface", "inconclusive", "Pas de nouvelle mesure AFM après le dépôt de la zone active."),
            objres("Diamètre de pointe", "inconclusive", "Pas de nouvelle mesure MEB à cette étape, pointe déjà validée précédemment."),
            objres("Longueur d'onde d'émission estimée", "met", "451nm estimé par EDX à partir de la composition d'indium, quasiment pile sur la cible de 450nm - à confirmer en photoluminescence.", {"value": 451, "unit": "nm"}),
            objres("Résistance de contact face arrière", "inconclusive", "Contact face arrière pas encore abordé."),
        ],
        days_ago=226,
    )
    b6 = proj.tag(demo, b6, ["zone-active", "wafer-lot-B"], days_ago=226)
    b6 = proj.track(demo, b6, sample_id="W-B1", location="Boîte à wafers, salle blanche, tiroir 2", days_ago=226)

    # 7. Contact ITO
    b7 = proj.evolve(
        lea, b6,
        title="Contact ITO en face avant",
        intent="Ajouter un contact transparent pour l'injection électrique tout en laissant passer la lumière.",
        hypothesis="Un dépôt directionnel d'ITO de 15nm devrait offrir un bon compromis conduction/transparence.",
        substrate=epi_substrate(), steps=epi_stack(15) + litho_etch + growth_taper + active_region(18) + ito_contact, days_ago=210,
    )
    b7 = proj.evidence(lea, b7, description="Contact continu observé au MEB, pas de zones découvertes.", source="MEB salle blanche", days_ago=208)
    b7 = proj.conclude(
        lea, b7, decision="promote", summary="Contact avant validé.",
        objective_results=[
            objres("Rugosité de surface", "inconclusive", "Pas de nouvelle mesure AFM après le dépôt du contact."),
            objres("Diamètre de pointe", "inconclusive", "Pas de nouvelle mesure MEB dédiée à la pointe sur cette étape."),
            objres("Longueur d'onde d'émission estimée", "inconclusive", "Pas de nouvelle mesure optique, contact avant seulement."),
            objres("Résistance de contact face arrière", "inconclusive", "Contact avant validé visuellement, mais la résistance de contact face arrière reste à valider (voir le wafer test dédié)."),
        ],
        days_ago=206,
    )
    b7 = proj.tag(lea, b7, ["contact", "wafer-lot-B"], days_ago=206)

    # 8. Campagne composition du puits quantique
    campaign_steps = epi_stack(15) + litho_etch + growth_taper + active_region(18) + ito_contact
    indium_step_index = campaign_steps.index(next(s for s in campaign_steps if s["name"] == "Puits quantique InGaN"))
    b8 = proj.campaign(
        demo,
        title="Campagne composition du puits quantique - 4 échantillons",
        intent="Balayer la composition d'indium pour cartographier la longueur d'onde d'émission visée.",
        substrate=epi_substrate(), steps=campaign_steps,
        plan={"factors": [{"step_index": indium_step_index, "via_estimate": "longueur_onde_nm", "values": [430, 450, 470, 490]}]},
        days_ago=190,
    )
    proj.tag(demo, b8, ["campagne", "zone-active"], days_ago=188)

    # 9. Ajustement composition suite à la campagne
    b9 = proj.evolve(
        demo, b7,
        title="Ajustement composition suite à la campagne (cible 450nm)",
        intent="Reprendre la composition d'indium qui vise le plus précisément 450nm d'après la campagne.",
        hypothesis="Une composition d'indium à 18.5% doit centrer l'émission sur 450nm.",
        substrate=epi_substrate(), steps=epi_stack(15) + litho_etch + growth_taper + active_region(18.5) + ito_contact, days_ago=160,
    )
    b9 = proj.evidence(demo, b9, description="Wafer marqué comme référence pour la suite du projet.", source="Suivi de lot", days_ago=158)
    b9 = proj.conclude(
        demo, b9, decision="promote", summary="Nouvelle référence de composition.",
        objective_results=[
            objres("Rugosité de surface", "inconclusive", "Pas de nouvelle mesure AFM, épitaxie inchangée depuis le lot précédent."),
            objres("Diamètre de pointe", "inconclusive", "Pas de nouvelle mesure MEB, géométrie de pointe inchangée."),
            objres("Longueur d'onde d'émission estimée", "partially_met", "Composition ajustée à 18.5% d'après la campagne pour viser 450nm, mesure de confirmation en photoluminescence pas encore réalisée."),
            objres("Résistance de contact face arrière", "inconclusive", "Pas encore abordé sur ce wafer."),
        ],
        days_ago=156,
    )
    b9 = proj.tag(demo, b9, ["recette-approuvee", "wafer-lot-C"], days_ago=156)
    proj.track(demo, b9, sample_id="W-C1", location="Boîte à wafers, salle blanche, tiroir 3", days_ago=156)

    # 10. Wafer test - validation du retournement pour contact face arrière (procédé
    # indépendant, validé sur un wafer test Si avant d'être appliqué à la ligne active GaN -
    # reprend exactement les valeurs de structureforge/examples/flip_backside_via.py, déjà
    # vérifiées).
    via_cx = 150.0
    flip_steps = [
        deposition("GaN (dispositif)", "GaN", thickness_nm=40),
        lithography("Masque du plot de contact", "Photoresist", thickness_nm=60, openings=[(via_cx - 50.0, via_cx + 50.0)]),
        deposition("Métal de contact (Au)", "Au", mode="directional", angle_deg=0.0, thickness_nm=30),
        resist_strip("Retrait résine"),
        deposition("Oxyde de scellement", "SiO2", thickness_nm=80),
        planarization_level("CMP de scellement", 110),
        flip("Retournement pour la face arrière"),
        etch("Amincissement de la face arrière", mode="isotropic", depth_nm=120),
        lithography("Masque du via", "Photoresist", thickness_nm=40, openings=[(via_cx - 15.0, via_cx + 15.0)]),
        etch("Gravure du via (traverse jusqu'au plot)", mode="directional", angle_deg=0.0, selectivity={"Photoresist": 0.1, "Au": 0.05}, depth_nm=75),
        resist_strip("Retrait résine"),
        deposition("Métal de la face arrière (Cu)", "Cu", mode="directional", angle_deg=0.0, thickness_nm=15),
    ]
    b10 = proj.launch(
        demo,
        title="Wafer test Si - validation du retournement pour contact face arrière",
        intent="Valider le procédé de retournement et de via traversant sur un wafer test Si, moins coûteux, avant de l'appliquer à la ligne GaN sur saphir.",
        hypothesis="Un amincissement à 120nm puis une gravure de via à 75nm devraient traverser le substrat aminci et atteindre le plot de contact enterré.",
        substrate=substrate("Si", width_nm=300, thickness_nm=150), steps=flip_steps, objectives=OBJ, days_ago=90,
    )
    b10 = proj.evidence(demo, b10, description="Contact mesuré continu entre le plot avant et le métal arrière (distance quasi nulle au MEB) - procédé validé.", source="MEB en coupe", metric_name="resistance_contact", metric_value=0.8, metric_unit="Ω·mm²", days_ago=87)
    b10 = proj.conclude(
        demo, b10, decision="promote", summary="Procédé de retournement validé, prêt à être appliqué à la ligne GaN.",
        objective_results=[
            objres("Rugosité de surface", "inconclusive", "Wafer test Si, sans rapport avec la rugosité d'épitaxie GaN suivie sur les autres lots."),
            objres("Diamètre de pointe", "inconclusive", "Wafer test plan, pas de nanofils sur cet essai."),
            objres("Longueur d'onde d'émission estimée", "inconclusive", "Wafer test sans zone active, objectif non applicable ici."),
            objres("Résistance de contact face arrière", "met", "0.8Ω·mm² mesuré, sous la cible de 1.0 - contact continu confirmé au MEB en coupe.", {"value": 0.8, "unit": "Ω·mm²"}),
        ],
        days_ago=85,
    )
    b10 = proj.tag(demo, b10, ["retournement", "design-valide", "wafer-test"], days_ago=85)
    b10 = proj.track(demo, b10, sample_id="Si-Test-1", location="Boîte à wafers, salle blanche, tiroir test", days_ago=85)

    # 11. Fusion : relier la ligne principale (b9) et la validation du retournement (b10) - deux
    # pistes indépendantes qui convergent. combine() garde les étapes de b9 telles quelles (pas
    # de nouvelle simulation risquée : le retournement a été validé sur une géométrie plane,
    # pas sur la pointe semipolaire) ; l'application réelle du retournement à un wafer GaN
    # complet est notée en next_steps plutôt que simulée ici.
    b11 = proj.combine(
        demo, b9, other_id=b10,
        title="Intégration du retournement validé dans la ligne principale",
        intent="Documenter que le procédé de retournement/contact face arrière, validé sur wafer test, est prêt à être appliqué à un wafer GaN réel de la ligne principale.",
        days_ago=70,
    )
    b11 = proj.evidence(demo, b11, description="Les deux pistes de travail (épitaxie/nanofils et validation du retournement) sont désormais reliées dans l'historique du projet.", source="Revue de projet", days_ago=68)
    b11 = proj.conclude(
        demo, b11, decision="branch",
        summary="Fusion des deux pistes de travail - le retournement est prêt pour le prochain lot GaN.",
        next_steps="Appliquer le retournement/via à un wafer GaN complet (épitaxie + nanofils + retournement) lors du prochain run.",
        objective_results=[
            objres("Rugosité de surface", "inconclusive", "Pas de nouvelle mesure, cette étape documente la fusion des deux pistes plutôt qu'un nouveau run."),
            objres("Diamètre de pointe", "inconclusive", "Pas de nouvelle mesure, géométrie de pointe inchangée depuis le lot C."),
            objres("Longueur d'onde d'émission estimée", "partially_met", "Composition à 18.5% conservée de la ligne principale, viser 450nm reste à confirmer en photoluminescence."),
            objres("Résistance de contact face arrière", "met", "Procédé de retournement validé à 0.8Ω·mm² sur wafer test, prêt à être appliqué au prochain lot GaN complet.", {"value": 0.8, "unit": "Ω·mm²"}),
        ],
        days_ago=65,
    )
    b11 = proj.tag(demo, b11, ["fusion", "wafer-lot-C"], days_ago=65)
    proj.track(demo, b11, sample_id="W-C1", location="Boîte à wafers, salle blanche, tiroir 3", days_ago=65)

    proj.save_structure(demo, name="Nanofil LED semipolaire - référence", substrate=epi_substrate(), steps=epi_stack(15) + litho_etch + growth_taper + active_region(18.5) + ito_contact)

    return slug


# --------------------------------------------------------------------------------------------
# Recalage des dates + orchestration
# --------------------------------------------------------------------------------------------


def backdate_experiments(data_dir: Path, slugs: list[str]) -> None:
    """Rewrite ``created_at`` directly on Follow's on-disk objects (see the module docstring for
    why this is safe: ``created_at`` is explicitly excluded from the content-addressed ``id``).
    """
    by_id = dict(SCHEDULE)
    for slug in slugs:
        objects_dir = data_dir / "projects" / slug / "follow" / "objects"
        if not objects_dir.exists():
            continue
        for file in objects_dir.glob("*.json"):
            data = json.loads(file.read_text(encoding="utf-8"))
            desired = by_id.get(data["id"])
            if desired is None:
                continue
            data["created_at"] = desired.isoformat()
            file.write_text(json.dumps(data, indent=2), encoding="utf-8")


def backdate_projects(data_dir: Path, slugs: list[str], days_ago: float) -> None:
    import sqlite3

    db_path = data_dir / "spectre.db"
    if not db_path.exists():
        return
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            f"UPDATE projects SET created_at = ? WHERE slug IN ({','.join('?' * len(slugs))})",
            [when(days_ago).isoformat(), *slugs],
        )
        conn.commit()
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", type=Path, default=None, help="Répertoire de données Spectre (défaut : SPECTRE_DATA_DIR ou ./data)")
    args = parser.parse_args()

    if args.data_dir is not None:
        os.environ["SPECTRE_DATA_DIR"] = str(args.data_dir)
    data_dir = Path(os.environ.get("SPECTRE_DATA_DIR", "./data")).resolve()
    os.environ["SPECTRE_DATA_DIR"] = str(data_dir)

    from fastapi.testclient import TestClient

    from spectre.api.app import create_app

    app = create_app()

    with TestClient(app) as client_demo, TestClient(app) as client_lea, TestClient(app) as client_marc:
        demo = Session(client_demo, email=DEMO_EMAIL, password=DEMO_PASSWORD, name=DEMO_NAME)
        lea = Session(client_lea, email=TEAMMATES[0][0], password=TEAMMATES[0][1], name=TEAMMATES[0][2])
        marc = Session(client_marc, email=TEAMMATES[1][0], password=TEAMMATES[1][1], name=TEAMMATES[1][2])

        print("Génération du projet « Gâteau au chocolat »...")
        cake_slug = build_cake_project(demo, lea, marc)
        print("Génération du projet « Nanofils GaN »...")
        nano_slug = build_nanowire_project(demo, lea, marc)

    print("Recalage des dates sur environ un an d'historique...")
    backdate_experiments(data_dir, [cake_slug, nano_slug])
    backdate_projects(data_dir, [cake_slug, nano_slug], days_ago=380)

    print(
        f"\nCompte de démo prêt :\n"
        f"  e-mail    : {DEMO_EMAIL}\n"
        f"  mot de passe : {DEMO_PASSWORD}\n"
        f"  projets   : {cake_slug}, {nano_slug}\n"
        f"  {len(SCHEDULE)} versions d'expérience générées au total.\n"
    )


if __name__ == "__main__":
    sys.exit(main())
