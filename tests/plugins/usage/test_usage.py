"""Paramètres > Utilisation : chaque requête d'un compte connecté est comptée (compte, heure, module,
route), et un administrateur en lit le rapport d'une période - adoption, modules, comptes et leur
rythme, pages et routes, carte de chaleur - filtré par équipe, compte ou module."""

from __future__ import annotations

from datetime import datetime

from support.accounts import login, signup
from support.http import assert_handler_404
from support.teams import add_team_member, create_team
from support.usage import at, usage_report

MONDAY = datetime(2026, 10, 5, 9, 30)
TUESDAY = datetime(2026, 10, 6, 14, 10)
WEEK = {"start": "2026-10-05", "end": "2026-10-11"}


def _alice_uses_lots(client, monkeypatch) -> dict:
    """Boss (le premier compte, administrateur) ne fait rien ; Alice ouvre les lots lundi et
    mardi, les lit et change son nom."""
    signup(client, "boss@example.com", name="Boss")
    at(monkeypatch, MONDAY)
    alice = signup(client, "alice@example.com", name="Alice")
    assert client.get("/lots").status_code == 200
    assert client.get("/api/lots").status_code == 200
    assert client.patch("/api/users/me", json={"name": "Alice B"}).status_code == 200
    at(monkeypatch, TUESDAY)
    assert client.get("/lots").status_code == 200
    login(client, "boss@example.com")  # ferme la session d'Alice : une écriture d'Alice
    return alice


def _by(items: list[dict], key: str) -> dict:
    return {item[key]: item for item in items}


def test_an_admin_reads_who_used_what_and_how_often(client, monkeypatch):
    alice = _alice_uses_lots(client, monkeypatch)
    report = usage_report(client, **WEEK)

    totals = report["totals"]
    assert (totals["active_users"], totals["registered_users"], totals["adoption_rate"]) == (1, 2, 0.5)
    assert (totals["page_views"], totals["reads"], totals["writes"]) == (2, 1, 2)
    assert totals["plugins_used"] == 2  # lots, accounts
    assert totals["avg_daily_active"] == 0.4 and totals["peak_daily_active"] == 1  # 2 jours actifs sur 5 ouvrés
    assert report["tracking_since"] == "2026-10-05"

    assert [point["bucket"] for point in report["series"]] == [f"2026-10-{day:02d}" for day in range(5, 12)]
    assert [point["active_users"] for point in report["series"]] == [1, 1, 0, 0, 0, 0, 0]

    plugins = _by(report["plugins"], "name")
    lots = plugins["lots"]
    assert (lots["title"], lots["users"], lots["adoption_rate"], lots["page_views"], lots["reads"], lots["writes"]) == ("Lots", 1, 1.0, 2, 1, 0)
    assert lots["last_used"] == "2026-10-06"
    assert plugins["accounts"]["writes"] == 2
    assert plugins["notebook"]["users"] == 0 and plugins["notebook"]["last_used"] is None  # jamais utilisé, listé quand même
    assert "usage" not in plugins  # regarder le rapport ne compte pas : le module ne se mesure pas
    assert {item["name"] for item in report["catalog"]} == set(plugins)

    users = _by(report["users"], "email")
    mine = users["alice@example.com"]
    assert (mine["id"], mine["name"], mine["active_days"], mine["frequency"]) == (alice["id"], "Alice B", 2, "weekly")
    assert (mine["first_seen"], mine["last_seen"]) == ("2026-10-05", "2026-10-06")
    assert mine["top_plugins"][0]["plugin"] == "lots"
    assert (users["boss@example.com"]["frequency"], users["boss@example.com"]["is_admin"]) == ("inactive", True)

    routes = {(route["kind"], route["method"], route["route"]): route for route in report["routes"]}
    page = routes[("page", "GET", "/lots")]
    assert (page["title"], page["hits"], page["users"]) == ("Suivi des lots", 2, 1)
    assert routes[("api", "PATCH", "/api/users/me")]["hits"] == 1
    assert routes[("api", "DELETE", "/api/sessions/current")]["plugin"] == "accounts"

    heat = {(cell["weekday"], cell["hour"]): cell["hits"] for cell in report["heatmap"]}
    assert heat == {(0, 9): 3, (1, 14): 2}


def test_the_report_compares_with_the_previous_period_and_groups_by_week_or_month(client, monkeypatch):
    _alice_uses_lots(client, monkeypatch)
    next_week = usage_report(client, start="2026-10-12", end="2026-10-18")
    assert next_week["totals"]["active_users"] == 0 and next_week["previous"]["active_users"] == 1
    assert next_week["period"]["previous_start"] == "2026-10-05"
    assert _by(next_week["plugins"], "name")["lots"]["previous_hits"] == 3
    assert _by(next_week["users"], "email")["alice@example.com"]["frequency"] == "inactive"

    weekly = usage_report(client, start="2026-09-30", end="2026-10-14", granularity="week")
    assert [(point["bucket"], point["active_users"]) for point in weekly["series"]] == [
        ("2026-09-28", 0), ("2026-10-05", 1), ("2026-10-12", 0)
    ]
    monthly = usage_report(client, start="2026-09-15", end="2026-10-31", granularity="month")
    assert [point["bucket"] for point in monthly["series"]] == ["2026-09-01", "2026-10-01"]
    assert {(row["bucket"], row["plugin"]) for row in monthly["plugin_series"]} == {("2026-10-01", "lots"), ("2026-10-01", "accounts")}


def test_the_report_filters_by_team_account_module_and_admins(client, monkeypatch):
    alice = _alice_uses_lots(client, monkeypatch)
    team = create_team(client, "Épitaxie")
    assert add_team_member(client, team["slug"], "alice@example.com").status_code == 201

    by_team = usage_report(client, team=team["slug"], **WEEK)
    assert (by_team["totals"]["registered_users"], by_team["totals"]["adoption_rate"]) == (1, 1.0)
    assert [user["email"] for user in by_team["users"]] == ["alice@example.com"]
    assert by_team["users"][0]["teams"] == ["Épitaxie"]

    without_admins = usage_report(client, include_admins="false", **WEEK)
    assert without_admins["totals"]["registered_users"] == 1

    only_lots = usage_report(client, plugin="lots", **WEEK)
    assert [plugin["name"] for plugin in only_lots["plugins"]] == ["lots"]
    assert only_lots["totals"]["writes"] == 0 and only_lots["totals"]["page_views"] == 2
    assert len(only_lots["catalog"]) > 10

    one = usage_report(client, user_id=alice["id"], **WEEK)
    assert [user["id"] for user in one["users"]] == [alice["id"]]
    assert one["totals"]["registered_users"] == 1

    assert_handler_404(client.get("/api/usage", params={"plugin": "nope"}))
    assert_handler_404(client.get("/api/usage", params={"team": "nope"}))


def test_the_period_is_checked(client):
    signup(client, "boss@example.com")
    default = usage_report(client)
    assert default["period"]["days"] == 30 and len(default["series"]) == 30
    for params, code in (
        ({"start": "2026-10-10", "end": "2026-10-01"}, "invalid_period"),
        ({"granularity": "hour"}, "invalid_granularity"),
        ({"start": "2020-01-01", "end": "2026-01-01"}, "invalid_period"),
        ({"start": "2024-01-01", "end": "2026-01-01", "granularity": "day"}, "invalid_period"),
    ):
        response = client.get("/api/usage", params=params)
        assert (response.status_code, response.json()["code"]) == (422, code), params


def test_only_an_admin_reads_the_usage(client):
    signup(client, "boss@example.com")
    signup(client, "alice@example.com")
    assert client.get("/api/usage").status_code == 403
    assert client.get("/parametres/utilisation").status_code == 200  # la page dit « Réservé aux administrateurs »


def test_anonymous_requests_are_not_counted_and_a_disabled_plugin_counts_nothing(client, monkeypatch):
    at(monkeypatch, MONDAY)
    client.get("/connexion")
    signup(client, "boss@example.com")
    assert usage_report(client, **WEEK)["totals"]["hits"] == 0

    assert client.patch("/api/plugins/usage", json={"enabled": False}).status_code == 200
    client.get("/lots")
    client.get("/api/lots")
    assert client.patch("/api/plugins/usage", json={"enabled": True}).status_code == 200
    totals = usage_report(client, **WEEK)["totals"]
    # rien d'éteint n'a compté ; seul le réveil compte - l'usage est rallumé quand sa réponse part
    assert (totals["page_views"], totals["reads"], totals["writes"]) == (0, 0, 1)

    client.get("/lots")
    assert usage_report(client, **WEEK)["totals"]["page_views"] == 1


def test_the_settings_menu_links_the_usage_page_only_while_the_plugin_is_on(client):
    signup(client, "boss@example.com")
    page = client.get("/parametres/plugins").text
    assert "/static/settings/sections.js" in page
    client.patch("/api/plugins/usage", json={"enabled": False})
    assert 'data-plugins-off="kpis_demo usage"' in client.get("/parametres/plugins").text
    assert client.get("/parametres/utilisation").status_code == 404
