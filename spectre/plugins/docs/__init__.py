"""Pages de documentation."""

from ...kernel.plugin import NavEntry, Page, Plugin

PLUGIN = Plugin(
    name="docs",
    pages=(
        Page("/docs", "docs.html"),
        Page("/docs/guide", "docs-guide.html"),
        Page("/docs/exemples", "docs-exemples.html"),
        Page("/docs/architecture", "docs-architecture.html"),
    ),
    nav=(NavEntry("Documentation", "/docs", order=50, match=r"^/docs"),),
)
