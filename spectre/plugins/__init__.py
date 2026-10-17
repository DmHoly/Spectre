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
from .comparator import PLUGIN as comparator
from .docs import PLUGIN as docs
from .experiments import PLUGIN as experiments
from .external_images import PLUGIN as external_images
from .intent_forms import PLUGIN as intent_forms
from .kpi_tracking import PLUGIN as kpi_tracking
from .kpis import PLUGIN as kpis
from .kpis_demo import PLUGIN as kpis_demo
from .library import PLUGIN as library
from .links import PLUGIN as links
from .lots import PLUGIN as lots
from .materials import PLUGIN as materials
from .meta_analysis import PLUGIN as meta_analysis
from .microprojects import PLUGIN as microprojects
from .notebook import PLUGIN as notebook
from .planning import PLUGIN as planning
from .prism import PLUGIN as prism
from .process_library import PLUGIN as process_library
from .promotion import PLUGIN as promotion
from .references import PLUGIN as references
from .search import PLUGIN as search
from .sem_images import PLUGIN as sem_images
from .settings import PLUGIN as settings
from .simulation_progress import PLUGIN as simulation_progress
from .step_report import PLUGIN as step_report
from .structures import PLUGIN as structures
from .teams import PLUGIN as teams
from .twins import PLUGIN as twins
from .usage import PLUGIN as usage
from .wafer_data import PLUGIN as wafer_data
from .wafers import PLUGIN as wafers

PLUGINS = (
    accounts,
    settings,
    teams,
    search,
    library,
    areas,
    microprojects,
    attachments,
    structures,
    experiments,
    comparator,
    process_library,
    references,
    promotion,
    intent_forms,
    wafers,
    twins,
    lots,
    planning,
    links,
    atlas,
    characterization,
    prism,
    external_images,
    notebook,
    kpis,
    kpis_demo,
    usage,
    simulation_progress,
    step_report,
    materials,
    kpi_tracking,
    wafer_data,
    meta_analysis,
    sem_images,
    docs,
)
