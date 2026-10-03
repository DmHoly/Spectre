"""Le graphe des imports respecte le contrat (``ARCHITECTURE.md`` § 1 et § 3), lu dans le code sans
l'exécuter : chaque ``import`` de ``spectre/kernel`` et ``spectre/plugins``, où qu'il soit écrit -
en tête de fichier ou dans une fonction (un import paresseux reste une dépendance).

- le noyau n'importe aucun plugin ;
- un plugin n'importe que les plugins de son ``depends_on`` (et ceux dont ils dépendent) ;
- un plugin n'importe jamais le module ``api`` d'un autre ;
- le domaine d'un plugin (tout module autre que ``api``, ``deps`` et ``schemas``) n'importe pas FastAPI.

Les exceptions encore permises sont listées ici, chacune avec ce qui la fera disparaître ; une entrée
qui ne correspond plus à aucun import fait échouer le test.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCANNED = (ROOT / "spectre" / "kernel", ROOT / "spectre" / "plugins")
HTTP_MODULES = {"api", "deps", "schemas"}


def _is_http_module(module: str) -> bool:
    """``api``, ``deps``, ``schemas`` - ou un routeur annexe ``<sujet>_api`` (microprojects.invitations_api)."""
    name = module.rsplit(".", 1)[-1]
    return name in HTTP_MODULES or name.endswith("_api")


# La racine de composition : create_app() lit la liste des plugins quand on ne lui en passe pas.
KERNEL_COMPOSITION_ROOT = ("spectre.kernel.app", "spectre.plugins")

# (module qui importe, module importé) -> ce qui supprimera l'import.
ALLOWED_TRANSITIONAL: dict[tuple[str, str], str] = {
    ("spectre.plugins.library.api", "spectre.plugins.microprojects.deps"): "GET /api/ui-texts/intention (sans µprojet)",
    ("spectre.plugins.library.api", "spectre.plugins.microprojects.service"): "GET /api/ui-texts/intention (sans µprojet)",
    ("spectre.plugins.library.service", "spectre.plugins.process_library.step_presets"): (
        "registre LibraryFile : process_library déclare ses fichiers presets.yml et briques.yml"
    ),
    ("spectre.plugins.library.service", "spectre.plugins.process_library.tech_bricks"): (
        "registre LibraryFile : process_library déclare ses fichiers presets.yml et briques.yml"
    ),
    ("spectre.plugins.areas.api", "spectre.plugins.microprojects.service"): (
        "GET /api/experiment-stats (agrégats par µprojet) et PATCH /api/microprojects/{mp} (rattachement)"
    ),
    ("spectre.plugins.areas.api", "spectre.plugins.experiments.repository"): "GET /api/experiment-stats?area=",
    ("spectre.plugins.areas.api", "spectre.plugins.experiments.lineage"): "GET /api/experiment-timeline?area=&thematic=",
    ("spectre.plugins.microprojects.api", "spectre.plugins.experiments.repository"): "GET /api/experiment-stats?microproject=",
    ("spectre.plugins.microprojects.api", "spectre.plugins.wafers.fdl"): "GET /api/wafers?fdl=",
    ("spectre.plugins.microprojects.api", "spectre.plugins.wafers.service"): "GET /api/wafers?fdl=",
    ("spectre.plugins.experiments.api", "spectre.plugins.evidence.service"): (
        "GET .../experiments/{exp}/evidence : la fiche ne porte plus les preuves"
    ),
    ("spectre.plugins.experiments.lineage", "spectre.plugins.lots.service"): (
        "GET /api/microprojects/{mp}/lineage sans badge de lot : le front compose les badges via lotsApi"
    ),
    ("spectre.plugins.wafers.api", "spectre.plugins.lots.service"): "GET /api/wafers/{wafer_key} sans les lots : le front appelle GET /api/lots?wafer=",
    ("spectre.plugins.kpis.service", "spectre.plugins.kpis_demo.service"): (
        "GET /api/areas/{area_slug}/kpis/{kpi_key} : kpis_demo enregistre lui-même son KPI (kpis.register)"
    ),
}

# Modules du domaine qui lèvent encore HTTPException -> ce qui la remplacera.
ALLOWED_FASTAPI: dict[str, str] = {
    "spectre.plugins.attachments.store": "uploaded_image lève InvalidInput (kernel.errors)",
    "spectre.plugins.structures.kinds": "structure_image_from_input lève InvalidInput (kernel.errors)",
    "spectre.plugins.experiments.service": (
        "require_branch_name, require_title_and_intent et form_validation_error lèvent InvalidInput, "
        "not_found devient NotFound (kernel.errors)"
    ),
}


def _module_name(path: Path) -> str:
    parts = path.relative_to(ROOT).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def _modules() -> dict[str, Path]:
    return {_module_name(path): path for root in SCANNED for path in sorted(root.rglob("*.py"))}


def _imports(name: str, path: Path, known: set[str]) -> set[str]:
    """Every module ``name`` imports, as absolute names - ``from .x import y`` counts as ``.x.y``
    when ``y`` is a module, as ``.x`` otherwise."""
    package = name if path.name == "__init__.py" else name.rsplit(".", 1)[0]
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base_parts = package.split(".")[: len(package.split(".")) - node.level + 1]
                base = ".".join(base_parts + ([node.module] if node.module else []))
            else:
                base = node.module
            for alias in node.names:
                candidate = f"{base}.{alias.name}"
                found.add(candidate if candidate in known else base)
    return found


def _plugin_of(module: str) -> str | None:
    parts = module.split(".")
    return parts[2] if len(parts) > 2 and parts[:2] == ["spectre", "plugins"] else None


def _reachable() -> dict[str, set[str]]:
    """Each plugin's ``depends_on``, and theirs, and so on."""
    from spectre.plugins import PLUGINS

    direct = {plugin.name: set(plugin.depends_on) for plugin in PLUGINS}
    reachable: dict[str, set[str]] = {}
    for name in direct:
        seen, stack = set(), list(direct[name])
        while stack:
            dependency = stack.pop()
            if dependency not in seen:
                seen.add(dependency)
                stack.extend(direct.get(dependency, ()))
        reachable[name] = seen
    return reachable


def _graph() -> list[tuple[str, str]]:
    modules = _modules()
    known = set(modules)
    return sorted((name, target) for name, path in modules.items() for target in _imports(name, path, known))


def test_the_scanner_sees_the_plugin_imports():
    # garde-fou : un analyseur cassé ne trouverait rien, et tout le reste passerait
    graph = _graph()
    assert ("spectre.plugins.lots.api", "spectre.plugins.lots.service") in graph
    assert ("spectre.plugins.experiments.lineage", "spectre.plugins.lots.service") in graph  # import paresseux


def test_the_kernel_imports_no_plugin():
    leaks = [
        f"{module} -> {target}"
        for module, target in _graph()
        if module.startswith("spectre.kernel") and target.startswith("spectre.plugins") and (module, target) != KERNEL_COMPOSITION_ROOT
    ]
    assert not leaks, "Le noyau importe un plugin :\n  " + "\n  ".join(leaks)


def test_a_plugin_only_imports_the_plugins_it_depends_on():
    reachable = _reachable()
    used = set()
    undeclared = []
    for module, target in _graph():
        plugin, other = _plugin_of(module), _plugin_of(target)
        if plugin is None or other is None or other == plugin or other in reachable[plugin]:
            continue
        if (module, target) in ALLOWED_TRANSITIONAL:
            used.add((module, target))
        else:
            undeclared.append(f"{module} -> {target} ({other} absent du depends_on de {plugin})")
    stale = [f"{module} -> {target}" for module, target in ALLOWED_TRANSITIONAL if (module, target) not in used]
    assert not undeclared, "Imports hors depends_on :\n  " + "\n  ".join(undeclared)
    assert not stale, "Entrées de ALLOWED_TRANSITIONAL qui ne correspondent plus à aucun import :\n  " + "\n  ".join(stale)


def test_no_plugin_imports_another_plugins_api():
    crossing = [
        f"{module} -> {target}"
        for module, target in _graph()
        if _plugin_of(module) and _plugin_of(target) not in (None, _plugin_of(module)) and (target.split(".")[3:4] == ["api"] or target.endswith("_api"))
    ]
    assert not crossing, "Un plugin importe l'api d'un autre :\n  " + "\n  ".join(crossing)


def test_the_domain_of_a_plugin_does_not_know_http():
    importing = {
        module
        for module, target in _graph()
        if _plugin_of(module) and not _is_http_module(module) and target.split(".")[0] in ("fastapi", "starlette")
    }
    unexpected = sorted(importing - ALLOWED_FASTAPI.keys())
    stale = sorted(ALLOWED_FASTAPI.keys() - importing)
    assert not unexpected, "Modules du domaine qui importent FastAPI :\n  " + "\n  ".join(unexpected)
    assert not stale, "Entrées de ALLOWED_FASTAPI qui n'importent plus FastAPI :\n  " + "\n  ".join(stale)
