#!/usr/bin/env python3
"""Génère un compte de démonstration avec deux projets déjà remplis, comme si l'équipe utilisait
Spectre depuis un an - tous les deux sur des nanofils GaN épitaxiés pour LED, afin de rester dans
un seul domaine métier plutôt que d'en mélanger un fictif (l'ancienne version semait aussi une
recette de gâteau) :

- **Nanofils GaN - puits quantique simple** : l'épitaxie de référence jusqu'à une LED bleue à un
  seul puits quantique, avec un changement de substrat de base (saphir -> SiC, comparé puis
  recombiné avec la ligne principale) et une déclinaison rouge/vert/bleu du taux d'indium de la
  zone active.
- **Nanofils GaN - puits quantiques multiples (MQW)** - projet séparé : la même base épitaxiale,
  mais avec plusieurs puits quantiques, une comparaison avec/sans couche bloqueuse d'électrons
  (EBL), puis un réglage fin du dopage P en aval.

Les deux profitent des refs (:mod:`spectre.core.refs`) pour marquer les points de départ vraiment
réutilisés plusieurs fois (l'épitaxie standard, la référence à puits simple, la référence
MQW+EBL...) plutôt que de laisser cette notion complètement absente de la démo.

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


def deposition(name, material, *, recipe="CVD Conformal", thickness_nm):
    return {"kind": "deposition", "name": name, "material": material, "recipe": recipe, "thickness": length(thickness_nm)}


def etch(name, *, recipe="Anisotropic RIE", depth_nm):
    return {"kind": "etch", "name": name, "recipe": recipe, "depth": length(depth_nm)}


def lithography(name, resist, *, thickness_nm, openings):
    return {"kind": "lithography", "name": name, "resist_material": resist, "thickness": length(thickness_nm), "openings": list(openings)}


def resist_strip(name, material="Photoresist"):
    return {"kind": "resist_strip", "name": name, "material": material}


def faceted_growth(name, material, *, thickness_nm, rate_m, rate_sp, rate_c=1.0, semi_polar_angle_deg=30.0, seed_materials=None):
    return {
        "kind": "faceted_growth",
        "name": name,
        "material": material,
        "thickness": length(thickness_nm),
        "rate_c": rate_c,
        "rate_m": rate_m,
        "rate_sp": rate_sp,
        "semi_polar_angle_deg": semi_polar_angle_deg,
        "seed_materials": seed_materials or [],
    }


def substrate(material, *, width_nm, thickness_nm):
    return {"material": material, "domain_width": length(width_nm), "thickness": length(thickness_nm)}


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

    def launch(self, session: Session, *, title, intent, hypothesis, substrate, steps, objectives, sample_id, location=None, days_ago) -> str:
        # every experience needs a physical entity from the moment it's created (spectre.api.structures
        # enforces this) - passed straight through rather than tracked as an afterthought.
        result = session.post(
            f"/api/projects/{self.slug}/experiences",
            json={
                "substrate": substrate,
                "steps": steps,
                "title": title,
                "intent": intent,
                "hypothesis": hypothesis,
                "objectives": objectives,
                "entities": [{"sample_id": sample_id, "location": location}],
            },
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
        see the "LED complète sur substrat SiC" beat)."""
        result = session.post(
            f"/api/projects/{self.slug}/experiences/{ref}/combiner",
            json={"other_id": other_id, "title": title, "intent": intent},
        )
        return record(result["id"], days_ago)

    def make_ref(self, session: Session, ref: str, *, name: str | None = None) -> str:
        """Tag ``ref`` as a ref (:mod:`spectre.core.refs`) - unlike every other beat here, this
        doesn't create a new commit (a ref is just a name on an experience that already exists),
        so there's nothing to schedule for backdating."""
        result = session.post(f"/api/projects/{self.slug}/experiences/{ref}/ref", json={"name": name})
        return result["name"]

    def save_structure(self, session: Session, *, name, substrate, steps, partagee=False, derived_from=None):
        session.post(
            f"/api/projects/{self.slug}/structures-sauvegardees",
            json={"name": name, "substrate": substrate, "steps": steps, "derived_from": derived_from, "partagee": partagee},
        )


# --------------------------------------------------------------------------------------------
# Empilement épitaxial partagé par les deux projets : tampon AlN, croissance GaN, piliers par
# lithographie/gravure, puis pointe semipolaire par croissance sélective - la même base que
# chaque projet part construire avant de diverger sur sa propre zone active.
# --------------------------------------------------------------------------------------------

DOMAIN_WIDTH = 300.0
_CX = DOMAIN_WIDTH / 2
_PILLAR_HALF_WIDTH = 30.0


def epi_substrate(material="Sapphire"):
    return substrate(material, width_nm=DOMAIN_WIDTH, thickness_nm=20)


def epi_stack(aln_nm):
    return [
        deposition("Tampon AlN", "AlN", recipe="MOCVD Epitaxial", thickness_nm=aln_nm),
        deposition("Croissance GaN", "GaN", recipe="MOCVD Epitaxial", thickness_nm=60),
    ]


LITHO_ETCH = [
    lithography("Masque des piliers", "Photoresist", thickness_nm=80, openings=[(0.0, _CX - _PILLAR_HALF_WIDTH), (_CX + _PILLAR_HALF_WIDTH, DOMAIN_WIDTH)]),
    etch("Gravure ICP Cl2 des piliers", recipe="Cl2 ICP-RIE (III-N)", depth_nm=60),
    resist_strip("Retrait du masque"),
]

GROWTH_TAPER = [
    faceted_growth("Croissance facettée 1", "GaN", thickness_nm=10, rate_m=0.4, rate_sp=0.15, seed_materials=["GaN"]),
    faceted_growth("Croissance facettée 2", "GaN", thickness_nm=10, rate_m=0.4, rate_sp=0.15, seed_materials=["GaN"]),
    faceted_growth("Croissance facettée 3", "GaN", thickness_nm=8, rate_m=0.35, rate_sp=0.12, seed_materials=["GaN"]),
]


# --------------------------------------------------------------------------------------------
# Projet 1 : Nanofils GaN - puits quantique simple
# --------------------------------------------------------------------------------------------


def build_single_qw_project(demo: Session, lea: Session, marc: Session) -> str:
    created = demo.post(
        "/api/projects",
        json={
            "name": "Nanofils GaN - puits quantique simple",
            "description": "Nanofils GaN à pointe semipolaire pour LED bleue - épitaxie, gravure, croissance sélective, un seul puits quantique, avec un changement de substrat de base et une déclinaison rouge/vert/bleu du taux d'indium.",
        },
    )
    slug = created["slug"]
    for email in (lea.email, marc.email):
        demo.post(f"/api/projects/{slug}/members", json={"email": email, "role": "editor"})
    proj = Project(slug)

    OBJ = [
        objective("Rugosité de surface", "rugosite_rms_nm", "minimize", target=1.0, rationale="Une surface rugueuse dégrade la qualité de l'épitaxie suivante.", verification_method="Mesure AFM sur 5x5 µm"),
        objective("Diamètre de pointe", "diametre_pointe_nm", "minimize", target=15, rationale="Une pointe plus fine améliore le confinement optique visé.", verification_method="Mesure MEB en coupe"),
        objective("Longueur d'onde d'émission estimée", "longueur_onde_nm", "target", target=450, rationale="Cible : émission dans le bleu pour l'application LED.", verification_method="Photoluminescence, recoupée avec la composition d'indium mesurée en EDX"),
    ]

    def active_region_single(indium_pourcent):
        # indium_pourcent ne pilote pas l'étape simulée (pas de champ de composition sur
        # Deposition dans StructureForge) - gardé en argument pour documenter chaque essai, la
        # longueur d'onde visée reste suivie comme objectif/preuve, pas comme grandeur calculée.
        return [
            deposition("Puits quantique InGaN", "InGaN", recipe="MOCVD Epitaxial", thickness_nm=3),
            deposition("Capot GaN", "GaN", recipe="MOCVD Epitaxial", thickness_nm=8),
        ]

    ito_contact = [deposition("Contact ITO", "ITO", recipe="Sputter Metal (normal)", thickness_nm=15)]

    # 1. Épitaxie de référence
    b1 = proj.launch(
        demo,
        title="Épitaxie de référence AlN/GaN sur saphir",
        intent="Établir une épitaxie GaN de référence sur saphir avant d'aller plus loin.",
        hypothesis="Un tampon AlN de 10nm devrait suffire à amorcer une croissance GaN correcte, avec une rugosité autour de 1-1.5nm.",
        substrate=epi_substrate(), steps=epi_stack(10), objectives=OBJ,
        sample_id="W-A1", location="Boîte à wafers, salle blanche, tiroir 1",
        days_ago=340,
    )
    b1 = proj.evidence(demo, b1, description="Imagerie AFM : rugosité RMS mesurée à 1.2nm, quelques dislocations visibles.", source="AFM salle blanche", metric_name="rugosite_rms_nm", metric_value=1.2, metric_unit="nm", days_ago=337)
    b1 = proj.conclude(
        demo, b1, decision="branch", summary="Bon point de départ, tampon un peu fin.",
        objective_results=[
            objres("Rugosité de surface", "not_met", "1.2nm de rugosité RMS mesurée, au-dessus de la cible de 1.0nm.", {"value": 1.2, "unit": "nm"}),
            objres("Diamètre de pointe", "inconclusive", "Pas encore de piliers à ce stade, pas de pointe à mesurer."),
            objres("Longueur d'onde d'émission estimée", "inconclusive", "Zone active pas encore déposée."),
        ],
        days_ago=335,
    )
    b1 = proj.tag(demo, b1, ["epitaxie", "wafer-lot-A"], days_ago=335)
    b1 = proj.track(demo, b1, sample_id="W-A1", location="Boîte à wafers, salle blanche, tiroir 1", days_ago=335)

    # 2. Tampon AlN plus épais - devient la ref "epitaxie-standard", réutilisée deux fois plus
    # bas (continuation vers les piliers, et fork substrat SiC).
    b2 = proj.evolve(
        demo, b1,
        title="Tampon AlN plus épais (15nm)",
        intent="Réduire la densité de dislocations en épaississant le tampon.",
        hypothesis="Un tampon AlN à 15nm devrait mieux filtrer les dislocations issues du désaccord de maille avec le saphir.",
        substrate=epi_substrate(), steps=epi_stack(15), days_ago=315,
    )
    b2 = proj.evidence(demo, b2, description="Rugosité RMS réduite à 0.6nm - nette amélioration.", source="AFM salle blanche", metric_name="rugosite_rms_nm", metric_value=0.6, metric_unit="nm", days_ago=313)
    b2 = proj.conclude(
        demo, b2, decision="promote", summary="Tampon 15nm adopté comme standard.",
        objective_results=[
            objres("Rugosité de surface", "met", "0.6nm de rugosité RMS, sous la cible de 1.0nm.", {"value": 0.6, "unit": "nm"}),
            objres("Diamètre de pointe", "inconclusive", "Pas encore de piliers définis."),
            objres("Longueur d'onde d'émission estimée", "inconclusive", "Zone active pas encore déposée."),
        ],
        days_ago=312,
    )
    b2 = proj.tag(demo, b2, ["epitaxie", "recette-approuvee"], days_ago=312)
    proj.make_ref(demo, b2, name="epitaxie-standard")

    # 3. Fork substrat SiC - changement de base wafer, comparé à l'épitaxie standard sur saphir.
    b5 = proj.evolve(
        marc, b2,
        title="Essai sur substrat SiC",
        intent="Comparer la qualité d'épitaxie sur SiC, plus cher mais mieux accordé en maille que le saphir.",
        hypothesis="Le meilleur accord de maille SiC/GaN devrait donner une rugosité encore plus faible que sur saphir.",
        substrate=epi_substrate("SiC"), steps=epi_stack(15), new_branch="substrat-sic", days_ago=290,
    )
    b5 = proj.evidence(marc, b5, description="Rugosité RMS à 0.4nm, meilleure que sur saphir, mais coût du substrat très supérieur.", source="AFM salle blanche", metric_name="rugosite_rms_nm", metric_value=0.4, metric_unit="nm", days_ago=288)
    b5 = proj.conclude(
        marc, b5, decision="inconclusive", summary="Qualité supérieure confirmée, réservé aux lots critiques vu le coût.",
        objective_results=[
            objres("Rugosité de surface", "met", "0.4nm sur SiC, meilleure valeur obtenue jusqu'ici, mais coût du substrat très supérieur - réservé aux lots critiques.", {"value": 0.4, "unit": "nm"}),
            objres("Diamètre de pointe", "inconclusive", "Pas de piliers gravés sur cet essai, comparaison limitée au tampon."),
            objres("Longueur d'onde d'émission estimée", "inconclusive", "Zone active pas abordée sur cette variante."),
        ],
        days_ago=287,
    )
    b5 = proj.tag(marc, b5, ["substrat-sic", "a-verifier"], days_ago=287)

    # 4. Piliers par lithographie + gravure (continuation de la ligne principale, depuis la ref)
    b3 = proj.evolve(
        demo, b2,
        title="Définition du réseau de piliers par lithographie + gravure ICP",
        intent="Passer d'un empilement plan à un réseau de piliers, première étape vers les nanofils.",
        hypothesis="Une gravure Cl2 ICP-RIE à travers un masque de résine devrait donner des piliers bien verticaux, sélectifs par rapport au masque.",
        substrate=epi_substrate(), steps=epi_stack(15) + LITHO_ETCH, days_ago=270,
    )
    b3 = proj.evidence(demo, b3, description="Piliers bien définis au MEB, flancs verticaux, diamètre proche de la cible.", source="MEB salle blanche", metric_name="diametre_pointe_nm", metric_value=60, metric_unit="nm", days_ago=268)
    b3 = proj.conclude(
        demo, b3, decision="promote", summary="Gravure validée pour la suite.",
        objective_results=[
            objres("Rugosité de surface", "inconclusive", "Pas de nouvelle mesure AFM après la gravure des piliers."),
            objres("Diamètre de pointe", "not_met", "60nm mesurés au sommet des piliers, loin de la cible de 15nm - attendu avant la croissance sélective.", {"value": 60, "unit": "nm"}),
            objres("Longueur d'onde d'émission estimée", "inconclusive", "Zone active pas encore déposée."),
        ],
        days_ago=266,
    )
    b3 = proj.tag(demo, b3, ["gravure", "wafer-lot-A"], days_ago=266)

    # 5. Croissance sélective - pointe semipolaire
    b4 = proj.evolve(
        demo, b3,
        title="Croissance sélective - amorce de la pointe semipolaire",
        intent="Faire converger le sommet des piliers en pointe semipolaire par croissance sélective successive.",
        hypothesis="Une série de croissances sélectives avec un rapport C>M>SP suffisamment marqué devrait refermer le sommet en quelques étapes.",
        substrate=epi_substrate(), steps=epi_stack(15) + LITHO_ETCH + GROWTH_TAPER, days_ago=250,
    )
    b4 = proj.evidence(demo, b4, description="Pointe bien refermée, diamètre résiduel mesuré au MEB.", source="MEB salle blanche", metric_name="diametre_pointe_nm", metric_value=18, metric_unit="nm", days_ago=248)
    b4 = proj.conclude(
        demo, b4, decision="promote", summary="Pointe semipolaire obtenue, proche de l'objectif.",
        objective_results=[
            objres("Rugosité de surface", "inconclusive", "Pas de nouvelle mesure AFM sur cette étape."),
            objres("Diamètre de pointe", "partially_met", "18nm résiduels, proche de la cible de 15nm après trois croissances sélectives successives.", {"value": 18, "unit": "nm"}),
            objres("Longueur d'onde d'émission estimée", "inconclusive", "Zone active pas encore déposée."),
        ],
        days_ago=246,
    )
    b4 = proj.tag(demo, b4, ["croissance-selective", "wafer-lot-A"], days_ago=246)

    # 6. Puits quantique unique InGaN + capot GaN (visée bleue, ~18% d'indium)
    b6 = proj.evolve(
        demo, b4,
        title="Puits quantique InGaN + capot GaN",
        intent="Ajouter la zone active (un seul puits quantique InGaN) sur la pointe semipolaire pour viser l'émission bleue.",
        hypothesis="Un puits InGaN de 3nm avec une composition d'indium modérée (~18%) devrait viser une émission autour de 450nm.",
        substrate=epi_substrate(), steps=epi_stack(15) + LITHO_ETCH + GROWTH_TAPER + active_region_single(18), days_ago=220,
    )
    b6 = proj.evidence(demo, b6, description="Composition d'indium confirmée par EDX à 17-19%, cohérent avec la cible.", source="EDX salle blanche", metric_name="longueur_onde_nm", metric_value=451, metric_unit="nm", days_ago=218)
    b6 = proj.conclude(
        demo, b6, decision="branch", summary="Zone active en place, à caractériser en photoluminescence puis à contacter.",
        objective_results=[
            objres("Rugosité de surface", "inconclusive", "Pas de nouvelle mesure AFM après le dépôt de la zone active."),
            objres("Diamètre de pointe", "inconclusive", "Pas de nouvelle mesure MEB à cette étape, pointe déjà validée précédemment."),
            objres("Longueur d'onde d'émission estimée", "met", "451nm estimé par EDX à partir de la composition d'indium, quasiment pile sur la cible de 450nm.", {"value": 451, "unit": "nm"}),
        ],
        days_ago=216,
    )
    b6 = proj.tag(demo, b6, ["zone-active", "wafer-lot-B"], days_ago=216)
    b6 = proj.track(demo, b6, sample_id="W-B1", location="Boîte à wafers, salle blanche, tiroir 2", days_ago=216)

    # 7. Contact ITO en face avant - devient la ref "puits-simple-reference" : la structure LED à
    # puits simple complète, point de départ des trois déclinaisons de teinte ci-dessous.
    b7 = proj.evolve(
        lea, b6,
        title="Contact ITO en face avant",
        intent="Ajouter un contact transparent pour l'injection électrique tout en laissant passer la lumière.",
        hypothesis="Un dépôt directionnel d'ITO de 15nm devrait offrir un bon compromis conduction/transparence.",
        substrate=epi_substrate(), steps=epi_stack(15) + LITHO_ETCH + GROWTH_TAPER + active_region_single(18) + ito_contact, days_ago=200,
    )
    b7 = proj.evidence(lea, b7, description="Contact continu observé au MEB, pas de zones découvertes.", source="MEB salle blanche", days_ago=198)
    b7 = proj.conclude(
        lea, b7, decision="promote", summary="LED bleue à puits simple validée de bout en bout - référence pour les déclinaisons de couleur.",
        objective_results=[
            objres("Rugosité de surface", "inconclusive", "Pas de nouvelle mesure AFM après le dépôt du contact."),
            objres("Diamètre de pointe", "inconclusive", "Pas de nouvelle mesure MEB dédiée à la pointe sur cette étape."),
            objres("Longueur d'onde d'émission estimée", "met", "451nm confirmé avant contact, contact avant transparent sans impact optique attendu.", {"value": 451, "unit": "nm"}),
        ],
        days_ago=196,
    )
    b7 = proj.tag(lea, b7, ["contact", "wafer-lot-B", "recette-approuvee"], days_ago=196)
    proj.make_ref(demo, b7, name="puits-simple-reference")

    # 8. Déclinaison verte (~27% d'indium visé) - le "green gap" reste difficile à atteindre
    # pile, réaliste pour ce type de matériau.
    b8 = proj.evolve(
        demo, b7,
        title="Puits quantique InGaN - visée verte (~520nm)",
        intent="Décliner la zone active vers le vert en augmentant la composition d'indium du puits.",
        hypothesis="Une composition d'indium autour de 27% devrait décaler l'émission vers 520nm, au prix d'un désaccord de maille plus marqué.",
        substrate=epi_substrate(), steps=epi_stack(15) + LITHO_ETCH + GROWTH_TAPER + active_region_single(27) + ito_contact,
        new_branch="led-verte", days_ago=170,
    )
    b8 = proj.evidence(demo, b8, description="Émission mesurée à 508nm - décalage réel mais en-deçà de la cible, intensité plus faible qu'en bleu (signe de relaxation de contrainte).", source="Photoluminescence salle blanche", metric_name="longueur_onde_nm", metric_value=508, metric_unit="nm", days_ago=168)
    b8 = proj.conclude(
        demo, b8, decision="inconclusive", summary="Décalage vers le vert confirmé mais incomplet - le \"green gap\" bien connu de la filière InGaN.",
        objective_results=[
            objres("Rugosité de surface", "inconclusive", "Pas de nouvelle mesure AFM dédiée à cette variante."),
            objres("Diamètre de pointe", "inconclusive", "Géométrie de pointe inchangée par rapport à la référence."),
            objres("Longueur d'onde d'émission estimée", "partially_met", "508nm mesurés, décalage réel vers le vert mais sous la cible de 520nm et intensité dégradée - désaccord de maille croissant avec la composition d'indium.", {"value": 508, "unit": "nm"}),
        ],
        days_ago=166,
    )
    b8 = proj.tag(demo, b8, ["led-verte", "zone-active"], days_ago=166)

    # 9. Déclinaison rouge (~40% d'indium visé) - encore plus difficile ("red gap").
    b9 = proj.evolve(
        marc, b7,
        title="Puits quantique InGaN - visée rouge (~620nm)",
        intent="Pousser la composition d'indium encore plus loin pour viser le rouge.",
        hypothesis="Une composition d'indium autour de 40% devrait viser 620nm, mais avec un risque élevé de défauts structuraux à cette teneur.",
        substrate=epi_substrate(), steps=epi_stack(15) + LITHO_ETCH + GROWTH_TAPER + active_region_single(40) + ito_contact,
        new_branch="led-rouge", days_ago=150,
    )
    b9 = proj.evidence(marc, b9, description="Décalage vers le rouge observé (~580nm) mais intensité très faible - forte recombinaison non-radiative, cohérente avec une densité de défauts élevée à cette composition.", source="Photoluminescence salle blanche", metric_name="longueur_onde_nm", metric_value=580, metric_unit="nm", days_ago=148)
    b9 = proj.conclude(
        marc, b9, status="abandoned", decision="abandon", summary="\"Red gap\" confirmé - la filière InGaN plane atteint ses limites à cette teneur en indium, à retenter avec une approche différente (relaxation de contrainte, structure core-shell...).",
        next_steps="Explorer une approche de relaxation de contrainte dédiée avant de retenter le rouge, plutôt que de pousser encore la composition d'indium seule.",
        objective_results=[
            objres("Rugosité de surface", "inconclusive", "Pas de nouvelle mesure AFM dédiée à cette variante."),
            objres("Diamètre de pointe", "inconclusive", "Géométrie de pointe inchangée par rapport à la référence."),
            objres("Longueur d'onde d'émission estimée", "not_met", "580nm mesurés avec une intensité très faible, loin de la cible de 620nm avec une qualité d'émission utilisable.", {"value": 580, "unit": "nm"}),
        ],
        days_ago=146,
    )
    b9 = proj.tag(marc, b9, ["led-rouge", "a-retravailler"], days_ago=146)

    # 10. Fusion : réunir la référence à puits simple (b7) et l'exploration substrat SiC (b5),
    # puis reproduire réellement la structure complète sur SiC dans l'evolve() qui suit.
    b10 = proj.combine(
        demo, b7, other_id=b5,
        title="Réunion : structure LED à puits simple + exploration substrat SiC",
        intent="Relier la référence LED bleue et l'exploration substrat SiC avant de tester la structure complète sur SiC.",
        days_ago=120,
    )
    b10 = proj.evolve(
        demo, b10,
        title="LED bleue complète sur substrat SiC",
        intent="Reproduire la structure LED de référence sur substrat SiC pour vérifier si la meilleure qualité d'épitaxie se traduit par une meilleure LED.",
        hypothesis="Le meilleur accord de maille du SiC devrait réduire encore la densité de dislocations dans la zone active, potentiellement au bénéfice de l'intensité d'émission.",
        substrate=epi_substrate("SiC"), steps=epi_stack(15) + LITHO_ETCH + GROWTH_TAPER + active_region_single(18) + ito_contact,
        days_ago=118,
    )
    b10 = proj.evidence(demo, b10, description="Intensité de photoluminescence supérieure d'environ 30% à l'équivalent sur saphir, à composition d'indium égale.", source="Photoluminescence salle blanche", metric_name="longueur_onde_nm", metric_value=449, metric_unit="nm", days_ago=116)
    b10 = proj.conclude(
        demo, b10, decision="inconclusive", summary="Meilleure qualité optique confirmée sur SiC, mais le coût du substrat en réserve l'usage aux lots les plus critiques.",
        objective_results=[
            objres("Rugosité de surface", "inconclusive", "Pas de nouvelle mesure AFM dédiée, la comparaison porte ici sur l'intensité d'émission."),
            objres("Diamètre de pointe", "inconclusive", "Géométrie de pointe inchangée par rapport à la référence saphir."),
            objres("Longueur d'onde d'émission estimée", "met", "449nm mesurés, cohérent avec la référence saphir, avec une intensité nettement supérieure.", {"value": 449, "unit": "nm"}),
        ],
        days_ago=114,
    )
    b10 = proj.tag(demo, b10, ["substrat-sic", "fusion", "wafer-lot-B"], days_ago=114)
    proj.track(demo, b10, sample_id="W-SiC-1", location="Boîte à wafers, salle blanche, tiroir 4", days_ago=114)

    proj.save_structure(demo, name="Nanofil LED bleue - puits simple, référence", substrate=epi_substrate(), steps=epi_stack(15) + LITHO_ETCH + GROWTH_TAPER + active_region_single(18) + ito_contact)

    return slug


# --------------------------------------------------------------------------------------------
# Projet 2 : Nanofils GaN - puits quantiques multiples (MQW)
# --------------------------------------------------------------------------------------------


def build_mqw_project(demo: Session, lea: Session, marc: Session) -> str:
    created = demo.post(
        "/api/projects",
        json={
            "name": "Nanofils GaN - puits quantiques multiples (MQW)",
            "description": "Même base épitaxiale que le projet à puits simple, mais avec plusieurs puits quantiques : comparaison avec/sans couche bloqueuse d'électrons (EBL), puis réglage du dopage P en aval.",
        },
    )
    slug = created["slug"]
    for email in (lea.email, marc.email):
        demo.post(f"/api/projects/{slug}/members", json={"email": email, "role": "editor"})
    proj = Project(slug)

    OBJ = [
        objective("Rugosité de surface", "rugosite_rms_nm", "minimize", target=1.0, rationale="Une surface rugueuse dégrade la qualité de l'épitaxie suivante.", verification_method="Mesure AFM sur 5x5 µm"),
        objective("Diamètre de pointe", "diametre_pointe_nm", "minimize", target=15, rationale="Une pointe plus fine améliore le confinement optique visé.", verification_method="Mesure MEB en coupe"),
        objective("Intensité électroluminescence relative", "intensite_el_pct", "maximize", target=100, rationale="La couche bloqueuse d'électrons (EBL) doit réduire la fuite d'électrons vers la couche p et donc augmenter l'intensité EL relative.", verification_method="Mesure EL sous injection, normalisée à la meilleure structure connue"),
        objective("Résistance série de la jonction P", "resistance_serie_ohm_mm2", "minimize", target=5.0, rationale="Une résistance série trop élevée limite le courant utile de la LED - directement lié au niveau de dopage P.", verification_method="Mesure 4 pointes sous polarisation directe"),
    ]

    def mqw_active_region(n_periods=3):
        # même remarque que active_region_single : la composition d'indium ne pilote pas l'étape
        # simulée, seul le nombre de périodes (un champ réel du procédé) change la géométrie.
        steps = []
        for i in range(1, n_periods + 1):
            steps.append(deposition(f"Puits quantique InGaN #{i}", "InGaN", recipe="MOCVD Epitaxial", thickness_nm=3))
            steps.append(deposition(f"Barrière GaN #{i}", "GaN", recipe="MOCVD Epitaxial", thickness_nm=8))
        return steps

    def p_gan_cap(doping_label):
        # le dopage (concentration de Mg) n'est pas non plus un champ simulé - seul le nom de
        # l'étape change d'un essai à l'autre, ce qui illustre bien le niveau "correctif (Z)" de
        # spectre.core.versioning : la géométrie simulée est identique, seul le libellé change.
        return deposition(f"Couche GaN dopée Mg (type p, {doping_label})", "GaN", recipe="MOCVD Epitaxial", thickness_nm=100)

    ebl_layer = deposition("Couche bloqueuse d'électrons AlGaN (EBL)", "AlGaN", recipe="MOCVD Epitaxial", thickness_nm=15)

    # 1. Épitaxie de référence (même point de départ que le projet à puits simple, mais dans son
    # propre dépôt Follow - chaque projet a le sien).
    c1 = proj.launch(
        demo,
        title="Épitaxie de référence AlN/GaN sur saphir",
        intent="Établir une épitaxie GaN de référence sur saphir avant d'aller plus loin.",
        hypothesis="Un tampon AlN de 10nm devrait suffire à amorcer une croissance GaN correcte, avec une rugosité autour de 1-1.5nm.",
        substrate=epi_substrate(), steps=epi_stack(10), objectives=OBJ,
        sample_id="M-A1", location="Boîte à wafers, salle blanche, tiroir 5",
        days_ago=300,
    )
    c1 = proj.evidence(demo, c1, description="Imagerie AFM : rugosité RMS mesurée à 1.3nm, quelques dislocations visibles.", source="AFM salle blanche", metric_name="rugosite_rms_nm", metric_value=1.3, metric_unit="nm", days_ago=297)
    c1 = proj.conclude(
        demo, c1, decision="branch", summary="Bon point de départ, tampon un peu fin.",
        objective_results=[
            objres("Rugosité de surface", "not_met", "1.3nm de rugosité RMS mesurée, au-dessus de la cible de 1.0nm.", {"value": 1.3, "unit": "nm"}),
            objres("Diamètre de pointe", "inconclusive", "Pas encore de piliers à ce stade."),
            objres("Intensité électroluminescence relative", "inconclusive", "Zone active pas encore déposée."),
            objres("Résistance série de la jonction P", "inconclusive", "Couche p pas encore déposée."),
        ],
        days_ago=295,
    )
    c1 = proj.tag(demo, c1, ["epitaxie", "wafer-lot-M"], days_ago=295)
    c1 = proj.track(demo, c1, sample_id="M-A1", location="Boîte à wafers, salle blanche, tiroir 5", days_ago=295)

    # 2. Tampon AlN plus épais - ref "epitaxie-standard" (même nom que dans l'autre projet : deux
    # dépôts Follow séparés, les noms de ref ne se marchent pas dessus d'un projet à l'autre).
    c2 = proj.evolve(
        demo, c1,
        title="Tampon AlN plus épais (15nm)",
        intent="Réduire la densité de dislocations en épaississant le tampon.",
        hypothesis="Un tampon AlN à 15nm devrait mieux filtrer les dislocations issues du désaccord de maille avec le saphir.",
        substrate=epi_substrate(), steps=epi_stack(15), days_ago=275,
    )
    c2 = proj.evidence(demo, c2, description="Rugosité RMS réduite à 0.6nm - nette amélioration.", source="AFM salle blanche", metric_name="rugosite_rms_nm", metric_value=0.6, metric_unit="nm", days_ago=273)
    c2 = proj.conclude(
        demo, c2, decision="promote", summary="Tampon 15nm adopté comme standard.",
        objective_results=[
            objres("Rugosité de surface", "met", "0.6nm de rugosité RMS, sous la cible de 1.0nm.", {"value": 0.6, "unit": "nm"}),
            objres("Diamètre de pointe", "inconclusive", "Pas encore de piliers définis."),
            objres("Intensité électroluminescence relative", "inconclusive", "Zone active pas encore déposée."),
            objres("Résistance série de la jonction P", "inconclusive", "Couche p pas encore déposée."),
        ],
        days_ago=271,
    )
    c2 = proj.tag(demo, c2, ["epitaxie", "recette-approuvee"], days_ago=271)
    proj.make_ref(demo, c2, name="epitaxie-standard")

    # 3. Piliers par lithographie + gravure
    c3 = proj.evolve(
        lea, c2,
        title="Définition du réseau de piliers par lithographie + gravure ICP",
        intent="Passer d'un empilement plan à un réseau de piliers, première étape vers les nanofils.",
        hypothesis="Une gravure Cl2 ICP-RIE à travers un masque de résine devrait donner des piliers bien verticaux, sélectifs par rapport au masque.",
        substrate=epi_substrate(), steps=epi_stack(15) + LITHO_ETCH, days_ago=250,
    )
    c3 = proj.evidence(lea, c3, description="Piliers bien définis au MEB, flancs verticaux, diamètre proche de la cible.", source="MEB salle blanche", metric_name="diametre_pointe_nm", metric_value=58, metric_unit="nm", days_ago=248)
    c3 = proj.conclude(
        lea, c3, decision="promote", summary="Gravure validée pour la suite.",
        objective_results=[
            objres("Rugosité de surface", "inconclusive", "Pas de nouvelle mesure AFM après la gravure des piliers."),
            objres("Diamètre de pointe", "not_met", "58nm mesurés au sommet des piliers, loin de la cible de 15nm - attendu avant la croissance sélective.", {"value": 58, "unit": "nm"}),
            objres("Intensité électroluminescence relative", "inconclusive", "Zone active pas encore déposée."),
            objres("Résistance série de la jonction P", "inconclusive", "Couche p pas encore déposée."),
        ],
        days_ago=246,
    )
    c3 = proj.tag(lea, c3, ["gravure", "wafer-lot-M"], days_ago=246)

    # 4. Croissance sélective - pointe semipolaire
    c4 = proj.evolve(
        demo, c3,
        title="Croissance sélective - amorce de la pointe semipolaire",
        intent="Faire converger le sommet des piliers en pointe semipolaire par croissance sélective successive.",
        hypothesis="Une série de croissances sélectives avec un rapport C>M>SP suffisamment marqué devrait refermer le sommet en quelques étapes.",
        substrate=epi_substrate(), steps=epi_stack(15) + LITHO_ETCH + GROWTH_TAPER, days_ago=230,
    )
    c4 = proj.evidence(demo, c4, description="Pointe bien refermée, diamètre résiduel mesuré au MEB.", source="MEB salle blanche", metric_name="diametre_pointe_nm", metric_value=17, metric_unit="nm", days_ago=228)
    c4 = proj.conclude(
        demo, c4, decision="promote", summary="Pointe semipolaire obtenue, proche de l'objectif.",
        objective_results=[
            objres("Rugosité de surface", "inconclusive", "Pas de nouvelle mesure AFM sur cette étape."),
            objres("Diamètre de pointe", "partially_met", "17nm résiduels, proche de la cible de 15nm après trois croissances sélectives successives.", {"value": 17, "unit": "nm"}),
            objres("Intensité électroluminescence relative", "inconclusive", "Zone active pas encore déposée."),
            objres("Résistance série de la jonction P", "inconclusive", "Couche p pas encore déposée."),
        ],
        days_ago=226,
    )
    c4 = proj.tag(demo, c4, ["croissance-selective", "wafer-lot-M"], days_ago=226)

    # 5. Puits quantiques multiples (3 périodes), sans EBL - couche p directement après le
    # dernier puits/barrière.
    c5 = proj.evolve(
        demo, c4,
        title="Puits quantiques multiples InGaN/GaN (MQW, sans EBL)",
        intent="Empiler plusieurs puits quantiques pour augmenter le volume actif, avant d'évaluer si une couche bloqueuse d'électrons est nécessaire.",
        hypothesis="Trois périodes InGaN/GaN devraient augmenter le volume actif, mais sans couche bloqueuse, une partie des électrons risque de fuir vers la couche p sous forte injection.",
        substrate=epi_substrate(), steps=epi_stack(15) + LITHO_ETCH + GROWTH_TAPER + mqw_active_region(3) + [p_gan_cap("dopage de référence")], days_ago=200,
    )
    c5 = proj.evidence(demo, c5, description="Intensité EL mesurée à 62% de la meilleure structure connue, avec un net repli (\"efficiency droop\") à forte injection - signe probable de fuite électronique vers la couche p.", source="Banc EL salle blanche", metric_name="intensite_el_pct", metric_value=62, metric_unit="%", days_ago=198)
    c5 = proj.conclude(
        demo, c5, decision="branch", summary="MQW en place mais fuite électronique probable sans couche bloqueuse - à confirmer en ajoutant un EBL.",
        objective_results=[
            objres("Rugosité de surface", "inconclusive", "Pas de nouvelle mesure AFM après le dépôt de la zone active."),
            objres("Diamètre de pointe", "inconclusive", "Géométrie de pointe inchangée depuis l'étape précédente."),
            objres("Intensité électroluminescence relative", "not_met", "62% de la meilleure structure connue, avec un repli marqué à forte injection - cohérent avec une fuite électronique vers la couche p.", {"value": 62, "unit": "%"}),
            objres("Résistance série de la jonction P", "inconclusive", "Pas de mesure dédiée sur cette variante sans EBL."),
        ],
        days_ago=196,
    )
    c5 = proj.tag(demo, c5, ["mqw", "sans-ebl"], days_ago=196)

    # 6. Ajout de l'EBL - devient la ref "mqw-ebl-reference", point de départ du réglage du
    # dopage P ci-dessous.
    c6 = proj.evolve(
        lea, c5,
        title="Ajout d'une couche bloqueuse d'électrons AlGaN (EBL)",
        intent="Insérer une couche AlGaN entre la zone active et la couche p pour bloquer la fuite d'électrons observée sans EBL.",
        hypothesis="Une couche AlGaN de 15nm juste avant la couche p devrait relever la barrière de conduction et réduire fortement la fuite électronique.",
        substrate=epi_substrate(), steps=epi_stack(15) + LITHO_ETCH + GROWTH_TAPER + mqw_active_region(3) + [ebl_layer, p_gan_cap("dopage de référence")],
        new_branch="avec-ebl", days_ago=170,
    )
    c6 = proj.evidence(lea, c6, description="Intensité EL mesurée à 94% de la meilleure structure connue, plus de repli visible à forte injection - la fuite électronique est nettement réduite.", source="Banc EL salle blanche", metric_name="intensite_el_pct", metric_value=94, metric_unit="%", days_ago=168)
    c6 = proj.conclude(
        lea, c6, decision="promote", summary="EBL efficace - adopté comme structure de référence pour le MQW.",
        objective_results=[
            objres("Rugosité de surface", "inconclusive", "Pas de nouvelle mesure AFM dédiée à cette variante."),
            objres("Diamètre de pointe", "inconclusive", "Géométrie de pointe inchangée."),
            objres("Intensité électroluminescence relative", "met", "94% de la meilleure structure connue, net gain par rapport aux 62% sans EBL et plus de repli visible à forte injection.", {"value": 94, "unit": "%"}),
            objres("Résistance série de la jonction P", "inconclusive", "Dopage P encore au niveau de référence, pas encore optimisé."),
        ],
        days_ago=166,
    )
    c6 = proj.tag(lea, c6, ["mqw", "avec-ebl", "recette-approuvee"], days_ago=166)
    c6 = proj.track(demo, c6, sample_id="M-B1", location="Boîte à wafers, salle blanche, tiroir 6", days_ago=166)
    proj.make_ref(demo, c6, name="mqw-ebl-reference")

    # 7. Dopage P modéré - seul le libellé de la couche p change (correctif/patch pour
    # spectre.core.versioning : même géométrie simulée).
    c7 = proj.evolve(
        demo, c6,
        title="Dopage P modéré (Mg ~5e18 cm-3)",
        intent="Caractériser l'effet du niveau de dopage Mg de la couche p sur la résistance série de la jonction.",
        hypothesis="Un dopage modéré devrait déjà réduire sensiblement la résistance série sans dégrader la qualité cristalline de la couche p.",
        substrate=epi_substrate(), steps=epi_stack(15) + LITHO_ETCH + GROWTH_TAPER + mqw_active_region(3) + [ebl_layer, p_gan_cap("Mg ~5e18 cm-3")], days_ago=140,
    )
    c7 = proj.evidence(demo, c7, description="Résistance série mesurée à 4.2Ω·mm², sous la cible, sans dégradation visible de l'intensité EL.", source="Mesure 4 pointes salle blanche", metric_name="resistance_serie_ohm_mm2", metric_value=4.2, metric_unit="Ω·mm²", days_ago=138)
    c7 = proj.conclude(
        demo, c7, decision="promote", summary="Dopage modéré donne une bonne résistance série sans dégrader la qualité cristalline.",
        objective_results=[
            objres("Rugosité de surface", "inconclusive", "Pas de nouvelle mesure AFM dédiée."),
            objres("Diamètre de pointe", "inconclusive", "Géométrie de pointe inchangée."),
            objres("Intensité électroluminescence relative", "inconclusive", "Pas de nouvelle mesure EL dédiée à ce niveau de dopage."),
            objres("Résistance série de la jonction P", "met", "4.2Ω·mm² mesurés, sous la cible de 5.0.", {"value": 4.2, "unit": "Ω·mm²"}),
        ],
        days_ago=136,
    )
    c7 = proj.tag(demo, c7, ["dopage-p"], days_ago=136)

    # 8. Dopage P élevé - meilleure résistance série, mais compromis sur la qualité cristalline
    # (l'auto-compensation à fort dopage Mg est un phénomène bien connu du GaN de type p).
    c8 = proj.evolve(
        demo, c7,
        title="Dopage P élevé (Mg ~1e19 cm-3)",
        intent="Pousser le dopage plus loin pour voir si la résistance série continue de s'améliorer.",
        hypothesis="Un dopage plus élevé devrait encore réduire la résistance série, au risque de dégrader la qualité cristalline par auto-compensation.",
        substrate=epi_substrate(), steps=epi_stack(15) + LITHO_ETCH + GROWTH_TAPER + mqw_active_region(3) + [ebl_layer, p_gan_cap("Mg ~1e19 cm-3")], days_ago=110,
    )
    c8 = proj.evidence(demo, c8, description="Résistance série encore réduite à 2.8Ω·mm², mais intensité EL en légère baisse - signe d'auto-compensation à ce niveau de dopage.", source="Mesure 4 pointes + banc EL salle blanche", metric_name="resistance_serie_ohm_mm2", metric_value=2.8, metric_unit="Ω·mm²", days_ago=108)
    c8 = proj.conclude(
        demo, c8, decision="branch", summary="Meilleure résistance série mais au prix d'une intensité EL en baisse - compromis à affiner.",
        objective_results=[
            objres("Rugosité de surface", "inconclusive", "Pas de nouvelle mesure AFM dédiée."),
            objres("Diamètre de pointe", "inconclusive", "Géométrie de pointe inchangée."),
            objres("Intensité électroluminescence relative", "partially_met", "81% de la meilleure structure connue, en retrait par rapport aux 94% de la référence EBL - auto-compensation probable à ce niveau de dopage.", {"value": 81, "unit": "%"}),
            objres("Résistance série de la jonction P", "met", "2.8Ω·mm² mesurés, meilleure valeur obtenue, sous la cible de 5.0.", {"value": 2.8, "unit": "Ω·mm²"}),
        ],
        days_ago=106,
    )
    c8 = proj.tag(demo, c8, ["dopage-p", "a-optimiser"], days_ago=106)

    # 9. Dopage P optimisé - compromis retenu entre résistance série et intensité EL, devient la
    # ref "mqw-dopage-optimise".
    c9 = proj.evolve(
        marc, c8,
        title="Dopage P optimisé (Mg ~7e18 cm-3, compromis)",
        intent="Trouver un compromis entre les deux essais précédents plutôt que de pousser le dopage au maximum.",
        hypothesis="Un dopage intermédiaire devrait retrouver une intensité EL proche de la référence tout en gardant une résistance série nettement meilleure que le dopage de référence.",
        substrate=epi_substrate(), steps=epi_stack(15) + LITHO_ETCH + GROWTH_TAPER + mqw_active_region(3) + [ebl_layer, p_gan_cap("Mg ~7e18 cm-3, optimisé")], days_ago=80,
    )
    c9 = proj.evidence(marc, c9, description="Résistance série à 3.3Ω·mm² et intensité EL revenue à 97% de la meilleure structure connue - meilleur compromis obtenu à ce jour.", source="Mesure 4 pointes + banc EL salle blanche", metric_name="resistance_serie_ohm_mm2", metric_value=3.3, metric_unit="Ω·mm²", days_ago=78)
    c9 = proj.conclude(
        marc, c9, decision="promote", summary="Meilleur compromis dopage P trouvé - adopté comme structure MQW+EBL de référence.",
        objective_results=[
            objres("Rugosité de surface", "inconclusive", "Pas de nouvelle mesure AFM dédiée."),
            objres("Diamètre de pointe", "inconclusive", "Géométrie de pointe inchangée."),
            objres("Intensité électroluminescence relative", "met", "97% de la meilleure structure connue, quasiment au niveau de la référence EBL initiale.", {"value": 97, "unit": "%"}),
            objres("Résistance série de la jonction P", "met", "3.3Ω·mm², nettement sous la cible de 5.0 et sous le niveau de référence, sans le compromis observé au dopage maximal.", {"value": 3.3, "unit": "Ω·mm²"}),
        ],
        days_ago=76,
    )
    c9 = proj.tag(marc, c9, ["dopage-p", "recette-approuvee", "version-finale"], days_ago=76)
    proj.make_ref(demo, c9, name="mqw-dopage-optimise")
    proj.track(demo, c9, sample_id="M-B1", location="Boîte à wafers, salle blanche, tiroir 6", days_ago=76)

    proj.save_structure(demo, name="Nanofil LED MQW + EBL - référence dopage optimisé", substrate=epi_substrate(), steps=epi_stack(15) + LITHO_ETCH + GROWTH_TAPER + mqw_active_region(3) + [ebl_layer, p_gan_cap("Mg ~7e18 cm-3, optimisé")])

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

        print("Génération du projet « Nanofils GaN - puits quantique simple »...")
        single_qw_slug = build_single_qw_project(demo, lea, marc)
        print("Génération du projet « Nanofils GaN - puits quantiques multiples (MQW) »...")
        mqw_slug = build_mqw_project(demo, lea, marc)

    print("Recalage des dates sur environ un an d'historique...")
    backdate_experiments(data_dir, [single_qw_slug, mqw_slug])
    backdate_projects(data_dir, [single_qw_slug, mqw_slug], days_ago=350)

    print(
        f"\nCompte de démo prêt :\n"
        f"  e-mail    : {DEMO_EMAIL}\n"
        f"  mot de passe : {DEMO_PASSWORD}\n"
        f"  projets   : {single_qw_slug}, {mqw_slug}\n"
        f"  {len(SCHEDULE)} versions d'expérience générées au total.\n"
    )


if __name__ == "__main__":
    sys.exit(main())
