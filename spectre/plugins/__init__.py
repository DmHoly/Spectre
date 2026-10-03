"""Les plugins de Spectre, dans l'ordre topologique de ``ARCHITECTURE.md`` § 3 : chacun ne dépend
que de plugins listés avant lui (vérifié au démarrage par
:func:`spectre.kernel.plugin.check_dependencies`). C'est aussi l'ordre des migrations et de
l'inclusion des routes.
"""

from .accounts import PLUGIN as accounts
from .areas import PLUGIN as areas
from .atlas import PLUGIN as atlas
from .attachments import PLUGIN as attachments
from .characterization import PLUGIN as characterization
from .docs import PLUGIN as docs
from .evidence import PLUGIN as evidence
from .experiments import PLUGIN as experiments
from .external_images import PLUGIN as external_images
from .intent_forms import PLUGIN as intent_forms
from .kpis import PLUGIN as kpis
from .kpis_demo import PLUGIN as kpis_demo
from .library import PLUGIN as library
from .links import PLUGIN as links
from .lots import PLUGIN as lots
from .microprojects import PLUGIN as microprojects
from .notebook import PLUGIN as notebook
from .process_library import PLUGIN as process_library
from .search import PLUGIN as search
from .structures import PLUGIN as structures
from .wafers import PLUGIN as wafers

PLUGINS = (
    accounts,
    search,
    library,
    areas,
    microprojects,
    attachments,
    structures,
    process_library,
    experiments,
    evidence,
    intent_forms,
    wafers,
    lots,
    links,
    atlas,
    characterization,
    notebook,
    external_images,
    kpis,
    kpis_demo,
    docs,
)
