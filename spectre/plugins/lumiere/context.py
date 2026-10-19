"""Le contexte d'un rapport : la chose décrite - une plaque, une analyse, une étude, un µprojet, un lot - lue une fois
et partagée par tous les blocs d'un même rapport. Tout contexte a des **plaques** (``wafers`` : une, ou plusieurs
avec un rôle), un titre, et sait se décrire (``facts_html``) ; les lectures sont paresseuses et mémorisées ; une
lecture en échec rend « rien » et se journalise : un bloc dit alors ce qui manque, le rapport sort quand même.
:func:`make` vérifie que l'utilisateur voit la chose (une étude ou un µprojet demandent le rôle ``viewer``)."""

from __future__ import annotations

import html
import logging
from functools import cached_property
from typing import Any

from ...kernel.errors import DomainError, InvalidInput, NotFound
from ..accounts.service import User
from ..characterization import service as characterization
from ..experiments import repository
from ..experiments import service as experiments
from ..lots import service as lots
from ..meta_analysis import data as analysis_data
from ..meta_analysis import service as analyses
from ..microprojects import service as microprojects
from ..sem_images import service as sem_images
from ..structures import kinds
from ..wafer_data import blocks as wafer_data_blocks
from ..wafers import notes, records, timeline, tracking
from ..wafers import service as wafers

log = logging.getLogger(__name__)
esc = html.escape

MAX_WAFERS = 24  # plaques d'un contexte à plusieurs (µprojet, lot) : au-delà, les premières seulement

CONTEXTS = {"wafer": "une plaque", "analysis": "une analyse de plaques", "study": "une étude", "microproject": "un µprojet", "lot": "un lot"}


def _rows(pairs: list[tuple[str, Any]]) -> str:
    cells = "".join(f"<tr><th>{esc(k)}</th><td>{esc(str(v))}</td></tr>" for k, v in pairs if v not in (None, "", []))
    return f'<table class="spectre-facts">{cells}</table>' if cells else ""


class ReportContext:
    """Ce que tout contexte offre aux blocs."""

    kind = ""

    def __init__(self, user: User, key: str):
        self.user = user
        self.key = key.strip()
        self._data: dict[str, Any] = {}
        self._plates: dict[str, WaferContext] = {}

    # -- à définir par chaque contexte ---------------------------------------------------------------
    @property
    def wafers(self) -> list[str]:  # les lasermarks, la référence d'abord quand il y en a une
        raise NotImplementedError

    @property
    def roles(self) -> dict[str, str]:  # lasermark -> rôle (« référence », « comparée »…), vide sinon
        return {}

    @property
    def title(self) -> str:
        raise NotImplementedError

    def facts_html(self, options: dict[str, Any]) -> str:
        raise NotImplementedError

    # -- commun --------------------------------------------------------------------------------------
    def plate(self, lasermark: str) -> WaferContext:
        if lasermark not in self._plates:
            self._plates[lasermark] = WaferContext(self.user, lasermark)
        return self._plates[lasermark]

    @cached_property
    def catalog(self) -> list[wafer_data_blocks.CatalogHook]:
        return wafer_data_blocks.catalog()

    def hook(self, key: str) -> wafer_data_blocks.CatalogHook | None:
        return next((h for h in self.catalog if h.hook == key), None)

    def data(self, hook: str) -> Any | None:
        """Le résultat (colonnes, lignes, source) d'un type de données PRISM pour toutes les plaques ; ``None`` s'il
        ne se lit pas (ou sans plaque)."""
        if hook not in self._data:
            if not self.wafers:
                self._data[hook] = None
            else:
                try:
                    self._data[hook] = characterization.query(hook, {"wafer_names": list(self.wafers)})
                except DomainError as exc:
                    log.info("rapport %s %s : %s non lu (%s)", self.kind, self.key, hook, exc)
                    self._data[hook] = None
        return self._data[hook]


class WaferContext(ReportContext):
    """Une plaque : son passeport, sa vie en ligne, ses notes, sa frise, ses images MEB."""

    kind = "wafer"

    @cached_property
    def wafer_key(self) -> str:
        return wafers.wafer_key(self.key)

    @cached_property
    def passport(self) -> dict[str, Any]:
        line = tracking.line_facts([self.wafer_key]).get(self.wafer_key)
        return wafers.passport(self.key, wafers.occurrences(self.user, keys=[self.key]), records.get(self.key), line)

    @property
    def name(self) -> str:
        return self.passport["lasermark"]

    @property
    def wafers(self) -> list[str]:
        return [self.name]

    @property
    def title(self) -> str:
        return f"Plaque {self.name}"

    @cached_property
    def life(self) -> dict[str, Any] | None:
        try:
            return tracking.read(self.key)
        except DomainError as exc:
            log.info("rapport de %s : vie en ligne non lue (%s)", self.key, exc)
            return None

    @cached_property
    def notes(self) -> dict[str, Any] | None:
        return notes.get(self.key)

    @cached_property
    def fdls(self) -> list[str]:
        return list(dict.fromkeys([*(self.passport.get("line_fdl") or []), *(self.passport.get("fdl") or [])]))

    @cached_property
    def events(self) -> list[dict[str, Any]]:
        return timeline.events(self.user, self.name)

    @cached_property
    def sem_listing(self) -> dict[str, Any] | str:
        """La liste des images MEB du G4 (``groups``), ou le message qui dit pourquoi il n'y en a pas."""
        try:
            return sem_images.listing(self.name, self.fdls)
        except DomainError as exc:
            return str(exc)

    def plate(self, lasermark: str) -> WaferContext:
        return self if wafers.wafer_key(lasermark) == self.wafer_key else super().plate(lasermark)

    def facts_html(self, options: dict[str, Any]) -> str:
        passport, life, plate_notes = self.passport, self.life, self.notes
        out = _rows([
            ("Lasermark", passport["lasermark"]),
            ("Runs d'épitaxie", ", ".join(passport.get("run_names") or [])),
            ("FDL", ", ".join(self.fdls)),
            ("Lot", passport.get("lot_name") or (life or {}).get("lot")),
            ("Dernier emplacement connu", passport.get("last_location")),
            ("µprojets", ", ".join(m.get("code") or m.get("name") or "" for m in passport.get("microprojects") or [])),
            ("Statut en ligne", (life or {}).get("status")),
        ])
        if options.get("studies", True):
            studies = passport.get("occurrences") or []
            if studies:
                items = []
                for o in studies:
                    exp = o.get("experiment") or {}
                    mp = (exp.get("microproject") or {}).get("code") or (exp.get("microproject") or {}).get("name") or ""
                    bits = [f"<strong>{esc(str(mp))}</strong>" if mp else "", esc(str(exp.get("title") or exp.get("id") or "étude")), esc(str(exp.get("status") or ""))]
                    if o.get("variant"):
                        bits.append(f"variante {esc(str(o['variant']))}")
                    if o.get("location"):
                        bits.append(f"rangée : {esc(str(o['location']))}")
                    items.append(f"<li>{' · '.join(b for b in bits if b)}</li>")
                out += f"<h3>Études qui la suivent</h3><ul>{''.join(items)}</ul>"
            else:
                out += "<p><em>Aucune étude ne suit cette plaque.</em></p>"
        if options.get("notes", True) and plate_notes:
            written = [f"<h4>{esc(label)}</h4><p>{esc(str(plate_notes[k]))}</p>" for k, label in (("context", "Contexte"), ("hypothesis", "Hypothèse"), ("learnings", "Ce qu'on a compris")) if plate_notes.get(k)]
            if written:
                out += "<h3>Notes</h3>" + "".join(written)
        return out


class AnalysisContext(ReportContext):
    """Une analyse de plaques (meta_analysis) : sa question, sa référence et les plaques comparées, ses KPI."""

    kind = "analysis"

    @cached_property
    def analysis(self) -> dict[str, Any]:
        try:
            return analyses.get(int(self.key))
        except ValueError:
            raise NotFound("Cette analyse n'existe pas.", code="analysis_not_found") from None

    @property
    def wafers(self) -> list[str]:
        return [w["lasermark"] for w in self.analysis["wafers"]]

    @property
    def roles(self) -> dict[str, str]:
        return {w["lasermark"]: ("référence" if i == 0 else "comparée") for i, w in enumerate(self.analysis["wafers"])}

    @property
    def title(self) -> str:
        return f"Analyse · {self.analysis['title']}"

    @cached_property
    def kpis(self) -> dict[str, Any] | None:
        try:
            return analysis_data.kpis(self.analysis)
        except Exception as exc:  # noqa: BLE001 - PRISM absent : la slide le dit
            log.info("rapport de l'analyse %s : KPI non calculés (%s)", self.key, exc)
            return None

    def facts_html(self, options: dict[str, Any]) -> str:
        a = self.analysis
        out = _rows([("Titre", a["title"]), ("Créée par", f"{a['created_by']} · {a['created_at'][:10]}"), ("Plaques", f"{len(a['wafers'])} (la référence d'abord)")])
        if a.get("question"):
            out += f"<h3>La question posée</h3><p>{esc(a['question'])}</p>"
        out += "<h3>Plaques</h3><ul>" + "".join(f"<li><strong>{esc(w['lasermark'])}</strong> · {esc(self.roles[w['lasermark']])}</li>" for w in a["wafers"]) + "</ul>"
        if a.get("conclusion"):
            out += f"<h3>Conclusion</h3><p>{esc(a['conclusion'])}</p>"
        return out


class StudyContext(ReportContext):
    """Une étude (la dernière version d'une piste d'un µprojet) : titre, intention, hypothèse, conclusion,
    structure, plaques suivies. La clé est « slug/experiment_id »."""

    kind = "study"

    @cached_property
    def _found(self) -> tuple[Any, Any]:
        slug, _, experiment_id = self.key.partition("/")
        if not slug or not experiment_id:
            raise InvalidInput("Une étude se désigne par « µprojet/piste ».", code="invalid_study_key")
        microproject = microprojects.get_by_slug(slug)
        microprojects.check_role(self.user, microproject, "viewer")
        tip = experiments.tip_of(repository.get_repository(slug), experiment_id)
        return microproject, tip

    @property
    def microproject(self) -> Any:
        return self._found[0]

    @property
    def tip(self) -> Any:
        return self._found[1]

    @property
    def tracked(self) -> list[dict[str, Any]]:
        return [e for e in self.tip.metadata.get("physical_tracking", []) if e.get("sample_id")]

    @property
    def wafers(self) -> list[str]:
        return list(dict.fromkeys(e["sample_id"] for e in self.tracked))[:MAX_WAFERS]

    @property
    def title(self) -> str:
        return f"Étude · {self.tip.title}"

    @property
    def structure_svg(self) -> str | None:
        try:
            return kinds.render_structure_svg(self.tip.structure_type, self.tip.structure, self.tip.metadata)
        except Exception as exc:  # noqa: BLE001
            log.info("rapport de l'étude %s : structure non dessinée (%s)", self.key, exc)
            return None

    def facts_html(self, options: dict[str, Any]) -> str:
        tip, mp = self.tip, self.microproject
        conclusion = tip.conclusion
        out = _rows([
            ("Étude", tip.title), ("µprojet", mp.code or mp.name), ("Statut", repository.display_status(tip)),
            ("Auteur", f"{tip.author} · {tip.created_at.date().isoformat()}"), ("Étiquettes", ", ".join(tip.tags)),
            ("Plaques suivies", ", ".join(self.wafers)),
        ])
        if tip.intent:
            out += f"<h3>Ce qu'on veut démontrer</h3><p>{esc(tip.intent)}</p>"
        if tip.hypothesis:
            out += f"<h4>Hypothèse</h4><p>{esc(tip.hypothesis)}</p>"
        if self.tracked and options.get("studies", True):
            rows = "".join(f"<tr><td>{esc(str(e['sample_id']))}</td><td>{esc(str(e.get('variant') or ''))}</td><td>{esc(str(e.get('location') or ''))}</td><td>{esc(', '.join(e.get('fdl') or []) if isinstance(e.get('fdl'), list) else str(e.get('fdl') or ''))}</td></tr>" for e in self.tracked)
            out += f'<h3>Plaques</h3><table class="spectre-table"><tr><th>Plaque</th><th>Variante</th><th>Emplacement</th><th>FDL</th></tr>{rows}</table>'
        if getattr(conclusion, "summary", ""):
            out += f"<h3>Conclusion</h3><p>{esc(conclusion.summary)}</p>"
            if getattr(conclusion, "next_steps", ""):
                out += f"<h4>Et ensuite</h4><p>{esc(conclusion.next_steps)}</p>"
        return out


class MicroprojectContext(ReportContext):
    """Un µprojet : ses études (la dernière version de chaque piste) et leurs plaques."""

    kind = "microproject"

    @cached_property
    def microproject(self) -> Any:
        microproject = microprojects.get_by_slug(self.key)
        microprojects.check_role(self.user, microproject, "viewer")
        return microproject

    @cached_property
    def tips(self) -> list[Any]:
        return sorted(repository.branch_tips(repository.get_repository(self.microproject.slug)), key=lambda t: t.created_at, reverse=True)

    @property
    def wafers(self) -> list[str]:
        found = dict.fromkeys(e["sample_id"] for tip in self.tips for e in tip.metadata.get("physical_tracking", []) if e.get("sample_id"))
        return list(found)[:MAX_WAFERS]

    @property
    def title(self) -> str:
        mp = self.microproject
        return f"µprojet {mp.code or mp.name}"

    def facts_html(self, options: dict[str, Any]) -> str:
        mp = self.microproject
        out = _rows([("µprojet", mp.name), ("Code", mp.code), ("Études", len(self.tips)), ("Plaques suivies", len(self.wafers))])
        if mp.description:
            out += f"<p>{esc(mp.description)}</p>"
        return out

    def studies_html(self) -> str:
        if not self.tips:
            return "<p><em>Aucune étude dans ce µprojet.</em></p>"
        rows = "".join(
            f"<tr><td><strong>{esc(t.title)}</strong></td><td>{esc(repository.display_status(t))}</td><td>{esc(t.created_at.date().isoformat())}</td>"
            f"<td>{esc(', '.join(dict.fromkeys(e['sample_id'] for e in t.metadata.get('physical_tracking', []) if e.get('sample_id'))))}</td><td>{esc(t.conclusion.summary or '')}</td></tr>"
            for t in self.tips
        )
        return f'<table class="spectre-table"><tr><th>Étude</th><th>Statut</th><th>Créée le</th><th>Plaques</th><th>Conclusion</th></tr>{rows}</table>'


class LotContext(ReportContext):
    """Un lot de fabrication (plugin lots) et ses plaques."""

    kind = "lot"

    @cached_property
    def lot(self) -> Any:
        found = lots.find_by_code(self.key)
        if found is None:
            raise NotFound(f"Lot « {self.key} » introuvable.", code="lot_not_found")
        return found

    @cached_property
    def lot_wafers(self) -> list[Any]:
        return lots.wafers_of([self.lot.id])[self.lot.id]

    @property
    def wafers(self) -> list[str]:
        return [w.lasermark for w in self.lot_wafers][:MAX_WAFERS]

    @property
    def title(self) -> str:
        return f"Lot {self.lot.code}"

    def facts_html(self, options: dict[str, Any]) -> str:
        lot = self.lot
        out = _rows([
            ("Lot", lot.code), ("Intitulé", lot.title), ("Statut", lot.status), ("Priorité", lot.priority),
            ("Début", lot.started_on), ("Fin prévue", lot.forecast_exit_on), ("Fin déclarée", lot.exited_on), ("Source", lot.source),
            ("Plaques", f"{len(self.lot_wafers)}" + (f" ({MAX_WAFERS} dans le rapport)" if len(self.lot_wafers) > MAX_WAFERS else "")),
        ])
        if lot.description:
            out += f"<p>{esc(lot.description)}</p>"
        if lot.hold_reason:
            out += f"<p><em>En pause : {esc(lot.hold_reason)}</em></p>"
        return out


KINDS: dict[str, type[ReportContext]] = {"wafer": WaferContext, "analysis": AnalysisContext, "study": StudyContext, "microproject": MicroprojectContext, "lot": LotContext}


def make(user: User, kind: str, key: str) -> ReportContext:
    """Le contexte ``kind`` désigné par ``key``, vérifié : il existe et ``user`` le voit (404 / 403 sinon)."""
    cls = KINDS.get(kind)
    if cls is None:
        raise InvalidInput(f"Contexte inconnu : {kind!r}.", code="unknown_context")
    ctx = cls(user, key)
    ctx.title  # noqa: B018 - lit la chose : 404 si elle n'existe pas, 403 si on ne la voit pas
    return ctx
