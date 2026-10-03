"""Extraction statique des appels HTTP du front vers l'API : chaque ``api.get/post/put/patch/del/upload``
et ``api.request`` (``kernel/static/api.js``) et chaque ``fetch`` du front (``static/`` du noyau,
``static/`` et ``pages/`` de chaque plugin), avec la méthode et le chemin qu'il vise - sans navigateur
ni interpréteur JavaScript. Les URL de l'API ne s'écrivent que dans le ``static/client.js`` de chaque
plugin (``ARCHITECTURE.md`` § 1) : :func:`scan_clients` y lit chaque fonction (son nom, sa méthode,
son gabarit d'URL), :func:`scan_client_uses` relève les appels ``<plugin>Api.<fonction>(`` du reste
du front, et :func:`scan_api_strings` toute chaîne ``/api/`` écrite ailleurs. Un petit lexeur sait seulement ce que sont un commentaire, une chaîne, un
gabarit (`...${...}...`) et une expression régulière littérale : de quoi lire les arguments d'un appel.

Le chemin d'un appel est connu quand son URL commence par un littéral (éventuellement passé à
``api.withQuery(url, params)``) : chaque ``${...}`` (et chaque opérande non littéral d'une
concaténation) devient le segment générique :data:`PARAM`, la query string est retirée. Sinon - une variable, une expression - l'appel est « dynamique » : ``path`` vaut
``None``, et c'est à l'appelant de dire, par une liste explicite, quelle route il vise.

Une URL rangée dans une variable (``const areaUrl = `/api/...```), passée en ``src`` ou renvoyée par
une fonction n'est pas un appel : :func:`scan_urls` relève, elle, chaque URL ``/api/...`` écrite
dans une chaîne ou un gabarit, où qu'elle soit, sans méthode. Un gabarit qui commence par une
variable affectée d'une telle URL dans le même fichier (```${areaUrl}/objectifs```) est lu avec elle.
:func:`scan_static_urls` relève de même chaque chemin ``/static/...`` écrit en dur.
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

PARAM = "{param}"
API_PREFIX = "/api/"

SPECTRE_DIR = Path(__file__).resolve().parents[2] / "spectre"
# Le front, relatif à SPECTRE_DIR : celui du noyau, puis les statiques et les pages de chaque plugin.
DEFAULT_INCLUDES = ("kernel/static/*", "plugins/*/static/*", "plugins/*/pages/*")
# Les bibliothèques embarquées et le plugin docs (dont les pages citent des appels en exemple).
DEFAULT_EXCLUDES = ("kernel/static/vendor/*", "plugins/docs/*")

METHODS = {"get": "GET", "post": "POST", "put": "PUT", "patch": "PATCH", "del": "DELETE", "upload": "POST"}

_CALL_RE = re.compile(r"(?<![\w$.])(?:api\s*\.\s*(get|post|put|patch|del|upload|request)|fetch)\s*\(")
_WITH_QUERY_RE = re.compile(r"^api\s*\.\s*withQuery\s*\(")
CLIENT_FILE = "client.js"
# Le client d'un plugin : « const <plugin>Api = { ... }; » ; chaque fonction, une méthode de l'objet.
_CLIENT_GLOBAL_RE = re.compile(r"^const\s+([A-Za-z_$][\w$]*)\s*=\s*\{", re.M)
_CLIENT_METHOD_RE = re.compile(r"^  ([A-Za-z_$][\w$]*)\s*\(([^)]*)\)\s*\{", re.M)
_CLIENT_USE_RE = re.compile(r"(?<![\w$.])([a-z][A-Za-z]*Api)\s*\.\s*([A-Za-z_$][\w$]*)\s*\(")
_METHOD_OPTION_RE = re.compile(r"""\bmethod\s*:\s*["'`](\w+)["'`]""")
_INLINE_SCRIPT_RE = re.compile(r"<script\b(?![^>]*\bsrc=)[^>]*>(.*?)</script>", re.DOTALL | re.IGNORECASE)
# Une URL de l'API dans le texte d'un littéral : en tête, ou après un guillemet, un « = »... (le
# ``src="/api/..."`` d'un gabarit HTML) ; un préfixe nu (``a[href^='/api/']``) n'en est pas une.
_URL_IN_TEXT_RE = re.compile(r"(?<![\w$.}/])/api/[^\s\"'`<>?#()]+")
_STATIC_IN_TEXT_RE = re.compile(r"(?<![\w$.}/])/static/[^\s\"'`<>?#()]+")
# ``nom = <littéral>`` : une déclaration ou une affectation, pas une comparaison ni une flèche.
_ASSIGNMENT_RE = re.compile(r"(?<![\w$.])([A-Za-z_$][\w$]*)\s*=(?![=>])\s*")
_LEADING_NAME_RE = re.compile(r"`\$\{\s*([A-Za-z_$][\w$]*)\s*\}")
# Après l'un de ces caractères, un « / » ouvre une expression régulière, pas une division.
_REGEX_PRECEDERS = set("(,=:[!&|?{};+-*%<>~^")


@dataclass(frozen=True)
class FrontendCall:
    file: str  # relatif au dossier scanné (SPECTRE_DIR), en notation POSIX
    line: int
    method: str
    expression: str  # le premier argument tel qu'écrit (espaces réduits)
    path: str | None  # "/api/..." avec PARAM pour chaque partie variable ; None si l'URL est dynamique

    def __str__(self) -> str:
        return f"{self.file}:{self.line} {self.method} {self.path or self.expression}"


@dataclass(frozen=True)
class FrontendUrl:
    file: str  # relatif au dossier scanné (SPECTRE_DIR), en notation POSIX
    line: int
    path: str  # "/api/..." (ou "/static/...") avec PARAM pour chaque partie variable, sans la query string

    def __str__(self) -> str:
        return f"{self.file}:{self.line} {self.path}"


def scan(
    root: Path = SPECTRE_DIR, includes: Iterable[str] = DEFAULT_INCLUDES, excludes: Iterable[str] = DEFAULT_EXCLUDES
) -> list[FrontendCall]:
    """Tous les appels vers l'API des fichiers ``.js`` et ``.html`` sous ``root`` dont le chemin
    (relatif à ``root``) correspond à l'un des motifs ``includes`` et à aucun des motifs
    ``excludes``. Un appel dont l'URL littérale ne vise pas ``/api/`` (une feuille de style, une
    page) n'est pas retenu."""
    calls: list[FrontendCall] = []
    for relative, code in _sources(root, includes, excludes):
        calls.extend(_calls_in(relative, code))
    return calls


def scan_urls(
    root: Path = SPECTRE_DIR, includes: Iterable[str] = DEFAULT_INCLUDES, excludes: Iterable[str] = DEFAULT_EXCLUDES
) -> list[FrontendUrl]:
    """Chaque URL ``/api/...`` écrite dans une chaîne ou un gabarit des mêmes fichiers que
    :func:`scan` - qu'elle serve à un appel, à une variable, à un ``src`` ou à un lien."""
    urls: list[FrontendUrl] = []
    for relative, code in _sources(root, includes, excludes):
        urls.extend(_urls_in(relative, code))
    return urls


def scan_static_urls(
    root: Path = SPECTRE_DIR, includes: Iterable[str] = DEFAULT_INCLUDES, excludes: Iterable[str] = DEFAULT_EXCLUDES
) -> list[FrontendUrl]:
    """Chaque chemin ``/static/...`` écrit en dur dans une chaîne ou un gabarit des mêmes fichiers
    que :func:`scan` (la feuille de style que le rapport d'une expérience embarque, par exemple).
    Un chemin dont une partie est variable (``${...}``) n'est pas retenu : il ne désigne aucun
    fichier précis."""
    urls: list[FrontendUrl] = []
    for relative, code in _sources(root, includes, excludes):
        for start, end in _literal_spans(code):
            text = _literal_text(code[start:end]) or ""
            line = code.count("\n", 0, start) + 1
            urls += [
                FrontendUrl(relative, line + text.count("\n", 0, m.start()), m.group(0))
                for m in _STATIC_IN_TEXT_RE.finditer(text)
                if PARAM not in m.group(0)
            ]
    return urls


def openapi_routes(app: Any) -> dict[str, set[str]]:
    """``{chemin: {méthodes}}`` de l'application - lu dans ``app.openapi()`` plutôt que dans
    ``app.routes``, qui ne liste pas à plat les routes des routeurs inclus selon la version de FastAPI."""
    return {path: {method.upper() for method in operations} for path, operations in app.openapi()["paths"].items()}


def matching_route(method: str | None, path: str, routes: dict[str, set[str]]) -> str | None:
    """La route (un chemin d'``openapi_routes``) qu'un appel ``method path`` atteint, ou ``None`` ;
    ``method=None`` accepte n'importe quelle méthode. Un segment de route ``{nom}`` accepte
    n'importe quel segment ; un segment littéral doit être identique, :data:`PARAM` compris (un
    segment variable du front n'atteint pas un littéral)."""
    segments = path.strip("/").split("/")
    for route, methods in routes.items():
        if method is not None and method not in methods:
            continue
        route_segments = route.strip("/").split("/")
        if len(route_segments) == len(segments) and all(
            (r.startswith("{") and r.endswith("}") and s) or r == s for r, s in zip(route_segments, segments)
        ):
            return route
    return None


# -- lexeur ---------------------------------------------------------------------------------------


def _sources(root: Path, includes: Iterable[str], excludes: Iterable[str]) -> Iterable[tuple[str, str]]:
    """``(chemin relatif, code sans commentaires)`` de chaque ``.js`` et ``.html`` retenu sous
    ``root`` - un HTML réduit à ses scripts en ligne."""
    for path in sorted([*root.rglob("*.js"), *root.rglob("*.html")]):
        relative = path.relative_to(root).as_posix()
        if not any(fnmatch.fnmatch(relative, pattern) for pattern in includes):
            continue
        if any(fnmatch.fnmatch(relative, pattern) for pattern in excludes):
            continue
        source = path.read_text(encoding="utf-8")
        if path.suffix == ".html":
            source = _inline_scripts_only(source)
        yield relative, _without_comments(source)


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
    with_query = _WITH_QUERY_RE.match(argument.strip())
    if with_query:
        inner, _ = _split_top_level(argument.strip()[with_query.end() :], ",")
        return _url_of(inner[0])
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


def _literal_spans(code: str, start: int = 0, end: int | None = None) -> Iterable[tuple[int, int]]:
    """``(début, fin)`` de chaque chaîne et de chaque gabarit de ``code[start:end]``, y compris ceux
    écrits dans le ``${...}`` d'un gabarit (donnés juste après lui)."""
    end = len(code) if end is None else end
    i, last = start, ""
    while i < end:
        c = code[i]
        if c in "\"'":
            stop = _skip_string(code, i)
            yield i, stop
            i, last = stop, c
        elif c == "`":
            stop = _skip_template(code, i)
            yield i, stop
            j = i + 1
            while j < stop:
                if code[j] == "\\":
                    j += 2
                elif code.startswith("${", j):
                    closing = _skip_code_to_closing_brace(code, j + 2)
                    yield from _literal_spans(code, j + 2, closing - 1)
                    j = closing
                else:
                    j += 1
            i, last = stop, c
        elif c == "/" and (not last or last in _REGEX_PRECEDERS):
            i, last = _skip_regex(code, i), c
        else:
            if not c.isspace():
                last = c
            i += 1


def _api_urls(code: str, start: int, end: int) -> list[tuple[int, str]]:
    """``(ligne, chemin)`` de chaque URL ``/api/...`` du littéral ``code[start:end]``. Une URL qui
    finit le littéral et qu'un ``+`` prolonge (autrement que par une query) se termine par
    :data:`PARAM` : le chemin continue avec l'opérande suivant. Un :data:`PARAM` final collé à un
    segment (```.../cahier${path}```, ``path`` vide ou ``"/<id>"``) est un suffixe inconnu : le
    chemin s'arrête avant lui."""
    text = _literal_text(code[start:end]) or ""
    line = code.count("\n", 0, start) + 1
    matches = list(_URL_IN_TEXT_RE.finditer(text))
    urls = [(line + text.count("\n", 0, m.start()), m.group(0)) for m in matches]
    if matches and matches[-1].end() == len(text):
        rest = code[end:].lstrip()
        following = rest[1:].lstrip() if rest.startswith("+") else None
        if following is not None and not (following[:1] in "\"'`" and following[1:2] in ("?", "#")):
            urls[-1] = (urls[-1][0], urls[-1][1] + PARAM)
    return [(line, _without_glued_suffix(url)) for line, url in urls]


def _without_glued_suffix(path: str) -> str:
    if path.endswith(PARAM) and not path.endswith("/" + PARAM):
        return path[: -len(PARAM)]
    return path


def _urls_in(relative: str, code: str) -> list[FrontendUrl]:
    spans = dict(_literal_spans(code))
    found = {start: _api_urls(code, start, end) for start, end in spans.items()}
    # les variables affectées d'une URL de l'API (en tête du littéral), pour lire ```${nom}/suite```
    assigned: dict[str, set[str]] = {}
    for match in _ASSIGNMENT_RE.finditer(code):
        start = match.end()
        if found.get(start) and (_literal_text(code[start : spans[start]]) or "").startswith(API_PREFIX):
            assigned.setdefault(match.group(1), set()).add(found[start][0][1])

    urls = []
    for start, end in spans.items():
        urls += [FrontendUrl(relative, line, path) for line, path in found[start]]
        leading = _LEADING_NAME_RE.match(code, start)
        if leading and leading.group(1) in assigned:
            rest = (_literal_text(code[start:end]) or "")[len(PARAM) :]
            tail = re.match(r"[^\s\"'`<>?#()]*", rest).group(0)
            line = code.count("\n", 0, start) + 1
            urls += [FrontendUrl(relative, line, _without_glued_suffix(base + tail)) for base in sorted(assigned[leading.group(1)])]
    return urls


# -- les clients des plugins ------------------------------------------------------------------------


@dataclass(frozen=True)
class ClientFunction:
    file: str  # plugins/<plugin>/static/client.js
    line: int
    plugin: str
    client: str  # le global déclaré (lotsApi)
    name: str  # la fonction (get)
    method: str | None  # None : la fonction renvoie une URL (une <img src>), elle n'appelle rien
    path: str | None  # "/api/..." avec PARAM pour chaque partie variable

    def __str__(self) -> str:
        return f"{self.file}:{self.line} {self.client}.{self.name} -> {self.method or 'URL'} {self.path}"


@dataclass(frozen=True)
class ClientUse:
    file: str
    line: int
    client: str
    name: str

    def __str__(self) -> str:
        return f"{self.file}:{self.line} {self.client}.{self.name}()"


def client_files(root: Path = SPECTRE_DIR) -> list[Path]:
    return sorted(root.glob(f"plugins/*/static/{CLIENT_FILE}"))


def client_globals(path: Path) -> list[str]:
    """Les noms déclarés au premier niveau d'un ``client.js`` (il ne doit y en avoir qu'un)."""
    code = _without_comments(path.read_text(encoding="utf-8"))
    return re.findall(r"^(?:const|let|var|function|class)\s+([A-Za-z_$][\w$]*)", code, re.M)


def scan_clients(root: Path = SPECTRE_DIR) -> list[ClientFunction]:
    """Chaque fonction du client de chaque plugin, avec la méthode et le chemin de l'appel qu'elle
    fait - ou, pour une fonction qui renvoie une URL, ce chemin sans méthode."""
    functions: list[ClientFunction] = []
    for path in client_files(root):
        relative = path.relative_to(root).as_posix()
        plugin = path.parent.parent.name
        code = _without_comments(path.read_text(encoding="utf-8"))
        declared = _CLIENT_GLOBAL_RE.search(code)
        client = declared.group(1) if declared else ""
        methods = list(_CLIENT_METHOD_RE.finditer(code))
        for i, match in enumerate(methods):
            end = methods[i + 1].start() if i + 1 < len(methods) else len(code)
            # le corps de la fonction seul, aux mêmes positions (pour les numéros de ligne)
            body = re.sub(r"[^\n]", " ", code[: match.end()]) + code[match.end() : end]
            line = code.count("\n", 0, match.start()) + 1
            calls = [c for c in _calls_in(relative, body) if c.path]
            if calls:
                functions += [ClientFunction(relative, line, plugin, client, match.group(1), c.method, c.path) for c in calls]
                continue
            urls = _urls_in(relative, body)
            functions += [ClientFunction(relative, line, plugin, client, match.group(1), None, u.path) for u in urls] or [
                ClientFunction(relative, line, plugin, client, match.group(1), None, None)
            ]
    return functions


def scan_client_uses(
    root: Path = SPECTRE_DIR, includes: Iterable[str] = DEFAULT_INCLUDES, excludes: Iterable[str] = DEFAULT_EXCLUDES
) -> list[ClientUse]:
    """Chaque appel ``<plugin>Api.<fonction>(`` du front."""
    uses = []
    for relative, code in _sources(root, includes, excludes):
        uses += [ClientUse(relative, code.count("\n", 0, m.start()) + 1, m.group(1), m.group(2)) for m in _CLIENT_USE_RE.finditer(code)]
    return uses


def scan_api_strings(
    root: Path = SPECTRE_DIR, includes: Iterable[str] = DEFAULT_INCLUDES, excludes: Iterable[str] = DEFAULT_EXCLUDES
) -> list[FrontendUrl]:
    """Chaque chaîne ou gabarit du front qui contient ``/api/`` (une URL, un préfixe de sélecteur...),
    et chaque ``/api/`` du balisage d'une page (hors commentaires et scripts, lus à part)."""
    found = []
    for relative, code in _sources(root, includes, excludes):
        for start, end in _literal_spans(code):
            text = _literal_text(code[start:end]) or code[start:end]
            if API_PREFIX in text:
                found.append(FrontendUrl(relative, code.count("\n", 0, start) + 1, " ".join(text.split())[:120]))
    blank = lambda m: re.sub(r"[^\n]", " ", m.group(0))  # noqa: E731
    for path in sorted(root.rglob("*.html")):
        relative = path.relative_to(root).as_posix()
        if not any(fnmatch.fnmatch(relative, p) for p in includes) or any(fnmatch.fnmatch(relative, p) for p in excludes):
            continue
        html = re.sub(r"<!--.*?-->", blank, path.read_text(encoding="utf-8"), flags=re.S)
        html = _INLINE_SCRIPT_RE.sub(blank, html)
        for m in re.finditer(re.escape(API_PREFIX), html):
            found.append(FrontendUrl(relative, html.count("\n", 0, m.start()) + 1, html[m.start() : m.start() + 80].split('"')[0]))
    return found
