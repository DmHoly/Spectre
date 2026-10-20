# Spectre - image de production.
#
# Le paquet dépend de structureforge[follow] installé depuis GitHub et de PRISM
# (prism-aledia-datahook) installé depuis gitlab-it.aledia.com (voir pyproject.toml) : construire
# cette image nécessite donc un accès réseau sortant vers GitHub et vers le GitLab interne. Rien
# d'autre à compiler (pas d'extension C) - une seule étape suffit.
#
# PRISM : les profils de connexion (hôtes et bases, sans secret) sont embarqués (config/connections.yml).
# Le mot de passe, lui, n'est JAMAIS dans l'image (le .tar part chez l'IT) : il se fournit au
# lancement, par `--env-file .env` (PRISM_USER / PRISM_PASSWORD, ou PRISM_<PROFIL>_*).

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
COPY config ./config

# Certificats de l'entreprise (dossier certs/, fichiers .crt) : le GitLab interne est signé par une
# autorité que l'image python:slim ne connaît pas. Aucun fichier = aucun ajout.
COPY certs/ /usr/local/share/ca-certificates/

# git : les dépendances (StructureForge, PRISM, Lumière) s'installent depuis des dépôts git, et
# l'image python:slim n'en contient pas. Il n'est utile qu'à la construction : retiré juste après.
# Le GitLab interne demande un compte : un jeton d'accès (lecture des dépôts) fourni au build par
# `--secret id=gitlab_token` (build-docker.bat, variable GITLAB_TOKEN). Il n'existe que le temps de
# cette commande - ni dans l'image, ni dans ses couches, ni dans les métadonnées pip.
RUN --mount=type=secret,id=gitlab_token \
    apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && update-ca-certificates \
    && if [ -s /run/secrets/gitlab_token ]; then \
         export GIT_CONFIG_COUNT=1 \
                GIT_CONFIG_KEY_0="url.https://oauth2:$(cat /run/secrets/gitlab_token)@gitlab-it.aledia.com/.insteadOf" \
                GIT_CONFIG_VALUE_0="https://gitlab-it.aledia.com/"; \
       fi \
    && pip install --no-cache-dir . \
    && apt-get purge -y --auto-remove git \
    && rm -rf /var/lib/apt/lists/*

# Les données (comptes, projets, dépôts d'expériences Follow, recettes) sont écrites ici - monter
# un volume sur ce chemin pour les faire survivre à un redémarrage du conteneur.
ENV SPECTRE_DATA_DIR=/data     PRISM_DATA_DIR=/data/prism     PRISM_CONNECTIONS_FILE=/app/config/connections.yml

# Premier démarrage sur un /data vide : crée le compte administrateur « admin » / « admin » (identifiant
# puis mot de passe) qui doit changer son mot de passe à sa première connexion. Sans effet dès qu'un
# compte existe ; à surcharger (docker-compose.yml) pour un autre identifiant initial.
ENV SPECTRE_INITIAL_ADMIN=admin:admin

# Derriere le reverse proxy de l'IT : uvicorn ne fait confiance aux en-tetes X-Forwarded-* que de
# 127.0.0.1 par defaut ; le proxy arrive d'une autre adresse, on les accepte donc de partout (le
# port 8000 n'est joignable que par le proxy).
ENV FORWARDED_ALLOW_IPS=*
RUN mkdir -p /data

# Utilisateur non privilégié : l'image ne tourne jamais en root.
RUN useradd --create-home --uid 1000 spectre \
    && chown -R spectre:spectre /data /app
USER spectre

EXPOSE 8000

# --host 0.0.0.0 est nécessaire ici (le défaut de la CLI, 127.0.0.1, n'est pas joignable depuis
# l'extérieur du conteneur) ; --reload volontairement absent (jamais en production).
CMD ["spectre", "--host", "0.0.0.0", "--port", "8000"]
