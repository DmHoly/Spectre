"""Fonctions de graphique pédagogique référencées depuis un ``hook.yml`` (champ ``charts``), sur le
même principe que ``postprocessing`` : un module par hook, une fonction ``(df) -> matplotlib.figure.
Figure`` par graphique, résolue par ``module:fonction`` - jamais du code arbitraire dans le YAML.

Contrairement au post-traitement (qui transforme les données), un graphique ne fait qu'illustrer -
souvent en annotant *comment* un KPI est extrait d'une courbe brute (ex. facteur d'idéalité et
résistance série lus sur une courbe I-V), ce que le tableau de KPI seul ne montre pas.
"""

from __future__ import annotations
