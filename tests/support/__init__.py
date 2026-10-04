"""Aides partagées par les tests : un module par plugin (accounts, microprojects, structures,
experiments, lots, areas) plus ``http`` pour ce qui est propre au protocole, pour que chaque
plugin puisse faire évoluer les siennes sans toucher à celles des autres.

Chaque aide qui appelle une route en encapsule une seule (URL, méthode, code attendu) et renvoie
son JSON : quand une route est renommée, c'est le seul endroit à changer. Un test qui porte sur la
sémantique HTTP d'une route elle-même (codes, validation) garde son appel brut.
"""
