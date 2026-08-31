"""French, one-line descriptions for StructureForge's standard recipes - shown in place of their
``notes`` field, which is written in English for StructureForge's own (developer-facing) docs and
sometimes talks about the simulation engine's own modelling choices ("this engine doesn't check
for..."). A recipe not listed here (a project's own custom recipe) falls back to its own
``notes`` in the UI, since a project author writes those themselves.
"""

from __future__ import annotations

DEPOSITION_DESCRIPTIONS_FR: dict[str, str] = {
    "ALD Conformal": "Dépôt uniforme qui épouse parfaitement tous les reliefs de la surface.",
    "CVD Conformal": "Dépôt uniforme sur les reliefs, une bonne couverture standard.",
    "PVD Sputter (tilted)": "Dépôt métallique en visée directe, légèrement incliné — les zones cachées sont moins couvertes.",
    "Evaporation (normal)": "Dépôt métallique tout droit par le dessus — ne couvre presque pas les flancs, adapté à un lift-off.",
    "MOCVD Epitaxial": "Croissance épitaxiale (semi-conducteurs III-N/III-V) sur une base plane.",
    "PECVD Conformal": "Dépôt assisté par plasma, à plus basse température — bonne couverture des reliefs.",
    "Sputter Metal (normal)": "Dépôt métallique par pulvérisation, par le dessus — couvre mieux les flancs qu'une évaporation, reste directionnel.",
    "Electroplating (Cu)": "Remplissage électrochimique en cuivre — nécessite une couche d'amorce déjà en place.",
}

ETCH_DESCRIPTIONS_FR: dict[str, str] = {
    "Dry Oxide Etch": "Gravure sèche qui attaque surtout les oxydes ; grave presque aussi vite tout le reste.",
    "Wet HF Dip": "Bain humide très sélectif de l'oxyde — épargne le nitrure, le silicium et les métaux.",
    "Anisotropic RIE": "Gravure sèche quasi verticale — le masque de résine s'érode lentement, tout le reste au rythme normal.",
    "Ion Mill (tilted)": "Gravure physique inclinée (usinage ionique) — attaque presque tous les matériaux au même rythme.",
    "KOH Anisotropic Wet Etch": "Gravure humide cristallographique du silicium, angle fixe à 54,7° — s'arrête presque totalement sur un masque oxyde/nitrure.",
    "Cl2 ICP-RIE (III-N)": "Gravure sèche quasi verticale des semi-conducteurs III-N (GaN, AlGaN...) — sélective par rapport aux masques, diélectriques et métaux.",
    "TMAH Anisotropic Wet Etch": "Alternative au KOH sans contamination alcaline, même angle cristallographique — plus douce sur l'aluminium exposé.",
    "SF6 Deep RIE (Si)": "Gravure profonde du silicium (type Bosch) — quasi verticale et rapide, s'arrête bien sur un masque oxyde/nitrure/résine.",
    "Wet Metal Etch": "Bain humide générique pour graver un métal — attaque lentement tout le reste ; sous-grave comme toute gravure isotrope.",
}
