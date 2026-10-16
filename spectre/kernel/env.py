"""Le fichier ``.env`` à la racine du projet : secrets et réglages de poste (mot de passe de la base
PRISM, SMTP...), jamais versionné (``.gitignore``).

Lu une seule fois au démarrage, dans ``os.environ`` : tout le code (et PRISM, qui ne lit que
l'environnement) continue de passer par les variables d'environnement. Une variable déjà définie
dans l'environnement réel l'emporte sur le fichier - un déploiement n'a donc rien à changer.
``SPECTRE_ENV_FILE`` désigne un autre fichier (installation hors du dépôt, tests). Désigne aussi à
PRISM le ``config/connections.yml`` du dépôt (hôtes et bases, sans secret).
"""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONNECTIONS_FILE = PROJECT_ROOT / "config" / "connections.yml"


def env_file() -> Path:
    explicit = os.environ.get("SPECTRE_ENV_FILE")
    return Path(explicit) if explicit else PROJECT_ROOT / ".env"


def parse(text: str) -> dict[str, str]:
    """``NOM=valeur`` par ligne ; ``#`` commence un commentaire, ``export`` et les guillemets
    simples ou doubles autour de la valeur sont tolérés."""
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        name, sep, value = line.partition("=")
        name, value = name.strip(), value.strip()
        if not sep or not name:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        else:
            value = value.split(" #", 1)[0].rstrip()
        values[name] = value
    return values


def load_env() -> list[str]:
    """Charge le ``.env`` s'il existe ; renvoie les noms de variables posées (jamais leurs valeurs)."""
    # Les profils de connexion PRISM (sans secret) sont livrés avec Spectre ; un poste peut
    # toujours poser PRISM_CONNECTIONS_FILE (ou PRISM_CONFIG_DIR) pour utiliser les siens.
    if CONNECTIONS_FILE.is_file() and "PRISM_CONFIG_DIR" not in os.environ:
        os.environ.setdefault("PRISM_CONNECTIONS_FILE", str(CONNECTIONS_FILE))
    path = env_file()
    if not path.is_file():
        return []
    loaded = []
    for name, value in parse(path.read_text(encoding="utf-8-sig")).items():
        if name not in os.environ:
            os.environ[name] = value
            loaded.append(name)
    return loaded
