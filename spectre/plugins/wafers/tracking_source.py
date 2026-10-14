"""D'où vient la vie d'une plaque en ligne : la source lit les tables (:class:`TrackingFrames`),
:mod:`.tracking_model` les assemble, :mod:`.tracking` décide quand relire.

Deux sources, choisies à un seul endroit (:func:`current_source`) :

- **PRISM** : les hooks de la catégorie « Traçabilité » du catalogue (``wafer_mes_history`` sur la
  MES, ``wafer_epitaxy`` / ``wafer_record`` / ``wafer_fdl`` / ``lot_fdl`` / ``wafer_tests`` /
  ``fdl_steps`` sur Gozer) - Spectre ne porte aucune requête : PRISM fournit la donnée, documentée
  une fois pour tous les projets. C'est, avec ``characterization.prism_source``, le seul module qui
  importe ``prism`` ;
- **la démo** (``SPECTRE_DEMO_DATA=1``, comme la caractérisation) : des plaques inventées,
  toujours les mêmes pour le même lasermark, aux mêmes colonnes que les hooks - de quoi montrer la
  page sans accès aux bases.

Chaque lecture est isolée : si la MES ne répond pas, la fiche Gozer et les FDL sont gardées, et
l'échec est rendu dans ``phases`` - la page l'affiche en bandeau plutôt que de rester vide. Seule
une configuration PRISM absente arrête tout (503) ; des bases toutes injoignables sont une erreur
amont (502), sauf si une fiche déjà lue peut être montrée à la place (:mod:`.tracking`).
"""

from __future__ import annotations

import hashlib
import logging
import os
import random
import time
from datetime import datetime, timedelta
from typing import Any, Callable, Protocol

import pandas as pd

from ...kernel.db import data_dir
from ...kernel.errors import Unavailable, UpstreamError
from .tracking_model import TrackingFrames

logger = logging.getLogger(__name__)

# Les hooks PRISM lus, et le paramètre que chacun attend.
HOOKS = {
    "wafer_mes_history": "wafer_names",
    "wafer_epitaxy": "wafer_names",
    "wafer_record": "wafer_names",
    "wafer_fdl": "wafer_names",
    "lot_fdl": "lot_names",
    "wafer_tests": "wafer_names",
    "fdl_steps": "fdl_numbers",
}
# Une plaque renommée en route (physical_item_id_out) : on relit la MES avec les identifiants
# rencontrés, au plus deux fois.
MAX_ALIAS_HOPS = 2


class TrackingSource(Protocol):
    name: str  # "prism" ou "demo"

    def fetch(self, lasermark: str) -> TrackingFrames:
        """Les tables de cette plaque. Lève ``Unavailable`` sans configuration, ``UpstreamError``
        quand rien n'a pu être lu."""
        ...


Runner = Callable[[str, dict[str, Any]], pd.DataFrame]


def _timed(frames: TrackingFrames, name: str, fn: Callable[[], pd.DataFrame]) -> pd.DataFrame:
    t0 = time.perf_counter()
    try:
        df = fn()
    except Exception as exc:  # une base injoignable, une requête refusée : la phase le dit
        logger.warning("suivi de la plaque %s : lecture %s en échec (%s)", frames.lasermark, name, exc)
        frames.phases[name] = {"ok": False, "rows": 0, "seconds": round(time.perf_counter() - t0, 2), "error": str(exc)[:300]}
        return pd.DataFrame()
    frames.phases[name] = {"ok": True, "rows": int(len(df)), "seconds": round(time.perf_counter() - t0, 2), "error": None}
    return df


def _case_variants(ids: list[str]) -> list[str]:
    """La MES stocke les identifiants tels quels : on tente tel quel, majuscules et minuscules."""
    out: dict[str, None] = {}
    for i in ids:
        for v in (i, i.upper(), i.lower()):
            if v:
                out.setdefault(v, None)
    return list(out)


def _ident(value: Any) -> str:
    """Un identifiant MES comparable (majuscules, sans blancs) - vide pour une cellule vide."""
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return ""
    return str(value).strip().upper()


def _aliases(mes: pd.DataFrame, lasermark: str) -> dict[str, str]:
    """Les identifiants MES de la plaque, d'un renommage à l'autre (entrée -> sortie, dans les deux
    sens), chacun rattaché au lasermark demandé."""
    found: dict[str, str] = {}
    if mes.empty:
        return found
    wanted = {lasermark.upper()}
    pairs = {
        (_ident(a), _ident(b))
        for a, b in mes[["physical_item_id", "physical_item_id_out"]].itertuples(index=False)
        if _ident(a) and _ident(b) and _ident(a) != _ident(b)
    }
    changed = True
    while changed:
        changed = False
        for a, b in pairs:
            if (a in wanted) != (b in wanted):
                wanted |= {a, b}
                changed = True
    for ident in wanted - {lasermark.upper()}:
        found[ident] = lasermark
    return found


def read_frames(lasermark: str, run: Runner) -> TrackingFrames:
    """Les tables d'une plaque par ``run(hook, params)`` - la même suite de lectures pour PRISM et
    pour la démo : la MES d'abord (avec ses renommages), puis Gozer et JIRA à partir des noms et des
    lots rencontrés, et l'avancement des FDL citées."""
    lm = lasermark.strip()
    frames = TrackingFrames(lasermark=lm)
    ids = [lm]
    pieces: list[pd.DataFrame] = []
    for hop in range(MAX_ALIAS_HOPS + 1):
        name = "mes" if hop == 0 else f"mes+{hop}"
        df = _timed(frames, name, lambda ids=ids: run("wafer_mes_history", {"wafer_names": _case_variants(ids)}))
        pieces.append(df)
        frames.mes = pd.concat([p for p in pieces if not p.empty], ignore_index=True).drop_duplicates() if any(not p.empty for p in pieces) else pd.DataFrame()
        if not frames.phases[name]["ok"]:
            break
        frames.aliases = _aliases(frames.mes, lm)
        fresh = [a for a in frames.aliases if a.upper() not in {i.upper() for i in ids}]
        if not fresh:
            break
        ids = ids + fresh

    names = sorted({lm.upper()} | {a.upper() for a in frames.aliases})
    frames.epitaxy = _timed(frames, "epitaxy", lambda: run("wafer_epitaxy", {"wafer_names": names}))
    frames.record = _timed(frames, "record", lambda: run("wafer_record", {"wafer_names": names}))
    if not frames.epitaxy.empty:
        for col in ("wafer_name", "substrat_lasermark"):
            if col in frames.epitaxy.columns:
                names = sorted(set(names) | {str(v).upper() for v in frames.epitaxy[col].dropna()})
    frames.fdl_by_wafer = _timed(frames, "fdl", lambda: run("wafer_fdl", {"wafer_names": names}))
    lots: list[str] = []
    if not frames.mes.empty:
        values = pd.concat([frames.mes["physical_lot_id"], frames.mes["physical_lot_id_out"]]).dropna()
        lots = sorted({str(v).strip().upper() for v in values if str(v).strip()})
    if lots:
        frames.fdl_by_lot = _timed(frames, "lot_fdl", lambda: run("lot_fdl", {"lot_names": lots}))
    requests = sorted(
        {
            str(v)
            for df in (frames.fdl_by_wafer, frames.fdl_by_lot, frames.epitaxy)
            if not df.empty
            for col in df.columns
            if str(col).lower() in ("request_number", "epi_request_number", "bw_request_number", "test_request_number")
            for v in df[col].dropna()
        }
    )
    if requests:
        frames.fdl_steps = _timed(frames, "fdl_steps", lambda: run("fdl_steps", {"fdl_numbers": requests}))
    frames.tests = _timed(frames, "tests", lambda: run("wafer_tests", {"wafer_names": names}))
    return frames


class PrismSource:
    name = "prism"

    @staticmethod
    def _run(hook: str, params: dict[str, Any]) -> pd.DataFrame:
        import prism

        return prism.run_hook(hook, **params)

    def fetch(self, lasermark: str) -> TrackingFrames:
        import prism

        try:
            frames = read_frames(lasermark, self._run)
        except prism.ConfigError as exc:
            raise Unavailable(f"configuration de connexion PRISM incomplète : {exc}") from exc
        if not frames.any_ok:
            first = next((p["error"] for p in frames.phases.values() if p.get("error")), "aucune lecture")
            raise UpstreamError(f"les bases de la ligne ne répondent pas : {first}")
        return frames


# --- la démo --------------------------------------------------------------------------------------

_ROUTES = [
    ("EPI_MOCVD_V3", ["Clean substrat", "Dépôt buffer", "EPI.EPITAXY", "Dépôt p-GaN", "Mesure PL"]),
    ("BACKPLANE_PT2", ["Litho ouverture", "Gravure", "Dépôt métal", "Recuit", "Inspection"]),
    ("LED_PROCESS_PT2", ["Litho mesa", "Gravure mesa", "Passivation", "Litho contact", "Dépôt contact", "Recuit contact"]),
]
_EQUIPMENTS = ["MOCVD-04", "LITHO-02", "ICP-01", "PVD-03", "FURN-05", "INSPECT-01", "WET-02"]
_STAGES = [
    ("EPI2 - Delivery", "EPI PF2"), ("CAR - PL", "Characterization"), ("OGM - Logistique", "OGM"),
    ("SDL - Transfert", "SDM Logistics"), ("PROWET - OPS - Nettoyage", "PROWET"), ("PEN - OPS - Dépôt", "Process Engineering"),
    ("PEN - Photolithographie", "Process Engineering"), ("PEN - Gravure Dry", "Process Engineering"),
    ("METRO - OPS - CD", "Métrologie"), ("DEF - OPS - Patterned Wafer Inspection", "Defectivity"),
    ("PEN - CMP", "Process Engineering"), ("METRO - OPS - Epaisseur", "Métrologie"),
]
# Le scénario d'une plaque de démo, par son lasermark : en cours dans un équipement ; en attente
# entre deux étapes (avec une reprise et une étape jamais clôturée) ; immobile depuis 40 jours et
# dernière FDL close ; introuvable en MES (mais dans Gozer) ; renommée en route.
_SCENARIOS = ("running", "waiting", "old", "missing", "alias")


def demo_scenario(lasermark: str) -> str:
    digest = hashlib.sha256(lasermark.strip().upper().encode("utf-8")).hexdigest()
    return _SCENARIOS[int(digest[:8], 16) % len(_SCENARIOS)]


class DemoSource:
    """Des plaques inventées, déterministes par lasermark, servies par les mêmes lectures que
    PRISM (:func:`read_frames`) - la démo répond aux hooks, pas à la place de l'assemblage."""

    name = "demo"

    def __init__(self, now: Callable[[], datetime] = datetime.now):
        self._now = now

    def fetch(self, lasermark: str) -> TrackingFrames:
        tables = self._tables(lasermark.strip())
        return read_frames(lasermark, lambda hook, params: self._answer(tables, hook, params))

    @staticmethod
    def _answer(tables: dict[str, pd.DataFrame], hook: str, params: dict[str, Any]) -> pd.DataFrame:
        df = tables[hook]
        if df.empty:
            return df
        wanted = {str(v).upper() for v in next(iter(params.values()))}
        if hook == "wafer_mes_history":
            m = df["physical_item_id"].str.upper().isin(wanted) | df["physical_item_id_out"].str.upper().isin(wanted)
            return df[m].reset_index(drop=True)
        if hook == "fdl_steps":
            return df[df["Request_Number"].isin(wanted)].reset_index(drop=True)
        if hook == "lot_fdl":
            return df[df["lot"].str.upper().isin(wanted)].reset_index(drop=True)
        return df.reset_index(drop=True)

    def _tables(self, lm: str) -> dict[str, pd.DataFrame]:
        now = self._now()
        scenario = demo_scenario(lm)
        seed = int(hashlib.sha256(lm.upper().encode("utf-8")).hexdigest()[:8], 16)
        rng = random.Random(seed)
        key = lm.upper()
        lot = f"E26{seed % 90 + 10:02d}00{seed % 9 + 1}"
        lot_name = f"QMDE{seed % 40 + 1:02d}"
        alias = f"{key}-B" if scenario == "alias" else None
        mes = pd.DataFrame() if scenario == "missing" else pd.DataFrame(self._steps(key, lot, rng, scenario, alias, now))

        wafer_name = f"W{key[:6]}"
        record = pd.DataFrame(
            [
                {
                    "pk_wafer": 1000 + seed % 500, "wafer_name": wafer_name, "substrat_lasermark": key, "fk_fdl": 5,
                    "diameter_mm": 200, "substrat_type": "Si<111>", "substrat_supplier": "SupplierX",
                    "creation_date": now - timedelta(days=90), "comment": None,
                }
            ]
        )
        epi_rows = []
        for k in range(2):  # épi × test : deux lignes à replier en un run
            epi_rows.append(
                {
                    "wafer_name": wafer_name, "substrat_lasermark": key, "Run_Name": f"RUN-{2400 + seed % 100}",
                    "end_date": now - timedelta(days=50), "start_date": now - timedelta(days=50, hours=9),
                    "Recipe_Type": "MQW-B", "recipeversion": "12", "reactor": f"R{seed % 3 + 1}",
                    "Comments": "Léger décalage de longueur d'onde en bord de plaque." if scenario == "running" else None,
                    "epi_request_number": f"FDL-{100 + seed % 50}", "bw_request_number": f"FDL-{50 + seed % 20}",
                    "test_request_number": f"FDL-{200 + k}", "epi_task_code": "EPI-PT2", "jira_platform": "PT2",
                }
            )
        epitaxy = pd.DataFrame(epi_rows)
        closed = {"old": now - timedelta(days=35), "waiting": now - timedelta(days=20)}.get(scenario)
        fdl_request = f"FDL-{300 + seed % 100}"
        fdl_by_wafer = pd.DataFrame(
            [
                {
                    "wafer": key, "PK_FDL": seed % 1000, "Request_Number": fdl_request, "Task_Code": "PROC-PT2",
                    "Requester": "m.daanoune", "Creation_Date": now - timedelta(days=45), "Closure_Date": closed,
                    "ClosureDate": closed, "jira_key": f"PROD-{4000 + seed % 1000}", "Objective": "Validation du flux mesa",
                    "jira_description": "h2. Contexte\nSplit sur le recuit contact.", "jira_nom_lots": lot_name,
                    "jira_labels": ["split", "mesa"],
                }
            ]
        )
        fdl_by_lot = pd.DataFrame(
            [
                {
                    "lot": lot, "PK_FDL": 900 + seed % 100, "Request_Number": f"FDL-{900 + seed % 100}", "Task_Code": "LOT-QGO",
                    "Requester": "p.durand", "Creation_Date": now - timedelta(days=60 if scenario == "old" else 30),
                    "Closure_Date": None, "ClosureDate": None,
                    "jira_key": f"PROD-{9000 + seed % 100}", "Objective": "Suivi du lot complet", "jira_description": None,
                    "jira_nom_wafers": key, "jira_labels": None,
                }
            ]
        )
        tests = []
        for k in range(2):  # le 2e test n'a pas de FDL ; une plaque immobile n'a pas de test récent non plus
            d0 = now - timedelta(days=(45 if scenario == "old" else 3) + 4 * k + seed % 7)
            tests.append(
                {
                    "substrat_lasermark": key, "wafer_name": wafer_name, "PK_Test": 500 + 10 * (seed % 40) + k,
                    "Test_Type": "MOX4", "Test_Date": d0, "TestStartDate": d0, "TestEndDate": d0 + timedelta(hours=3),
                    "Operator": "tester1", "Optical_Sensor": "Sphere-A", "Prober_Name": "PRB-02", "Test_Temperature": "25C",
                    "TestDescription": "EQE + PL cartographie", "Link_To_Test_Report_Pdf": None, "lot_name": lot,
                    "Request_Number": None if k else "FDL-200", "Task_Code": None if k else "TEST-PT2",
                    "jira_nom_lots": lot, "jira_labels": None,
                }
            )
        requests = [fdl_request, f"FDL-{900 + seed % 100}", f"FDL-{100 + seed % 50}", "FDL-200"]
        return {
            "wafer_mes_history": mes,
            "wafer_epitaxy": epitaxy,
            "wafer_record": record,
            "wafer_fdl": fdl_by_wafer,
            "lot_fdl": fdl_by_lot,
            "wafer_tests": pd.DataFrame(tests),
            "fdl_steps": pd.DataFrame(self._fdl_steps(requests, scenario, now)),
        }

    @staticmethod
    def _mes_row(item: str, lot: str, route: str, step: str, order: int, cycle: int, start: datetime, end: datetime | None, i: int, item_out: str | None) -> dict:
        return {
            "physical_lot_id": lot, "physical_item_id": item, "route_detailed_name": route, "route_detailed_version": "3",
            "route": route.split("_")[0], "step_detailed_name": step, "step_order": order, "step_start_date": start,
            "step_end_date": end, "deltat_sec": None, "deltat_hour": None, "difference": None, "step_cycle_number": cycle,
            "equipment_name": "EP-PRO004_PM1" if step == "EPI.EPITAXY" else _EQUIPMENTS[i % len(_EQUIPMENTS)],
            "recipe_name": "SPC_PT2_LED_G_MOCVD_PM1" if step == "EPI.EPITAXY" else f"RCP_{step[:4].upper()}_{i:02d}",
            "carrier_name": f"CAR{lot[-2:]}", "productname": "uLED-PT2", "capability_name": "std",
            "wafertrackstatus_in": "InProcess", "wipdatasetupname_in": None, "physical_lot_id_out": lot,
            "physical_item_id_out": item_out or item, "wafertrackstatus_out": None if end is None else "Done",
            "wipdatasetupname_out": None, "last_update": end or start, "source_name": "demo",
        }

    def _steps(self, item: str, lot: str, rng: random.Random, scenario: str, alias: str | None, now: datetime) -> list[dict]:
        n_done = rng.randint(4, 14)
        flat = [(r, s) for r, steps in _ROUTES for s in steps]
        rows: list[dict] = []
        t = now - timedelta(days=60)
        for i, (route, step) in enumerate(flat[:n_done]):
            cycle = 2 if (scenario == "waiting" and i == 3) else 1
            start = t + timedelta(hours=rng.uniform(2, 70))
            end = start + timedelta(hours=rng.uniform(0.3, 6))
            t = end
            rows.append(self._mes_row(item, lot, route, step, (i + 1) * 10, cycle, start, end, i, alias if (alias and i > n_done // 2) else None))
        if scenario in ("running", "alias") and n_done < len(flat):
            route, step = flat[n_done]
            rows.append(self._mes_row(item, lot, route, step, (n_done + 1) * 10, 1, now - timedelta(hours=rng.uniform(0.5, 9)), None, n_done, alias))
        if scenario in ("old", "waiting"):  # recale le dernier mouvement
            age = timedelta(days=40) if scenario == "old" else timedelta(days=rng.uniform(0.5, 6))
            shift = (now - age) - rows[-1]["step_end_date"]
            for r in rows:
                r["step_start_date"] += shift
                r["step_end_date"] += shift
                r["last_update"] += shift
        if scenario == "waiting" and len(rows) > 3:  # oubli de clôture MES, mais suivi d'autres étapes
            rows[2]["step_end_date"] = None
            rows[2]["wafertrackstatus_out"] = None
        return rows

    @staticmethod
    def _fdl_steps(requests: list[str], scenario: str, now: datetime) -> list[dict]:
        rows = []
        for rank, req in enumerate(requests):
            n = len(_STAGES) if not req.startswith("FDL-9") else 6
            keys = [f"PROD-{req[-3:]}{k:02d}" for k in range(n)]
            t0 = now - timedelta(days=60 - rank)
            for k in range(n):
                stage, typ = _STAGES[k % len(_STAGES)]
                if scenario == "old" or rank == 1:
                    st = "Canceled" if k == 3 else "Skipped" if k == 4 else "Done"
                elif rank == 2:
                    st = "Done" if k == 0 else "In Progress" if k == 1 else "Ready To Do" if k == 2 else "To Validate"
                else:
                    cut = n // 2
                    st = "Done" if k < cut else "In Progress" if k == cut else "Hold" if k == cut + 2 else "Ready To Do"
                done = st in ("Done", "Canceled", "Skipped")
                created = t0 + timedelta(hours=k)
                # chaîne a->b->c, avec une branche : k=3 et k=4 ont le même précédent (k=2) et convergent vers k=5
                prev = keys[2] if k in (3, 4) else (keys[3] if k == 5 else (keys[k - 1] if k else None))
                nxt = keys[5] if k in (3, 4) else (keys[k + 1] if k + 1 < n else None)
                rows.append(
                    {
                        "Request_Number": req, "jira_key": keys[k], "jira_summary": stage, "jira_workshop_stage": stage,
                        "jira_workshop_type": typ, "jira_workshop_description": f"h2. {stage}\nÉtape *{k}* de la FDL {req}.",
                        "status": st, "jira_creationg_date": created,
                        "jira_closure_date": (created + timedelta(days=1 + k)) if done else None,
                        "jira_estimative_done_date": (now - timedelta(days=2)) if (rank == 0 and st == "Ready To Do" and k == n // 2 + 1) else now + timedelta(days=3 + k),
                        "jira_previous_ws": prev, "jira_next_ws": nxt, "jira_estimation_in_days": 1.0 + k % 3,
                        "assignee": "p.durand" if k % 2 else None,
                    }
                )
        return rows


_PRISM = PrismSource()
_DEMO = DemoSource()


def demo_enabled() -> bool:
    return os.environ.get("SPECTRE_DEMO_DATA") == "1"


def current_source() -> TrackingSource:
    # Le cache disque de PRISM vit avec les données de Spectre (comme pour la caractérisation).
    os.environ.setdefault("PRISM_DATA_DIR", str(data_dir() / "prism"))
    return _DEMO if demo_enabled() else _PRISM
