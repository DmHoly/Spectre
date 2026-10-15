"""Les routes de page du plugin PRISM : ``/prism`` s'ouvre sur sa première section, et l'ancienne
adresse de la page Data (``/donnees``, ``/donnees/{key}``) renvoie vers la nouvelle, requête comprise
(``?wafers=`` d'un lien enregistré). Pas d'API : le catalogue se lit chez ``characterization``."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

page_router = APIRouter()

FIRST_SECTION = "/prism/donnees"


def _with_query(request: Request, path: str) -> RedirectResponse:
    query = request.url.query
    return RedirectResponse(f"{path}?{query}" if query else path, status_code=302)


@page_router.get("/prism", include_in_schema=False)
def prism_home() -> RedirectResponse:
    """PRISM s'ouvre sur sa première section."""
    return RedirectResponse(FIRST_SECTION, status_code=302)


@page_router.get("/donnees", include_in_schema=False)
def legacy_data_home(request: Request) -> RedirectResponse:
    return _with_query(request, FIRST_SECTION)


@page_router.get("/donnees/{key}", include_in_schema=False)
def legacy_data_type(key: str, request: Request) -> RedirectResponse:
    return _with_query(request, f"{FIRST_SECTION}/{quote(key, safe='')}")
