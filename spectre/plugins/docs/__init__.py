"""Pages de documentation."""

from ...kernel.plugin import NavEntry, Page, Plugin

PLUGIN = Plugin(
    name="docs",
    pages=(
        Page("/docs", "index.html"),
        Page("/docs/guide", "guide.html"),
        Page("/docs/exemples", "examples.html"),
        Page("/docs/architecture", "architecture.html"),
    ),
    nav=(NavEntry("Documentation", "/docs", order=50, match=r"^/docs"),),
    title="Documentation",
    description="Les pages d'aide de Spectre.",
    icon="help",
)
