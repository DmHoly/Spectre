# Spectre - image de production.
#
# Le paquet dépend de structureforge[follow] installé depuis GitHub (voir pyproject.toml) :
# construire cette image nécessite donc un accès réseau sortant vers GitHub. Rien d'autre à
# compiler (pas d'extension C) - une seule étape suffit.

FROM python:3.11-slim

# Empêche la génération de .pyc et force les logs à s'afficher immédiatement (utile en conteneur,
# où stdout est bufferisé par défaut).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Copié avant le reste pour profiter du cache Docker : la couche d'installation des dépendances
# n'est reconstruite que si pyproject.toml change, pas à chaque modification du code.
COPY pyproject.toml README.md ./
COPY spectre ./spectre

RUN pip install --no-cache-dir .

# Les données (comptes, projets, dépôts d'expériences Follow, recettes) sont écrites ici - monter
# un volume sur ce chemin pour les faire survivre à un redémarrage du conteneur.
ENV SPECTRE_DATA_DIR=/data
RUN mkdir -p /data

# Utilisateur non privilégié : l'image ne tourne jamais en root.
RUN useradd --create-home --uid 1000 spectre \
    && chown -R spectre:spectre /data /app
USER spectre

EXPOSE 8000

# --host 0.0.0.0 est nécessaire ici (le défaut de la CLI, 127.0.0.1, n'est pas joignable depuis
# l'extérieur du conteneur) ; --reload volontairement absent (jamais en production).
CMD ["spectre", "--host", "0.0.0.0", "--port", "8000"]
