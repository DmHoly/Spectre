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
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ..core.db import init_db
from . import auth as auth_router
from . import experiments as experiments_router
from . import projects as projects_router
from . import structures as structures_router

STATIC_DIR = Path(__file__).parent / "static"


def create_app() -> FastAPI:
    init_db()

    app = FastAPI(title="Spectre", docs_url=None, redoc_url=None)

    app.include_router(auth_router.router)
    app.include_router(projects_router.router)
    app.include_router(structures_router.router)
    app.include_router(experiments_router.router)

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    def _page(filename: str):
        def handler() -> FileResponse:
            return FileResponse(STATIC_DIR / filename)

        return handler

    app.get("/")(_page("index.html"))
    app.get("/connexion")(_page("connexion.html"))
    app.get("/inscription")(_page("inscription.html"))
    app.get("/mot-de-passe-oublie")(_page("mot-de-passe-oublie.html"))
    app.get("/reinitialiser")(_page("reinitialiser.html"))
    app.get("/profil")(_page("profil.html"))
    app.get("/docs")(_page("docs.html"))
    app.get("/docs/guide")(_page("docs-guide.html"))
    app.get("/docs/exemples")(_page("docs-exemples.html"))
    app.get("/docs/architecture")(_page("docs-architecture.html"))
    app.get("/projets/{slug}")(_page("projet.html"))
    app.get("/projets/{slug}/structures/nouvelle")(_page("structure-builder.html"))
    app.get("/projets/{slug}/experiences/{experience_id}/evoluer")(_page("structure-builder.html"))
    app.get("/projets/{slug}/experiences/{experience_id}")(_page("experience.html"))
    app.get("/projets/{slug}/graphe")(_page("graphe.html"))

    return app


app = create_app()
