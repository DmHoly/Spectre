"""Pages de documentation."""

from ...kernel.plugin import NavEntry, Page, Plugin

# un bouton à icône à côté de la session, comme le comparateur : la nav garde les sections de travail
DOCS_ICON = '<path d="M2 4h6a4 4 0 0 1 4 4v13a3 3 0 0 0-3-3H2Z"/><path d="M22 4h-6a4 4 0 0 0-4 4v13a3 3 0 0 1 3-3h7Z"/>'

PLUGIN = Plugin(
    name="docs",
    pages=(
        Page("/docs", "index.html"),
        Page("/docs/guide", "guide.html"),
        Page("/docs/exemples", "examples.html"),
        Page("/docs/architecture", "architecture.html"),
    ),
    nav=(NavEntry("Documentation", "/docs", order=50, match=r"^/docs", icon=DOCS_ICON),),
    title="Documentation",
    description="Les pages d'aide de Spectre.",
    icon="help",
)
