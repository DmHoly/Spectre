"""The Spectre FastAPI application: a real multi-page site (each screen is its own HTML file and
URL, not a client-routed single shell - see ``static/*.html``) plus the JSON API backing it.

Deep domain logic never lives here: structure simulation comes from ``structureforge``, experiment
versioning/DOE/diffing/graphing come from ``follow``. This module (and the routers it wires
together) only adds what neither of those has: accounts, projects, permissions, and the pages that
tie them into one workflow.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from ..core.db import init_db
from . import atlas as atlas_router
from . import auth as auth_router
from . import experiments as experiments_router
from . import intent_forms as intent_forms_router
from . import links as links_router
from . import management as management_router
from . import projects as projects_router
from . import refs as refs_router
from . import structures as structures_router

STATIC_DIR = Path(__file__).parent / "static"


def create_app() -> FastAPI:
    init_db()

    app = FastAPI(title="Spectre", docs_url=None, redoc_url=None)

    app.include_router(auth_router.router)
    app.include_router(management_router.router)
    app.include_router(projects_router.router)
    app.include_router(structures_router.router)
    app.include_router(experiments_router.router)
    app.include_router(refs_router.router)
    app.include_router(intent_forms_router.router)
    app.include_router(atlas_router.router)
    app.include_router(links_router.router)

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.middleware("http")
    async def _revalidate_pages_and_assets(request, call_next):
        """The HTML pages and everything under ``/static`` are served straight from files that
        change on every deploy - tell the browser to revalidate (cheap: the responses already
        carry an ETag, so an unchanged file comes back 304) instead of serving a stale copy.
        Without this a JS/CSS/HTML change only shows after a manual hard-refresh.
        """
        response = await call_next(request)
        content_type = response.headers.get("content-type", "")
        if request.url.path.startswith("/static/") or content_type.startswith("text/html"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    def _page(filename: str):
        def handler() -> FileResponse:
            return FileResponse(STATIC_DIR / filename)

        return handler

    app.get("/")(_page("index.html"))
    app.get("/atlas")(_page("atlas.html"))
    app.get("/connexion")(_page("connexion.html"))
    app.get("/inscription")(_page("inscription.html"))
    app.get("/mot-de-passe-oublie")(_page("mot-de-passe-oublie.html"))
    app.get("/reinitialiser")(_page("reinitialiser.html"))
    app.get("/profil")(_page("profil.html"))
    app.get("/docs")(_page("docs.html"))
    app.get("/docs/guide")(_page("docs-guide.html"))
    app.get("/docs/exemples")(_page("docs-exemples.html"))
    app.get("/docs/architecture")(_page("docs-architecture.html"))
    app.get("/bibliotheque")(_page("bibliotheque.html"))
    app.get("/pilotage")(_page("pilotage.html"))
    app.get("/management/{slug}")(_page("management.html"))
    app.get("/microprojets/{slug}")(_page("projet.html"))
    app.get("/microprojets/{slug}/presets-etapes")(_page("presets.html"))
    app.get("/microprojets/{slug}/briques-technologiques")(_page("briques.html"))
    app.get("/microprojets/{slug}/briques-technologiques/bibliotheque/nouvelle")(_page("structure-builder.html"))
    app.get("/microprojets/{slug}/briques-technologiques/bibliotheque/{name}")(_page("structure-builder.html"))
    app.get("/microprojets/{slug}/structures/bibliotheque/nouvelle")(_page("structure-builder.html"))
    app.get("/microprojets/{slug}/structures/bibliotheque/{name}")(_page("structure-builder.html"))
    app.get("/microprojets/{slug}/structures/nouvelle")(_page("structure-builder.html"))
    app.get("/microprojets/{slug}/experiences/{experience_id}/evoluer")(_page("structure-builder.html"))
    app.get("/microprojets/{slug}/experiences/{experience_id}")(_page("experience.html"))
    app.get("/microprojets/{slug}/graphe")(_page("graphe.html"))
    app.get("/microprojets/{slug}/refs")(_page("refs.html"))
    app.get("/microprojets/{slug}/formulaire-intention")(_page("formulaire-intention.html"))

    # "projet" was renamed to "µprojet" (URL: /microprojets) - keep old bookmarks working.
    @app.get("/projets/{rest:path}")
    def _legacy_projet_redirect(rest: str):
        return RedirectResponse(f"/microprojets/{rest}", status_code=308)

    return app


app = create_app()
