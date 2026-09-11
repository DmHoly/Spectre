"""Connexion à la base de données de caractérisation (PostgreSQL) - le seul endroit de tout
``datahook`` qui parle réellement au réseau. Un hook (voir :mod:`spectre.core.datahook.hooks`)
n'a besoin que d'appeler :func:`run_query` avec sa requête et ses paramètres ; tout ce qui concerne
*comment* on s'y connecte (identifiants, hôte, base) vit ici, dans un seul endroit remplaçable.

Identifiants : priorité aux variables d'environnement (``DB_LUMIERE_USER``/``DB_LUMIERE_PASSWORD``),
sinon repli sur ``config/Credential.ini`` (jamais commité - voir ``config/Readme.md`` et le
``.gitignore`` à la racine du dépôt). Hôte/base/port : mêmes deux sources, dans
``config/config.ini`` (section ``[DB]``) plutôt que codés en dur, avec les valeurs historiques de
cette installation comme repli.
"""

from __future__ import annotations

import configparser
import logging
import os
from pathlib import Path
from typing import Any

import pandas as pd
import psycopg2

logger = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).resolve().parent / "config"
CREDENTIAL_PATH = CONFIG_DIR / "Credential.ini"
CONFIG_PATH = CONFIG_DIR / "config.ini"

# Repli historique (voir legacy/Requester.py) - toute installation qui ne fournit ni variable
# d'environnement ni [DB] dans config.ini se connecte comme le faisait l'ancien script.
_DEFAULT_HOST = "INF49"
_DEFAULT_DATABASE = "testcarac"
_DEFAULT_PORT = "5432"


class DatahookConfigError(Exception):
    """Identifiants ou paramètres de connexion introuvables ou incomplets."""


def _read_config_section(section: str) -> dict[str, str]:
    if not CONFIG_PATH.exists():
        return {}
    parser = configparser.ConfigParser()
    parser.read(CONFIG_PATH, encoding="utf-8")
    return dict(parser[section]) if section in parser else {}


def _read_credentials() -> tuple[str, str]:
    user = os.getenv("DB_LUMIERE_USER")
    password = os.getenv("DB_LUMIERE_PASSWORD")
    if user and password:
        return user, password

    if not CREDENTIAL_PATH.exists():
        raise DatahookConfigError(
            f"Identifiants introuvables : ni DB_LUMIERE_USER/DB_LUMIERE_PASSWORD, ni {CREDENTIAL_PATH} "
            "(voir spectre/core/datahook/config/Readme.md)."
        )
    parser = configparser.ConfigParser()
    parser.read(CREDENTIAL_PATH, encoding="utf-8")
    if "DB_CREDENTIALS" not in parser:
        raise DatahookConfigError(f"section [DB_CREDENTIALS] manquante dans {CREDENTIAL_PATH}")
    user = parser["DB_CREDENTIALS"].get("user")
    password = parser["DB_CREDENTIALS"].get("password")
    if not user or not password:
        raise DatahookConfigError(f"user/password manquant(s) dans {CREDENTIAL_PATH}")
    return user, password


def connection_params() -> dict[str, str]:
    """Les paramètres de connexion (hôte/base/port/identifiants), sans jamais se connecter -
    utile pour un diagnostic ("à quoi va-t-on se connecter ?") sans exécuter de requête.
    """
    db_section = _read_config_section("DB")
    user, password = _read_credentials()
    return {
        "host": os.getenv("DB_LUMIERE_HOST") or db_section.get("host", _DEFAULT_HOST),
        "database": os.getenv("DB_LUMIERE_NAME") or db_section.get("database", _DEFAULT_DATABASE),
        "port": os.getenv("DB_LUMIERE_PORT") or db_section.get("port", _DEFAULT_PORT),
        "user": user,
        "password": password,
    }


def get_connection() -> "psycopg2.extensions.connection":
    params = connection_params()
    return psycopg2.connect(**params)


def run_query(sql: str, params: dict[str, Any] | None = None) -> pd.DataFrame:
    """Exécute ``sql`` (avec ses paramètres nommés ``%(...)s``, style psycopg2) et renvoie le
    résultat en DataFrame - un hook n'a jamais besoin de toucher au curseur lui-même.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
    finally:
        conn.close()
    return pd.DataFrame(rows, columns=columns)
