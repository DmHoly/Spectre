"""Extraction statique des appels HTTP du front vers l'API : chaque ``api.get/post/put/patch/del``
et ``api.request`` (``js/api.js``) et chaque ``fetch`` d'un dossier de pages (``spectre/api/static``
aujourd'hui, celui d'un plugin demain), avec la méthode et le chemin qu'il vise - sans navigateur ni
interpréteur JavaScript. Un petit lexeur sait seulement ce que sont un commentaire, une chaîne, un
gabarit (`...${...}...`) et une expression régulière littérale : de quoi lire les arguments d'un appel.

Le chemin d'un appel est connu quand son URL commence par un littéral : chaque ``${...}`` (et chaque
opérande non littéral d'une concaténation) devient le segment générique :data:`PARAM`, la query
string est retirée. Sinon - une variable, une expression - l'appel est « dynamique » : ``path`` vaut
``None``, et c'est à l'appelant de dire, par une liste explicite, quelle route il vise.
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

PARAM = "{param}"
API_PREFIX = "/api/"

# Les bibliothèques embarquées et les pages de documentation (qui citent des appels en exemple).
DEFAULT_EXCLUDES = ("js/vendor/*", "docs*.html")

METHODS = {"get": "GET", "post": "POST", "put": "PUT", "patch": "PATCH", "del": "DELETE"}

_CALL_RE = re.compile(r"(?<![\w$.])(?:api\s*\.\s*(get|post|put|patch|del|request)|fetch)\s*\(")
_METHOD_OPTION_RE = re.compile(r"""\bmethod\s*:\s*["'`](\w+)["'`]""")
_INLINE_SCRIPT_RE = re.compile(r"<script\b(?![^>]*\bsrc=)[^>]*>(.*?)</script>", re.DOTALL | re.IGNORECASE)
# Après l'un de ces caractères, un « / » ouvre une expression régulière, pas une division.
_REGEX_PRECEDERS = set("(,=:[!&|?{};+-*%<>~^")


@dataclass(frozen=True)
class FrontendCall:
    file: str  # relatif au dossier scanné, en notation POSIX
    line: int
    method: str
    expression: str  # le premier argument tel qu'écrit (espaces réduits)
    path: str | None  # "/api/..." avec PARAM pour chaque partie variable ; None si l'URL est dynamique

    def __str__(self) -> str:
        return f"{self.file}:{self.line} {self.method} {self.path or self.expression}"


def scan(root: Path, excludes: Iterable[str] = DEFAULT_EXCLUDES) -> list[FrontendCall]:
    """Tous les appels vers l'API des fichiers ``.js`` et ``.html`` sous ``root``, sauf ceux des
    chemins (relatifs à ``root``) qui correspondent à l'un des motifs ``excludes``. Un appel dont
    l'URL littérale ne vise pas ``/api/`` (une feuille de style, une page) n'est pas retenu."""
    calls: list[FrontendCall] = []
    for path in sorted([*root.rglob("*.js"), *root.rglob("*.html")]):
        relative = path.relative_to(root).as_posix()
        if any(fnmatch.fnmatch(relative, pattern) for pattern in excludes):
            continue
        source = path.read_text(encoding="utf-8")
        if path.suffix == ".html":
            source = _inline_scripts_only(source)
        calls.extend(_calls_in(relative, _without_comments(source)))
    return calls


def openapi_routes(app: Any) -> dict[str, set[str]]:
    """``{chemin: {méthodes}}`` de l'application - lu dans ``app.openapi()`` plutôt que dans
    ``app.routes``, qui ne liste pas à plat les routes des routeurs inclus selon la version de FastAPI."""
    return {path: {method.upper() for method in operations} for path, operations in app.openapi()["paths"].items()}


def matching_route(method: str, path: str, routes: dict[str, set[str]]) -> str | None:
    """La route (un chemin d'``openapi_routes``) qu'un appel ``method path`` atteint, ou ``None``.
    Un segment de route ``{nom}`` accepte n'importe quel segment ; un segment littéral doit être
    identique, :data:`PARAM` compris (un segment variable du front n'atteint pas un littéral)."""
    segments = path.strip("/").split("/")
    for route, methods in routes.items():
        if method not in methods:
            continue
        route_segments = route.strip("/").split("/")
        if len(route_segments) == len(segments) and all(
            (r.startswith("{") and r.endswith("}") and s) or r == s for r, s in zip(route_segments, segments)
        ):
            return route
    return None


# -- lexeur ---------------------------------------------------------------------------------------


def _inline_scripts_only(html: str) -> str:
    """Le HTML réduit à ses ``<script>`` en ligne : le reste devient des blancs (sauts de ligne
    gardés, pour que les numéros de ligne restent ceux du fichier)."""
    kept = [" " if c != "\n" else c for c in html]
    for match in _INLINE_SCRIPT_RE.finditer(html):
        kept[match.start(1) : match.end(1)] = match.group(1)
    return "".join(kept)


def _skip_string(source: str, i: int) -> int:
    quote, i = source[i], i + 1
    while i < len(source) and source[i] != quote and source[i] != "\n":
        i += 2 if source[i] == "\\" else 1
    return i + 1


def _skip_template(source: str, i: int) -> int:
    i += 1
    while i < len(source):
        if source[i] == "\\":
            i += 2
        elif source[i] == "`":
            return i + 1
        elif source.startswith("${", i):
            i = _skip_code_to_closing_brace(source, i + 2)
        else:
            i += 1
    return i


def _skip_code_to_closing_brace(source: str, i: int) -> int:
    depth = 0
    while i < len(source):
        c = source[i]
        if c in "\"'":
            i = _skip_string(source, i)
            continue
        if c == "`":
            i = _skip_template(source, i)
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            if depth == 0:
                return i + 1
            depth -= 1
        i += 1
    return i


def _skip_regex(source: str, i: int) -> int:
    i += 1
    in_class = False
    while i < len(source) and source[i] != "\n":
        c = source[i]
        if c == "\\":
            i += 2
            continue
        if c == "[":
            in_class = True
        elif c == "]":
            in_class = False
        elif c == "/" and not in_class:
            return i + 1
        i += 1
    return i


def _blank(chars: list[str], start: int, end: int) -> int:
    chars[start:end] = [c if c == "\n" else " " for c in chars[start:end]]
    return end


def _without_comments(source: str) -> str:
    """``source`` dont les commentaires sont remplacés par des blancs (mêmes positions, mêmes
    lignes) - pour qu'un ``fetch()`` cité dans un commentaire ne compte pas comme un appel."""
    out = list(source)
    i, last = 0, ""
    while i < len(source):
        c = source[i]
        if c in "\"'":
            i, last = _skip_string(source, i), c
        elif c == "`":
            i, last = _skip_template(source, i), c
        elif source.startswith("//", i):
            end = source.find("\n", i)
            i = _blank(out, i, len(source) if end < 0 else end)
        elif source.startswith("/*", i):
            end = source.find("*/", i + 2)
            i = _blank(out, i, len(source) if end < 0 else end + 2)
        elif c == "/" and (not last or last in _REGEX_PRECEDERS):
            i, last = _skip_regex(source, i), c
        else:
            if not c.isspace():
                last = c
            i += 1
    return "".join(out)


def _split_top_level(text: str, separators: str) -> tuple[list[str], int]:
    """Coupe ``text`` sur les ``separators`` hors parenthèses/crochets/accolades/chaînes, jusqu'à
    une fermante qui n'a pas été ouverte (la fin des arguments d'un appel). Renvoie les morceaux et
    la position de cette fermante (``len(text)`` s'il n'y en a pas)."""
    parts, depth, start, i = [], 0, 0, 0
    while i < len(text):
        c = text[i]
        if c in "\"'":
            i = _skip_string(text, i)
            continue
        if c == "`":
            i = _skip_template(text, i)
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            if depth == 0:
                break
            depth -= 1
        elif c in separators and depth == 0:
            parts.append(text[start:i])
            start = i + 1
        i += 1
    parts.append(text[start:i])
    return parts, i


def _literal_text(operand: str) -> str | None:
    """Le texte d'un opérande qui est entièrement une chaîne ou un gabarit (chaque ``${...}``
    devient :data:`PARAM`), ``None`` sinon."""
    operand = operand.strip()
    if len(operand) >= 2 and operand[0] in "\"'" and _skip_string(operand, 0) == len(operand):
        return operand[1:-1]
    if len(operand) >= 2 and operand[0] == "`" and _skip_template(operand, 0) == len(operand):
        text, i = [], 1
        while i < len(operand) - 1:
            if operand.startswith("${", i):
                text.append(PARAM)
                i = _skip_code_to_closing_brace(operand, i + 2)
            else:
                text.append(operand[i])
                i += 1
        return "".join(text)
    return None


def _url_of(argument: str) -> tuple[bool, str | None]:
    """``(est_littérale, url)`` du premier argument d'un appel : l'URL d'une concaténation qui
    commence par un texte littéral (opérandes non littéraux remplacés par :data:`PARAM`), sinon
    ``(False, None)`` - un gabarit qui commence par ``${...}`` (```${base}/wafers```) est dynamique."""
    operands, _ = _split_top_level(argument, "+")
    texts = [_literal_text(operand) for operand in operands]
    if texts[0] is None or texts[0].startswith(PARAM):
        return False, None
    return True, "".join(PARAM if text is None else text for text in texts)


def _calls_in(relative: str, code: str) -> list[FrontendCall]:
    calls = []
    for match in _CALL_RE.finditer(code):
        arguments, _ = _split_top_level(code[match.end() :], ",")
        if not arguments[0].strip():
            continue
        literal, url = _url_of(arguments[0])
        if literal and not url.startswith(API_PREFIX):
            continue  # une page, une feuille de style... pas l'API
        helper = match.group(1)
        if helper in METHODS:
            method = METHODS[helper]
        else:
            option = _METHOD_OPTION_RE.search(arguments[1]) if len(arguments) > 1 else None
            method = option.group(1).upper() if option else "GET"
        calls.append(
            FrontendCall(
                file=relative,
                line=code.count("\n", 0, match.start()) + 1,
                method=method,
                expression=" ".join(arguments[0].split()),
                path=re.split(r"[?#]", url, maxsplit=1)[0] if literal else None,
            )
        )
    return calls
