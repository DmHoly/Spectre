"""Chaque appel du front (le noyau et les plugins) vers l'API vise une route qui existe - vérifié sans
navigateur, sur le texte des pages (voir :mod:`contracts.frontend_calls`). C'est ce qui rend un
renommage de routes vérifiable : une URL oubliée côté front fait échouer ce test au lieu de ne
répondre 404 qu'en production.

Les appels dont l'URL est une variable ne se lisent pas tels quels : chacun est listé ci-dessous
(fichier, méthode, expression telle qu'écrite) avec la ou les routes qu'il atteint, et la liste
elle-même est vérifiée dans les deux sens - une entrée qui ne correspond plus à aucun appel, ou un
nouvel appel dynamique qui n'y figure pas, fait échouer le test. Ce que DYNAMIC_CALLS affirme n'est
pas lu dans le JS : c'est :func:`contracts.frontend_calls.scan_urls` qui vérifie, elle, chaque URL
``/api/...`` écrite dans le front (une variable, un ``src``, un retour de fonction compris) - une
route renommée dans DYNAMIC_CALLS mais pas dans le JS y fait échouer le test.
"""

from __future__ import annotations

from contracts.frontend_calls import matching_route, openapi_routes, scan, scan_urls

_EXP = "/api/microprojets/{slug}/experiences"
_LOT = "/api/lots/{code}"
_AREA = "/api/management/{slug}"

# (fichier, méthode, expression de l'URL) -> les routes (chemins OpenAPI) qu'elle peut désigner.
DYNAMIC_CALLS: dict[tuple[str, str, str], tuple[str, ...]] = {
    # notebookChange(method, path, body) : url = `${...}/cahier${path}`, path "" ou "/<id de la vue>"
    ("plugins/notebook/static/notebook.js", "POST", "url"): (f"{_EXP}/{{ref}}/cahier",),
    ("plugins/notebook/static/notebook.js", "PUT", "url"): (f"{_EXP}/{{ref}}/cahier/{{entry_id}}",),
    ("plugins/notebook/static/notebook.js", "DELETE", "url"): (f"{_EXP}/{{ref}}/cahier/{{entry_id}}",),
    # « Comparer » : la même expérience du µprojet ou celle d'un autre µprojet
    ("plugins/experiments/static/experiment.js", "GET", "endpoint"): (f"{_EXP}/{{ref}}/diff", f"{_EXP}/{{ref}}/diff-externe"),
    # le rapport embarque ses images (img[src^='/api/']) : pièces jointes et galerie DATA
    ("plugins/experiments/static/experiment.js", "GET", "src"): ("/api/microprojets/{slug}/pieces-jointes/{attachment_id}", "/api/microprojets/{slug}/data/image"),
    # uploadStructureImage(slug, file, url) : une image de structure, ou (uploadUrl de la preuve) une image collée
    ("plugins/attachments/static/image-drop.js", "POST", "url || `/api/microprojets/${encodeURIComponent(slug)}/structures/images`"): (
        "/api/microprojets/{slug}/structures/images",
        "/api/microprojets/{slug}/images",
    ),
    # KpiTrendBlock, monté par area.js avec kpisUrl / seriesUrl = `${areaUrl}/tendances[/clé]`
    ("plugins/kpis/static/kpi-trend.js", "GET", "opts.kpisUrl"): (f"{_AREA}/tendances",),
    ("plugins/kpis/static/kpi-trend.js", "GET", "opts.seriesUrl(key, months, variant)"): (f"{_AREA}/tendances/{{kpi_key}}",),
    # lot.js : lotApi = `/api/lots/${code}`
    ("plugins/lots/static/lot.js", "GET", "lotApi"): (_LOT,),
    ("plugins/lots/static/lot.js", "PUT", "lotApi"): (_LOT,),
    ("plugins/lots/static/lot.js", "DELETE", "lotApi"): (_LOT,),
    ("plugins/lots/static/lot.js", "POST", "`${lotApi}/wafers`"): (f"{_LOT}/wafers",),
    ("plugins/lots/static/lot.js", "DELETE", "`${lotApi}/wafers/${encodeURIComponent(lasermark)}`"): (f"{_LOT}/wafers/{{lasermark}}",),
    ("plugins/lots/static/lot.js", "PUT", "`${lotApi}/thematiques`"): (f"{_LOT}/thematiques",),
    # area.js : areaUrl = `/api/management/${slug}`
    ("plugins/areas/static/area.js", "GET", "areaUrl"): (_AREA,),
    ("plugins/areas/static/area.js", "PUT", "areaUrl"): (_AREA,),
    ("plugins/areas/static/area.js", "DELETE", "areaUrl"): (_AREA,),
    ("plugins/areas/static/area.js", "POST", "`${areaUrl}/objectifs`"): (f"{_AREA}/objectifs",),
    ("plugins/areas/static/area.js", "PUT", "`${areaUrl}/objectifs/${o.id}`"): (f"{_AREA}/objectifs/{{objective_id}}",),
    ("plugins/areas/static/area.js", "DELETE", "`${areaUrl}/objectifs/${o.id}`"): (f"{_AREA}/objectifs/{{objective_id}}",),
    ("plugins/areas/static/area.js", "POST", "`${areaUrl}/thematiques`"): (f"{_AREA}/thematiques",),
    ("plugins/areas/static/area.js", "PUT", "`${areaUrl}/thematiques/${encodeURIComponent(t.slug)}`"): (f"{_AREA}/thematiques/{{thematique_slug}}",),
    ("plugins/areas/static/area.js", "DELETE", "`${areaUrl}/thematiques/${encodeURIComponent(t.slug)}`"): (f"{_AREA}/thematiques/{{thematique_slug}}",),
    ("plugins/areas/static/area.js", "POST", "`${areaUrl}/microprojets`"): (f"{_AREA}/microprojets",),
    ("plugins/areas/static/area.js", "GET", "`${areaUrl}/tendances/${encodeURIComponent(kpiKey)}/etudes/${encodeURIComponent(studyId)}`"): (
        f"{_AREA}/tendances/{{kpi_key}}/etudes/{{study_id}}",
    ),
    # thematic.js : thematicUrl = `/api/management/${area}/thematiques/${thematique}`
    ("plugins/areas/static/thematic.js", "GET", "thematicUrl"): (f"{_AREA}/thematiques/{{thematique_slug}}",),
    # le constructeur : une campagne, une évolution ou un lancement
    ("plugins/structures/static/builder/experience-launch.js", "POST", "endpoint"): (f"{_EXP}/campagne", f"{_EXP}/{{ref}}/evoluer", _EXP),
    # la structure en images : une évolution ou un lancement
    ("plugins/structures/static/image-structure.js", "POST", "endpoint"): (f"{_EXP}/{{ref}}/evoluer-image", f"{_EXP}/image"),
}

# Appels dynamiques qui ne visent pas une route de Spectre.
NOT_ROUTE_CALLS: dict[tuple[str, str, str], str] = {
    ("kernel/static/api.js", "GET", "path"): "le client HTTP lui-même : chaque api.* est vérifié là où il est appelé",
    ("plugins/experiments/static/experiment.js", "GET", "mount.dataset.url"): "graph_config.data_source_url : un service de données externe",
}


def test_the_scanner_sees_the_frontend_calls():
    # garde-fou : un lexeur cassé ne trouverait rien, et tout le reste passerait sans rien vérifier
    calls = scan()
    assert len([c for c in calls if c.path]) > 100
    assert any(c.file.endswith(".html") for c in calls)


def test_every_literal_frontend_call_targets_an_existing_route(app):
    routes = openapi_routes(app)
    dead = [str(call) for call in scan() if call.path and matching_route(call.method, call.path, routes) is None]
    assert not dead, "Appels du front vers une route qui n'existe pas :\n  " + "\n  ".join(dead)


def test_every_api_url_written_in_the_frontend_targets_an_existing_route(app):
    # sans méthode : une URL rangée dans une variable sert parfois à plusieurs (lotApi : GET, PUT, DELETE)
    routes = openapi_routes(app)
    urls = scan_urls()
    assert len(urls) > len([c for c in scan() if c.path])  # garde-fou : celles des appels, et les autres
    dead = [str(url) for url in urls if matching_route(None, url.path, routes) is None]
    assert not dead, "URL du front vers une route qui n'existe pas :\n  " + "\n  ".join(dead)


def test_every_dynamic_frontend_call_is_listed_and_targets_existing_routes(app):
    routes = openapi_routes(app)
    dynamic = {(call.file, call.method, call.expression): call for call in scan() if call.path is None}
    listed = DYNAMIC_CALLS.keys() | NOT_ROUTE_CALLS.keys()

    unlisted = [str(call) for key, call in dynamic.items() if key not in listed]
    stale = [" ".join(key) for key in listed if key not in dynamic]
    dead = [
        f"{file} {method} {expression} -> {route}"
        for (file, method, expression), targets in DYNAMIC_CALLS.items()
        for route in targets
        if method not in routes.get(route, set())
    ]
    problems = []
    if unlisted:
        problems.append("Appels à URL variable absents de DYNAMIC_CALLS :\n  " + "\n  ".join(unlisted))
    if stale:
        problems.append("Entrées qui ne correspondent plus à aucun appel du front :\n  " + "\n  ".join(stale))
    if dead:
        problems.append("Entrées de DYNAMIC_CALLS vers une route qui n'existe pas :\n  " + "\n  ".join(dead))
    assert not problems, "\n".join(problems)
