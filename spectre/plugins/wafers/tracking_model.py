"""La vie d'une plaque en ligne, assemblée à partir des tables que la source lui donne
(:mod:`.tracking_source` : MES, épitaxie et fiche Gozer, FDL JIRA, tests, étapes de FDL) en une
seule fiche JSON pour sa page - repris du bloc ``wafer_tracking`` de lumiere-suite, pour une plaque
à la fois, dans l'esprit de Spectre : des dictionnaires nommés plutôt que des lignes-listes.

Ce module ne sait pas d'où viennent les tables (PRISM, démo) ni quand elles ont été lues
(:mod:`.tracking`) : il ne fait que lire des DataFrames et rendre un dictionnaire.

Le statut d'une plaque :

- ``en cours`` : une étape MES est commencée et pas finie (et c'est la dernière) ;
- ``en attente`` : entre deux étapes ;
- ``clos`` : la dernière FDL citant la plaque est close et la plaque n'a plus bougé en MES depuis ;
- ``introuvable`` : aucune ligne MES - la fiche Gozer et les FDL, eux, peuvent exister.

Une étape commencée, jamais fermée, mais suivie d'une autre est un oubli de clôture MES, pas une
étape en cours : sa fin effective (``end_effective``) est le début de la suivante.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable

import numpy as np
import pandas as pd

_DESC_MAX = 800
_OBJ_MAX = 300
_EPI_STEP = "EPITAXY"


def _empty(columns: Iterable[str] = ()) -> pd.DataFrame:
    return pd.DataFrame(columns=list(columns))


@dataclass
class TrackingFrames:
    """Ce que la source a lu pour une plaque : les tables, telles que PRISM les rend (colonnes dans
    la casse de la base), les identifiants MES rencontrés en route (``aliases`` : identifiant ->
    lasermark demandé) et le compte rendu de chaque lecture (``phases`` : nom -> ``{ok, rows,
    seconds, error}``)."""

    lasermark: str
    mes: pd.DataFrame = field(default_factory=_empty)
    epitaxy: pd.DataFrame = field(default_factory=_empty)
    record: pd.DataFrame = field(default_factory=_empty)
    fdl_by_wafer: pd.DataFrame = field(default_factory=_empty)
    fdl_by_lot: pd.DataFrame = field(default_factory=_empty)
    tests: pd.DataFrame = field(default_factory=_empty)
    fdl_steps: pd.DataFrame = field(default_factory=_empty)
    aliases: dict[str, str] = field(default_factory=dict)
    phases: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def any_ok(self) -> bool:
        return any(p.get("ok") for p in self.phases.values())


# --- cellules ----------------------------------------------------------------------------------


def _text(v: Any) -> str | None:
    # Les colonnes tableau Postgres (jira_labels…) arrivent en list/ndarray : pd.isna() y est ambigu.
    if isinstance(v, (list, tuple, set, np.ndarray)):
        v = ", ".join(str(x).strip() for x in v if x is not None and str(x).strip())
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return None
    s = str(v).strip()
    return s or None


def _ts(v: Any) -> str | None:
    """Horodatage -> 'YYYY-MM-DD HH:MM' (NaT/None -> None)."""
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return None
    return pd.Timestamp(v).strftime("%Y-%m-%d %H:%M")


def _ts_loose(v: Any) -> str | None:
    """Comme :func:`_ts` mais ne plante pas sur un texte qui n'est pas une date (FDL.Closure_Date
    est du texte)."""
    try:
        return _ts(v)
    except (ValueError, TypeError):
        return _text(v)


def _num(v: Any, nd: int = 1) -> float | None:
    if v is None or pd.isna(v):
        return None
    return round(float(v), nd)


def _int(v: Any) -> int | None:
    n = pd.to_numeric(v, errors="coerce")
    return None if pd.isna(n) else int(n)


def _trunc(s: str | None, n: int) -> str | None:
    return s if s is None or len(s) <= n else s[: n - 1].rstrip() + "…"


def _lower(df: pd.DataFrame) -> pd.DataFrame:
    """Postgres replie les alias non quotés (Epi_Request_Number -> epi_request_number) et garde les
    quotés ("Run_Name") : on compare donc les colonnes sans tenir compte de la casse."""
    df = df.copy()
    df.columns = [str(c).lower() for c in df.columns]
    return df


def _cell(v: Any) -> str | None:
    if isinstance(v, (pd.Timestamp, datetime)):
        return _ts(v)
    return _text(v)


# --- nom du lot : nomenclature interne ----------------------------------------------------------
#   QTXXX  Quick Test            QMLXXX / QMLbXXX  Quick Midloop (bis)    SLXXX  Short Loop
#   QROXXX / QREXXX  Quick Red MOCVD (O) / MBE (E)    QGOXXX / QGEXXX  Quick Green
#   QBOXXX / QBEXXX  Quick Blue                        QTWEXXX / QTWOXXX  Quick Test White
#   CTVXXX  Contact Test Vehicle   QMDEXXX / QMDOXXX  Quick Midloop multidesign (MBE / MOCVD)
#   QPADXXX  Quick test pad
# Chiffres avec ou sans espace (« QMDE 06 », « QMDE06 »). Ordre = préfixe le plus long d'abord,
# sinon « QTWE12 » serait lu « QT » + « WE12 ».
_LOT_PREFIXES = ("QTWE", "QTWO", "QMDE", "QMDO", "QPAD", "QMLB", "QML", "QRO", "QRE", "QGO", "QGE", "QBO", "QBE", "CTV", "QT", "SL")
_LOT_RE = re.compile(r"(?<![A-Za-z0-9])(" + "|".join(_LOT_PREFIXES) + r")[ \t _-]?(\d{1,4})(?![A-Za-z0-9])", re.I)
# Valeurs que JIRA met faute de mieux dans jira_nom_lots
_PLACEHOLDERS = {"to be updated", "tbd", "n/a", "na", "none", "-", "?", "a définir", "à définir", "inconnu"}


def find_lots(text: str | None) -> list[str]:
    """Noms de lots de la nomenclature trouvés dans ``text``, normalisés (« qmde 06 » -> « QMDE06 »)."""
    seen: dict[str, None] = {}
    for m in _LOT_RE.finditer(text or ""):
        seen.setdefault(m.group(1).upper() + m.group(2), None)
    return list(seen)


def _raw_lot_tokens(s: str | None) -> list[str]:
    """Valeurs de jira_nom_lots hors placeholder et hors nomenclature (ex. un lot MES « E26090001 »)."""
    out: dict[str, None] = {}
    for tok in re.split(r"[\r\n,;]+", s or ""):
        tok = tok.strip().upper()
        if tok and tok.lower() not in _PLACEHOLDERS and not find_lots(tok):
            out.setdefault(tok, None)
    return list(out)


def _lot_name(tickets: list[dict], mes_lot: str | None) -> tuple[str | None, str | None, list[str]]:
    """Le nom de lot « métier » de la plaque et sa provenance : ``jira_nom_lots`` (nomenclature,
    sinon valeur brute) des tickets posés sur la plaque, puis leur description ; à défaut le lot
    MES. Plusieurs candidats : le plus cité gagne, les autres sont rendus."""
    for source, key in (("JIRA", "lots_jira"), ("JIRA", "lots_raw"), ("description", "lots_desc")):
        score: dict[str, tuple[int, int]] = {}
        for idx, t in enumerate(tickets):
            for name in t.get(key) or []:
                n, _ = score.get(name, (0, -1))
                score[name] = (n + 1, idx)
        if score:
            ranked = sorted(score, key=score.get, reverse=True)  # type: ignore[arg-type]
            return ranked[0], source, ranked[1:]
    return mes_lot, ("MES" if mes_lot else None), []


# --- MES ---------------------------------------------------------------------------------------


def mes_rows(mes: pd.DataFrame, ids: set[str]) -> pd.DataFrame:
    """Les lignes MES de ces identifiants (entrée ou sortie), triées, avec la fin effective de
    chaque étape et le marquage des étapes jamais clôturées mais suivies d'une autre."""
    if mes.empty:
        return mes
    item = mes["physical_item_id"].astype(str).str.upper()
    item_out = mes["physical_item_id_out"].astype(str).str.upper()
    rows = mes[item.isin(ids) | item_out.isin(ids)].copy()
    for c in ("step_start_date", "step_end_date", "last_update"):
        rows[c] = pd.to_datetime(rows[c], errors="coerce")
    rows = rows.sort_values(["step_start_date", "step_order"], na_position="last").reset_index(drop=True)
    started = rows["step_start_date"].notna()
    last_started = started[started].index.max() if started.any() else None
    rows["_orphan"] = started & rows["step_end_date"].isna() & (rows.index != last_started)
    rows["_end_eff"] = rows["step_end_date"].where(~rows["_orphan"], rows["step_start_date"].shift(-1))
    return rows


def _mes_summary(steps: pd.DataFrame, now: datetime) -> dict[str, Any]:
    out: dict[str, Any] = {
        "lot": None, "lots": [], "product": None, "route": None, "status": "introuvable",
        "current": None, "first_start": None, "last_seen": None, "elapsed_h": None, "last_update": None,
        "n_steps": 0, "n_unclosed": 0, "n_rework": 0,
    }
    if steps.empty:
        return out
    last = steps.iloc[-1]
    running = steps[steps["step_start_date"].notna() & steps["_end_eff"].isna()]
    lots: dict[str, None] = {}
    for _, r in steps.iterrows():
        for v in (r["physical_lot_id"], r["physical_lot_id_out"]):
            if _text(v):
                lots.setdefault(str(v).strip(), None)
    if not running.empty:
        cur = running.iloc[-1]
        status, since, idle_h = "en cours", cur["step_start_date"], 0.0
    else:
        cur = last
        since = steps["_end_eff"].max()
        idle_h = (pd.Timestamp(now) - since).total_seconds() / 3600 if pd.notna(since) else None
        status = "en attente"
    first = steps["step_start_date"].min()
    end_ref = pd.Timestamp(now) if status == "en cours" else (since if pd.notna(since) else pd.Timestamp(now))
    out.update(
        {
            "lot": _text(last["physical_lot_id_out"]) or _text(last["physical_lot_id"]),
            "lots": list(lots),
            "product": _text(steps["productname"].dropna().iloc[-1]) if steps["productname"].notna().any() else None,
            "route": _text(last["route_detailed_name"]) or _text(last["route"]),
            "status": status,
            "current": {
                "step": _text(cur["step_detailed_name"]),
                "equipment": _text(cur["equipment_name"]),
                "recipe": _text(cur["recipe_name"]),
                "since": _ts(since),
                "idle_h": _num(idle_h),
            },
            "first_start": _ts(first),
            "last_seen": _ts(max(steps["step_start_date"].max(), steps["_end_eff"].max())),
            "elapsed_h": _num((end_ref - first).total_seconds() / 3600) if pd.notna(first) else None,
            "last_update": _ts(steps["last_update"].max()),
            "n_steps": int(len(steps)),
            "n_unclosed": int(steps["_orphan"].sum()),
            "n_rework": int((pd.to_numeric(steps["step_cycle_number"], errors="coerce").fillna(1) > 1).sum()),
        }
    )
    return out


def _mes_epi(steps: pd.DataFrame) -> dict[str, Any] | None:
    """Dernière passe en étape épitaxie dans la MES : l'équipement y est le réacteur, la recette
    remplace le commentaire Gozer."""
    if steps.empty:
        return None
    hit = steps[steps["step_detailed_name"].astype(str).str.contains(_EPI_STEP, case=False, na=False, regex=False)]
    if hit.empty:
        return None
    r = hit.iloc[-1]
    start, end = r["step_start_date"], r["_end_eff"]
    return {
        "reactor": _text(r["equipment_name"]), "recipe": _text(r["recipe_name"]),
        "start": _ts(start), "end": None if pd.isna(end) else _ts(end),
        "running": bool(pd.notna(start) and pd.isna(end)), "step": _text(r["step_detailed_name"]),
    }


def _merge_epi(epi: list[dict], mes: dict | None) -> list[dict]:
    """Complète l'épitaxie Gozer avec l'étape MES, sans jamais écraser une valeur Gozer : pas de
    run Gozer -> une entrée construite sur la MES seule (``source: MES``) ; run Gozer incomplet ->
    réacteur / commentaire (= recette) / dates manquants remplis (``source: Gozer+MES``)."""
    for e in epi:
        e.setdefault("source", "Gozer")
    if mes is None:
        return epi
    trace = {"mes_recipe": mes["recipe"], "mes_step": mes["step"]}
    if not epi:
        return [
            {
                "run": None, "start": mes["start"], "end": mes["end"], "recipe_type": None, "recipe_version": None,
                "reactor": mes["reactor"], "comments": mes["recipe"], "request": None, "task_code": None,
                "platform": None, "source": "MES", "running": mes["running"], **trace,
            }
        ]
    last, filled = epi[-1], False
    for key, value in (("reactor", mes["reactor"]), ("comments", mes["recipe"]), ("start", mes["start"]), ("end", mes["end"])):
        if not last.get(key) and value:
            last[key], filled = value, True
    last.update(trace)
    if filled:
        last["source"] = "Gozer+MES"
        last["running"] = mes["running"] and not last.get("end")
    return epi


def _step_rows(steps: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    for _, r in steps.iterrows():
        rows.append(
            {
                "route": _text(r["route_detailed_name"]) or _text(r["route"]),
                "route_version": _text(r["route_detailed_version"]),
                "step": _text(r["step_detailed_name"]),
                "order": _int(r["step_order"]),
                "cycle": _int(r["step_cycle_number"]),
                "start": _ts(r["step_start_date"]),
                "end": _ts(r["step_end_date"]),
                "end_effective": _ts(r["_end_eff"]),
                "unclosed": bool(r["_orphan"]),
                "equipment": _text(r["equipment_name"]),
                "recipe": _text(r["recipe_name"]),
                "carrier": _text(r["carrier_name"]),
                "lot": _text(r["physical_lot_id"]),
                "lot_out": _text(r["physical_lot_id_out"]),
                "status_in": _text(r["wafertrackstatus_in"]),
                "status_out": _text(r["wafertrackstatus_out"]),
                "capability": _text(r["capability_name"]),
            }
        )
    return rows


# --- fiche wafer (Gozer) ------------------------------------------------------------------------


def _rows_of(df: pd.DataFrame, names: set[str], columns: tuple[str, ...] = ("substrat_lasermark", "wafer_name")) -> pd.DataFrame:
    if df.empty:
        return df
    mask = pd.Series(False, index=df.index)
    for col in columns:
        if col in df.columns:
            mask |= df[col].astype(str).str.upper().isin(names)
    return df[mask]


def _aggregate_epitaxy(info: pd.DataFrame) -> tuple[list[dict], list[str], list[str], list[str]]:
    """Replie le produit cartésien (épi × test) en un run d'épi par ligne + les FDL citées."""
    if info.empty:
        return [], [], [], []
    runs: dict[tuple, dict] = {}
    bw: dict[str, None] = {}
    tst: dict[str, None] = {}
    for _, r in info.iterrows():
        key = (_text(r.get("run_name")), _ts(r.get("start_date")))
        runs.setdefault(
            key,
            {
                "run": key[0], "start": key[1], "end": _ts(r.get("end_date")),
                "recipe_type": _text(r.get("recipe_type")), "recipe_version": _text(r.get("recipeversion")),
                "reactor": _text(r.get("reactor")), "comments": _trunc(_text(r.get("comments")), _DESC_MAX),
                "request": _text(r.get("epi_request_number")), "task_code": _text(r.get("epi_task_code")),
                "platform": _text(r.get("jira_platform")),
            },
        )
        if _text(r.get("bw_request_number")):
            bw.setdefault(_text(r.get("bw_request_number")), None)  # type: ignore[arg-type]
        if _text(r.get("test_request_number")):
            tst.setdefault(_text(r.get("test_request_number")), None)  # type: ignore[arg-type]
    epi = sorted(runs.values(), key=lambda e: e["start"] or "")
    names = sorted({str(v) for v in info.get("wafer_name", pd.Series(dtype=object)).dropna()})
    return epi, sorted(bw), sorted(tst), names


def _record(record: pd.DataFrame, names: set[str]) -> dict[str, str]:
    """Colonnes non vides de la ligne ``schema_gozer.wafer`` (hors clés pk_/fk_), telles quelles :
    on ne sait pas à l'avance lesquelles existent."""
    if record.empty:
        return {}
    low = {c: str(c).lower() for c in record.columns}
    mask = pd.Series(False, index=record.index)
    for col, name in low.items():
        if name in ("substrat_lasermark", "wafer_name"):
            mask |= record[col].astype(str).str.upper().isin(names)
    rows = record[mask]
    if rows.empty:
        return {}
    out: dict[str, str] = {}
    for col, v in rows.iloc[0].items():
        if low[col].startswith(("pk_", "fk_")):
            continue
        txt = _trunc(_cell(v), _DESC_MAX)
        if txt is not None:
            out[str(col)] = txt
    return out


# --- JIRA ---------------------------------------------------------------------------------------


def _ticket(r: pd.Series, via: str) -> dict[str, Any]:
    nom_lots = _text(r.get("jira_nom_lots"))
    full_desc, full_obj = _text(r.get("jira_description")), _text(r.get("objective"))
    closed = _ts_loose(r.get("closuredate")) or _ts_loose(r.get("closure_date"))
    return {
        "request": _text(r.get("request_number")), "jira_key": _text(r.get("jira_key")),
        "task_code": _text(r.get("task_code")), "requester": _text(r.get("requester")),
        "created": _ts_loose(r.get("creation_date")), "closed": closed,
        "state": "clos" if closed else "ouvert",
        "objective": _trunc(full_obj, _OBJ_MAX), "description": _trunc(full_desc, _DESC_MAX),
        "labels": _text(r.get("jira_labels")), "via": via,
        # candidats de nom de lot, calculés sur le texte complet (avant troncature)
        "lots_jira": find_lots(nom_lots), "lots_raw": _raw_lot_tokens(nom_lots),
        "lots_desc": find_lots(f"{full_desc or ''}\n{full_obj or ''}"),
    }


def _tickets(by_wafer: pd.DataFrame, by_lot: pd.DataFrame, names: set[str], lots: set[str]) -> list[dict]:
    """Tickets de la plaque ; un ticket cité à la fois par plaque et par lot reste « wafer »."""
    found: dict[str, dict] = {}
    lots_up = {lot.upper() for lot in lots}
    for df, col, keys, via in ((by_wafer, "wafer", names, "wafer"), (by_lot, "lot", lots_up, "lot")):
        if df.empty or col not in df.columns:
            continue
        for _, r in df[df[col].astype(str).str.upper().isin(keys)].iterrows():
            t = _ticket(r, via)
            found.setdefault(t["request"] or f"?{len(found)}", t)
    return sorted(found.values(), key=lambda t: t["created"] or "")


def _tests(tests: pd.DataFrame, names: set[str]) -> list[dict]:
    """Tests de la plaque (lasermark ou nom). ``date`` = début du test, à défaut Test_Date."""
    out = []
    for _, r in _rows_of(tests, names).iterrows():
        start, tdate = _ts_loose(r.get("teststartdate")), _ts_loose(r.get("test_date"))
        out.append(
            {
                "id": _int(r.get("pk_test")), "type": _text(r.get("test_type")),
                "date": start or tdate, "start": start, "end": _ts_loose(r.get("testenddate")),
                "operator": _text(r.get("operator")), "sensor": _text(r.get("optical_sensor")),
                "prober": _text(r.get("prober_name")), "temperature": _text(r.get("test_temperature")),
                "description": _trunc(_text(r.get("testdescription")), _OBJ_MAX),
                "report": _text(r.get("link_to_test_report_pdf")), "lot": _text(r.get("lot_name")),
                "request": _text(r.get("request_number")), "task_code": _text(r.get("task_code")),
                "labels": _text(r.get("jira_labels")),
            }
        )
    return sorted(out, key=lambda t: t["date"] or "")


def _apply_closure(rec: dict[str, Any]) -> None:
    """Statut « clos » : la dernière FDL de la plaque (par date de création) est close ET la plaque
    n'a plus bougé en MES depuis. Les tickets posés sur le lot seulement ne comptent pas : les
    clore ne dit rien d'une plaque précise."""
    own = [t for t in rec["tickets"] if t["via"] == "wafer"]
    last = max(own, key=lambda t: (t["created"] or "", t["closed"] or "9999"), default=None)
    rec["last_fdl"] = None if last is None else {k: last.get(k) for k in ("request", "task_code", "created", "closed", "state")}
    rec["closed_at"] = None
    if last and last["closed"] and rec["status"] != "en cours" and (rec["last_seen"] is None or rec["last_seen"] <= last["closed"]):
        rec["status"] = "clos"
        rec["closed_at"] = last["closed"]


# --- avancement d'une FDL (étapes JIRA) ---------------------------------------------------------
#   cat        statuts JIRA                                              compté dans l'avancement
#   done       Done                                                      oui (fait)
#   running    In Progress                                               oui
#   hold       Hold, Futur Hold                                          oui
#   todo       Ready To Do, Waiting For Treatment, Validated, To Validate, Draft (et inconnu non clos)
#   skipped    Canceled, Skipped, Rejected, Scrapped, Material Scrapped  non

_DONE = {"done"}
_RUN = {"in progress"}
_HOLD = {"hold", "futur hold"}
_SKIP = {"canceled", "cancelled", "skipped", "rejected", "scrapped", "material scrapped"}
_FDL_DESC_MAX = 300


def step_category(status: str | None, closed: str | None) -> str:
    """Catégorie d'avancement d'une étape d'après son statut JIRA (repli : clôturée = faite)."""
    s = (status or "").strip().lower()
    if s in _DONE:
        return "done"
    if s in _SKIP:
        return "skipped"
    if s in _RUN:
        return "running"
    if s in _HOLD:
        return "hold"
    if s:
        return "todo"
    return "done" if closed else "todo"


def clean_jira_text(raw: Any) -> str | None:
    """Texte wiki Jira -> texte brut sur une ligne (couleurs, gras, macros, retours à la ligne)."""
    t = _text(raw)
    if t is None:
        return None
    t = re.sub(r"\{color[^}]*\}", "", t)
    for marker in (r"\*", "_", r"\+", r"\^", "~"):
        t = re.sub(rf"{marker}([^{marker[-1]}\n]+){marker}", r"\1", t)
    t = re.sub(r"\{\{([^}]+)\}\}", r"\1", t)
    t = re.sub(r"\{[a-zA-Z0-9:_\- ]+\}", "", t)
    return re.sub(r"\s+", " ", t.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")).strip() or None


def _sort_date(step: dict) -> str:
    for col in ("closed", "estimated", "created"):
        if step.get(col):
            return step[col]
    return "9999"


def _order_by_chain(steps: list[dict]) -> list[dict] | None:
    """Tri topologique sur previous/next (branches parallèles départagées par la date). None si le
    graphe est incomplet, cyclique, ou si une clé manque ou est dupliquée."""
    by_key = {s["key"]: s for s in steps if s.get("key")}
    if len(by_key) != len(steps):
        return None
    children: dict[str, list[str]] = {k: [] for k in by_key}
    indegree = {k: 0 for k in by_key}
    edges = set()
    for s in steps:
        if s.get("previous") in by_key:
            edges.add((s["previous"], s["key"]))
        if s.get("next") in by_key:
            edges.add((s["key"], s["next"]))
    for a, b in edges:
        children[a].append(b)
        indegree[b] += 1
    ready = [k for k, d in indegree.items() if d == 0]
    if not ready:
        return None
    ordered: list[dict] = []
    seen: set[str] = set()
    while ready:
        ready.sort(key=lambda k: _sort_date(by_key[k]))
        key = ready.pop(0)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(by_key[key])
        for child in children[key]:
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
    return ordered if len(ordered) == len(steps) else None


def _fdl_summary(steps: list[dict], method: str) -> dict[str, Any]:
    by_key = {s["key"]: s for s in steps if s.get("key")}
    counted = [s for s in steps if s["category"] != "skipped"]

    def n(cat: str) -> int:
        return sum(1 for s in steps if s["category"] == cat)

    def ready(s: dict) -> bool:  # toutes les étapes en amont sont faites ou écartées
        p = by_key.get(s.get("previous"))
        return p is None or p["category"] in ("done", "skipped")

    done = [s for s in steps if s["category"] == "done" and s["closed"]]
    last = max(done, key=lambda s: s["closed"], default=None)
    n_done = n("done")
    return {
        "n": len(steps), "n_done": n_done, "n_running": n("running"), "n_hold": n("hold"), "n_todo": n("todo"),
        "n_skipped": n("skipped"), "n_late": sum(1 for s in steps if s["late"]),
        "pct": round(100 * n_done / len(counted)) if counted else None,
        "order": method,
        "running": [s["stage"] for s in steps if s["category"] == "running"][:3],
        "hold": [s["stage"] for s in steps if s["category"] == "hold"][:3],
        "next": [s["stage"] for s in steps if s["category"] == "todo" and ready(s)][:2],
        "last_done": None if last is None else {"stage": last["stage"], "closed": last["closed"]},
    }


def build_fdl_flows(fdl_steps: pd.DataFrame, now: datetime) -> dict[str, dict[str, Any]]:
    """Par numéro de FDL : ses étapes ordonnées (chaînage JIRA, à défaut par date), chacune avec sa
    catégorie et si elle est en retard (fin estimée passée et pas faite), et le résumé d'avancement."""
    if fdl_steps.empty:
        return {}
    df = _lower(fdl_steps)
    today = _ts(pd.Timestamp(now))
    flows: dict[str, dict[str, Any]] = {}
    for request, group in df.groupby("request_number", sort=True):
        steps = []
        for _, r in group.iterrows():
            closed = _ts_loose(r.get("jira_closure_date"))
            cat = step_category(_text(r.get("status")), closed)
            est = _ts_loose(r.get("jira_estimative_done_date"))
            steps.append(
                {
                    "key": _text(r.get("jira_key")),
                    "stage": _text(r.get("jira_workshop_stage")) or _text(r.get("jira_summary")),
                    "type": _text(r.get("jira_workshop_type")),
                    "status": _text(r.get("status")),
                    "category": cat,
                    "created": _ts_loose(r.get("jira_creationg_date")),
                    "closed": closed,
                    "estimated": est,
                    "previous": _text(r.get("jira_previous_ws")),
                    "next": _text(r.get("jira_next_ws")),
                    "days": _num(r.get("jira_estimation_in_days")),
                    "assignee": _text(r.get("assignee")),
                    "late": bool(est and today and est < today and cat in ("todo", "running", "hold")),
                    "description": _trunc(clean_jira_text(r.get("jira_workshop_description")), _FDL_DESC_MAX),
                }
            )
        ordered = _order_by_chain(steps)
        method = "chain" if ordered is not None else "date"
        ordered = ordered if ordered is not None else sorted(steps, key=_sort_date)
        flows[str(request)] = {"request": str(request), "steps": ordered, **_fdl_summary(ordered, method)}
    return flows


# --- la fiche --------------------------------------------------------------------------------------


def build(frames: TrackingFrames, now: datetime | None = None) -> dict[str, Any]:
    """La vie de la plaque ``frames.lasermark`` : son statut en ligne et son étape courante, ses
    étapes MES, son épitaxie, ses FDL (avec leur avancement), ses tests et sa fiche Gozer."""
    now = now or datetime.now()
    lm = frames.lasermark.strip().upper()
    my_ids = {lm} | {a.upper() for a, owner in frames.aliases.items() if owner.upper() == lm}
    mes = _lower(frames.mes) if not frames.mes.empty else frames.mes
    steps = mes_rows(mes, my_ids)
    epitaxy = _lower(frames.epitaxy) if not frames.epitaxy.empty else frames.epitaxy
    info = _rows_of(epitaxy, my_ids)

    rec: dict[str, Any] = {"lasermark": frames.lasermark, "aliases": sorted(my_ids - {lm})}
    rec.update(_mes_summary(steps, now))
    rec["steps"] = _step_rows(steps)
    epi, bw_req, test_req, wafer_names = _aggregate_epitaxy(info)
    rec["epitaxy"] = _merge_epi(epi, _mes_epi(steps))
    rec["base_wafer_fdl"], rec["test_fdl"], rec["wafer_names"] = bw_req, test_req, wafer_names

    names = my_ids | {n.upper() for n in wafer_names}
    rec["tickets"] = _tickets(
        _lower(frames.fdl_by_wafer) if not frames.fdl_by_wafer.empty else frames.fdl_by_wafer,
        _lower(frames.fdl_by_lot) if not frames.fdl_by_lot.empty else frames.fdl_by_lot,
        names,
        set(rec["lots"]),
    )
    rec["tests"] = _tests(_lower(frames.tests) if not frames.tests.empty else frames.tests, names)
    own = [t for t in rec["tickets"] if t["via"] == "wafer"]
    rec["lot_name"], rec["lot_source"], rec["lot_alternatives"] = _lot_name(own, rec["lot"])
    _apply_closure(rec)
    rec["record"] = _record(frames.record, names)
    cited = {t["request"] for t in rec["tickets"]} | {e["request"] for e in rec["epitaxy"]} | set(bw_req) | set(test_req)
    rec["fdls"] = {r: f for r, f in build_fdl_flows(frames.fdl_steps, now).items() if r in cited}
    rec["last_movement"] = last_movement(rec)
    rec["phases"] = frames.phases
    return rec


def last_movement(rec: dict[str, Any]) -> str | None:
    """Quand la plaque a bougé pour la dernière fois, toutes sources confondues ('YYYY-MM-DD HH:MM') :
    dernière étape MES, dernier test, dernier ticket créé ou clos, dernière fin d'épitaxie - ce qui
    décide si elle est immobile (:mod:`.tracking`)."""
    candidates = [rec.get("last_seen")]
    candidates += [t.get("date") for t in rec.get("tests", [])] + [t.get("end") for t in rec.get("tests", [])]
    candidates += [t.get("created") for t in rec.get("tickets", [])] + [t.get("closed") for t in rec.get("tickets", [])]
    candidates += [e.get("end") or e.get("start") for e in rec.get("epitaxy", [])]
    dated = [c for c in candidates if c and re.match(r"^\d{4}-\d{2}-\d{2}", c)]
    return max(dated) if dated else None
