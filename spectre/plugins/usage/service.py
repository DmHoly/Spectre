"""Le rapport d'utilisation d'une période : qui a utilisé Spectre, quels modules (plugins), quelles
pages et quelles routes, à quel rythme. Lu dans les compteurs horaires de ``usage_counts``
(:mod:`.recorder`), les comptes de ``accounts`` et les équipes de ``teams``.

Trois mesures, d'après la requête comptée :

- **pages vues** : une page HTML ouverte (``kind = page``) ;
- **lectures** : un ``GET`` de l'API - souvent fait par une page pour s'afficher ;
- **écritures** : toute autre méthode de l'API (créer, modifier, supprimer) : ce qu'on y a *fait*.

Un compte est **actif** sur la période s'il a fait au moins une requête ; le **taux d'adoption**
rapporte les comptes actifs aux comptes inscrits à la fin de la période (dans le périmètre des
filtres). Le **rythme** d'un compte compte ses jours actifs par semaine de la période : 3 ou plus,
assidu ; de 1 à 3, régulier ; moins, occasionnel ; aucun, inactif.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable

from ...kernel.db import get_conn
from ...kernel.errors import InvalidInput
from . import recorder

GRANULARITIES = ("day", "week", "month")
MAX_DAYS = 3 * 366
MAX_DAY_BUCKETS = 400
ROUTE_LIMIT = 200

_PAGE = "SUM(CASE WHEN kind = 'page' THEN hits ELSE 0 END)"
_READ = "SUM(CASE WHEN kind = 'api' AND method IN ('GET', 'HEAD') THEN hits ELSE 0 END)"
_WRITE = "SUM(CASE WHEN kind = 'api' AND method NOT IN ('GET', 'HEAD') THEN hits ELSE 0 END)"
_METRICS = f"{_PAGE} AS page_views, {_READ} AS reads, {_WRITE} AS writes, SUM(hits) AS hits"

_BUCKET_SQL = {
    "day": "day",
    # le lundi de la semaine (strftime %w : 0 = dimanche)
    "week": "date(day, '-' || ((CAST(strftime('%w', day) AS INTEGER) + 6) % 7) || ' days')",
    "month": "strftime('%Y-%m-01', day)",
}


@dataclass(frozen=True)
class Filters:
    start: date
    end: date
    granularity: str = "day"
    team_id: int | None = None
    user_id: int | None = None
    plugin: str | None = None
    include_admins: bool = True


@dataclass(frozen=True)
class PluginInfo:
    """Ce que le rapport dit d'un plugin de l'application (lu par l'API dans l'état des plugins)."""

    name: str
    title: str
    icon: str
    active: bool


def check(filters: Filters) -> None:
    if filters.granularity not in GRANULARITIES:
        raise InvalidInput("Granularité inconnue : day, week ou month.", code="invalid_granularity")
    if filters.end < filters.start:
        raise InvalidInput("La fin de la période précède son début.", code="invalid_period")
    days = (filters.end - filters.start).days + 1
    if days > MAX_DAYS:
        raise InvalidInput("Une période de trois ans au plus.", code="invalid_period")
    if filters.granularity == "day" and days > MAX_DAY_BUCKETS:
        raise InvalidInput("Trop de jours pour un graphique par jour : choisissez la semaine ou le mois.", code="invalid_period")


def _bucket(day: date, granularity: str) -> date:
    if granularity == "week":
        return day - timedelta(days=day.weekday())
    if granularity == "month":
        return day.replace(day=1)
    return day


def buckets(start: date, end: date, granularity: str) -> list[str]:
    """Les périodes du graphique, toutes, vides comprises, dans l'ordre."""
    seen: list[str] = []
    day = start
    while day <= end:
        key = _bucket(day, granularity).isoformat()
        if not seen or seen[-1] != key:
            seen.append(key)
        day += timedelta(days=1)
    return seen


def _scope(filters: Filters, start: date | None = None, end: date | None = None, *, plugin: bool = True) -> tuple[str, list]:
    """La clause WHERE sur ``usage_counts`` : la période et les filtres."""
    clauses = ["day BETWEEN ? AND ?"]
    params: list = [(start or filters.start).isoformat(), (end or filters.end).isoformat()]
    if plugin and filters.plugin:
        clauses.append("plugin = ?")
        params.append(filters.plugin)
    if not filters.include_admins:
        clauses.append("user_id NOT IN (SELECT id FROM users WHERE is_admin = 1)")
    if filters.team_id is not None:
        clauses.append("user_id IN (SELECT user_id FROM team_members WHERE team_id = ?)")
        params.append(filters.team_id)
    if filters.user_id is not None:
        clauses.append("user_id = ?")
        params.append(filters.user_id)
    return " AND ".join(clauses), params


def _accounts_scope(filters: Filters) -> tuple[str, list]:
    """La clause WHERE sur ``users`` : les comptes du périmètre (équipe, administrateurs, compte)."""
    clauses = ["1 = 1"]
    params: list = []
    if not filters.include_admins:
        clauses.append("is_admin = 0")
    if filters.team_id is not None:
        clauses.append("id IN (SELECT user_id FROM team_members WHERE team_id = ?)")
        params.append(filters.team_id)
    if filters.user_id is not None:
        clauses.append("id = ?")
        params.append(filters.user_id)
    return " AND ".join(clauses), params


def _weekdays(start: date, end: date) -> list[str]:
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    working = [day for day in days if day.weekday() < 5] or days
    return [day.isoformat() for day in working]


def _totals(conn, filters: Filters, start: date, end: date) -> dict:
    where, params = _scope(filters, start, end)
    row = conn.execute(
        f"SELECT COUNT(DISTINCT user_id) AS active_users, COUNT(DISTINCT plugin) AS plugins_used, {_METRICS}, "
        f"SUM(client_errors) AS client_errors, SUM(server_errors) AS server_errors FROM usage_counts WHERE {where}",
        params,
    ).fetchone()
    daily = dict(
        conn.execute(f"SELECT day, COUNT(DISTINCT user_id) FROM usage_counts WHERE {where} GROUP BY day", params).fetchall()
    )
    working = _weekdays(start, end)
    return {
        "active_users": row["active_users"] or 0,
        "plugins_used": row["plugins_used"] or 0,
        "page_views": row["page_views"] or 0,
        "reads": row["reads"] or 0,
        "writes": row["writes"] or 0,
        "hits": row["hits"] or 0,
        "client_errors": row["client_errors"] or 0,
        "server_errors": row["server_errors"] or 0,
        "avg_daily_active": round(sum(daily.get(day, 0) for day in working) / len(working), 2),
        "peak_daily_active": max(daily.values(), default=0),
    }


def _registered(conn, filters: Filters, end: date) -> int:
    where, params = _accounts_scope(filters)
    return conn.execute(f"SELECT COUNT(*) FROM users WHERE {where} AND date(created_at) <= ?", [*params, end.isoformat()]).fetchone()[0]


def _new_accounts(conn, filters: Filters, start: date, end: date) -> int:
    where, params = _accounts_scope(filters)
    return conn.execute(
        f"SELECT COUNT(*) FROM users WHERE {where} AND date(created_at) BETWEEN ? AND ?", [*params, start.isoformat(), end.isoformat()]
    ).fetchone()[0]


def _metrics(row) -> dict:
    return {key: row[key] or 0 for key in ("page_views", "reads", "writes", "hits")}


def frequency(active_days: int, period_days: int) -> str:
    """Le rythme d'un compte : ``daily`` (3 jours actifs par semaine ou plus), ``weekly`` (1 à 3),
    ``occasional`` (moins), ``inactive`` (aucun)."""
    if active_days == 0:
        return "inactive"
    per_week = active_days / max(period_days / 7, 1)
    if per_week >= 3:
        return "daily"
    if per_week >= 1:
        return "weekly"
    return "occasional"


def report(filters: Filters, plugins: Iterable[PluginInfo], page_titles: dict[str, str] | None = None) -> dict:
    """Le rapport complet d'une période (voir le docstring du module)."""
    check(filters)
    recorder.flush()
    catalog = {plugin.name: plugin for plugin in plugins}
    page_titles = page_titles or {}
    period_days = (filters.end - filters.start).days + 1
    previous_end = filters.start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=period_days - 1)
    bucket_sql = _BUCKET_SQL[filters.granularity]
    where, params = _scope(filters)

    with get_conn() as conn:
        totals = _totals(conn, filters, filters.start, filters.end)
        previous = _totals(conn, filters, previous_start, previous_end)
        registered = _registered(conn, filters, filters.end)
        totals.update(
            registered_users=registered,
            adoption_rate=round(min(totals["active_users"] / registered, 1.0), 4) if registered else 0.0,
            new_users=_new_accounts(conn, filters, filters.start, filters.end),
            plugins_total=sum(1 for plugin in catalog.values() if plugin.active),
        )
        previous_registered = _registered(conn, filters, previous_end)
        previous.update(
            registered_users=previous_registered,
            adoption_rate=round(min(previous["active_users"] / previous_registered, 1.0), 4) if previous_registered else 0.0,
        )
        tracking_since = conn.execute("SELECT MIN(day) FROM usage_counts").fetchone()[0]

        by_bucket = {
            row["bucket"]: row
            for row in conn.execute(
                f"SELECT {bucket_sql} AS bucket, COUNT(DISTINCT user_id) AS active_users, {_METRICS} "
                f"FROM usage_counts WHERE {where} GROUP BY bucket",
                params,
            )
        }
        keys = buckets(filters.start, filters.end, filters.granularity)
        series = [
            {"bucket": key, "active_users": by_bucket[key]["active_users"] if key in by_bucket else 0,
             **(_metrics(by_bucket[key]) if key in by_bucket else {"page_views": 0, "reads": 0, "writes": 0, "hits": 0})}
            for key in keys
        ]

        plugin_series = [
            {"bucket": row["bucket"], "plugin": row["plugin"], "users": row["users"], **_metrics(row)}
            for row in conn.execute(
                f"SELECT {bucket_sql} AS bucket, plugin, COUNT(DISTINCT user_id) AS users, {_METRICS} "
                f"FROM usage_counts WHERE {where} GROUP BY bucket, plugin ORDER BY bucket, plugin",
                params,
            )
        ]

        plugin_rows = {
            row["plugin"]: row
            for row in conn.execute(
                f"SELECT plugin, COUNT(DISTINCT user_id) AS users, COUNT(DISTINCT day) AS active_days, MAX(day) AS last_used, "
                f"{_METRICS}, SUM(server_errors) AS server_errors FROM usage_counts WHERE {where} GROUP BY plugin",
                params,
            )
        }
        previous_where, previous_params = _scope(filters, previous_start, previous_end)
        previous_plugins = dict(
            conn.execute(
                f"SELECT plugin, SUM(hits) FROM usage_counts WHERE {previous_where} GROUP BY plugin", previous_params
            ).fetchall()
        )
        ever_where, ever_params = _scope(filters, date.min, date.max, plugin=False)
        ever_used = dict(
            conn.execute(f"SELECT plugin, MAX(day) FROM usage_counts WHERE {ever_where} GROUP BY plugin", ever_params).fetchall()
        )
        names = list(catalog) + sorted(set(plugin_rows) - set(catalog))
        if filters.plugin:
            names = [filters.plugin]
        plugins_out = []
        for name in names:
            info = catalog.get(name)
            row = plugin_rows.get(name)
            users = row["users"] if row else 0
            plugins_out.append(
                {
                    "name": name,
                    "title": info.title if info else name,
                    "icon": info.icon if info else "puzzle",
                    "active": info.active if info else False,
                    "users": users,
                    "adoption_rate": round(users / totals["active_users"], 4) if totals["active_users"] else 0.0,
                    "active_days": row["active_days"] if row else 0,
                    **(_metrics(row) if row else {"page_views": 0, "reads": 0, "writes": 0, "hits": 0}),
                    "server_errors": (row["server_errors"] or 0) if row else 0,
                    "previous_hits": previous_plugins.get(name, 0),
                    "last_used": ever_used.get(name),
                }
            )
        # les plus adoptés d'abord ; à égalité, ce qu'on y a vu et fait (pas les lectures qu'une page
        # fait pour s'afficher : la session, relue à chaque page, passerait devant)
        plugins_out.sort(key=lambda p: (-p["users"], -(p["page_views"] + p["writes"]), -p["reads"], p["title"].lower()))

        heatmap = [
            {"weekday": row[0], "hour": row[1], "hits": row[2]}
            for row in conn.execute(
                f"SELECT (CAST(strftime('%w', day) AS INTEGER) + 6) % 7 AS weekday, hour, SUM(hits) "
                f"FROM usage_counts WHERE {where} GROUP BY weekday, hour",
                params,
            )
        ]

        routes = []
        for row in conn.execute(
            f"SELECT plugin, kind, method, route, COUNT(DISTINCT user_id) AS users, SUM(hits) AS hits, "
            f"SUM(client_errors) AS client_errors, SUM(server_errors) AS server_errors, SUM(total_ms) AS total_ms, "
            f"MAX(max_ms) AS max_ms, MAX(day) AS last_used FROM usage_counts WHERE {where} "
            f"GROUP BY plugin, kind, method, route ORDER BY hits DESC, route LIMIT {ROUTE_LIMIT}",
            params,
        ):
            routes.append(
                {
                    "plugin": row["plugin"],
                    "kind": row["kind"],
                    "method": row["method"],
                    "route": row["route"],
                    "title": page_titles.get(row["route"]) if row["kind"] == "page" else None,
                    "users": row["users"],
                    "hits": row["hits"],
                    "client_errors": row["client_errors"],
                    "server_errors": row["server_errors"],
                    "avg_ms": round(row["total_ms"] / row["hits"], 1) if row["hits"] else 0.0,
                    "max_ms": round(row["max_ms"], 1),
                    "last_used": row["last_used"],
                }
            )

        users = _users(conn, filters, where, params, period_days)

    return {
        "period": {
            "start": filters.start.isoformat(),
            "end": filters.end.isoformat(),
            "days": period_days,
            "granularity": filters.granularity,
            "previous_start": previous_start.isoformat(),
            "previous_end": previous_end.isoformat(),
        },
        "tracking_since": tracking_since,
        # tous les plugins de l'application, filtre ou pas : de quoi choisir un module
        "catalog": [{"name": p.name, "title": p.title, "icon": p.icon, "active": p.active} for p in catalog.values()],
        "totals": totals,
        "previous": previous,
        "series": series,
        "plugin_series": plugin_series,
        "plugins": plugins_out,
        "heatmap": heatmap,
        "routes": routes,
        "users": users,
    }


def _users(conn, filters: Filters, where: str, params: list, period_days: int) -> list[dict]:
    """Les comptes du périmètre, actifs ou non sur la période, et les comptes supprimés qui y ont
    une activité."""
    stats = {
        row["user_id"]: row
        for row in conn.execute(
            f"SELECT user_id, COUNT(DISTINCT day) AS active_days, MAX(day) AS last_day, {_METRICS} "
            f"FROM usage_counts WHERE {where} GROUP BY user_id",
            params,
        )
    }
    top: dict[int, list[dict]] = {}
    for row in conn.execute(
        f"SELECT user_id, plugin, {_METRICS} FROM usage_counts WHERE {where} GROUP BY user_id, plugin "
        f"ORDER BY user_id, page_views + writes DESC, reads DESC",
        params,
    ):
        top.setdefault(row["user_id"], []).append({"plugin": row["plugin"], **_metrics(row)})
    seen = {
        row[0]: (row[1], row[2])
        for row in conn.execute("SELECT user_id, MIN(day), MAX(day) FROM usage_counts GROUP BY user_id")
    }
    accounts_where, accounts_params = _accounts_scope(filters)
    accounts = {
        row["id"]: row
        for row in conn.execute(
            f"SELECT id, name, email, is_admin, created_at FROM users WHERE {accounts_where} AND date(created_at) <= ?",
            [*accounts_params, filters.end.isoformat()],
        )
    }
    teams: dict[int, list[str]] = {}
    for row in conn.execute(
        "SELECT team_members.user_id, teams.name FROM team_members JOIN teams ON teams.id = team_members.team_id ORDER BY teams.name"
    ):
        teams.setdefault(row[0], []).append(row[1])

    out = []
    for user_id in list(accounts) + [user_id for user_id in stats if user_id not in accounts]:
        account = accounts.get(user_id)
        row = stats.get(user_id)
        active_days = row["active_days"] if row else 0
        first_seen, last_seen = seen.get(user_id, (None, None))
        out.append(
            {
                "id": user_id,
                "name": account["name"] if account else None,
                "email": account["email"] if account else None,
                "deleted": account is None,
                "is_admin": bool(account["is_admin"]) if account else False,
                "teams": teams.get(user_id, []),
                "created_at": account["created_at"] if account else None,
                "first_seen": first_seen,
                "last_seen": last_seen,
                "active_days": active_days,
                **(_metrics(row) if row else {"page_views": 0, "reads": 0, "writes": 0, "hits": 0}),
                "frequency": frequency(active_days, period_days),
                "top_plugins": top.get(user_id, [])[:3],
            }
        )
    out.sort(key=lambda user: (-user["active_days"], -user["hits"], (user["name"] or "").lower()))
    return out
