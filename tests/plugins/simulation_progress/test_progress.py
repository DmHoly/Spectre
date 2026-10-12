"""La barre de chargement du constructeur : la page donne un identifiant à sa simulation
(``POST /api/simulations?run=``), puis en lit l'avancement (``GET /api/simulation-runs/{run}``) ;
éteint, le plugin laisse le constructeur simuler comme avant, sans barre."""

from __future__ import annotations

from collections import OrderedDict

import pytest

from spectre.plugins.structures import simulation as structures_simulation
from support.accounts import signup
from support.http import assert_handler_404, assert_ok, plugins_off
from support.structures import simulate, steps, substrate

RUN = "0a1b2c3d4e5f60718293a4b5"
BUILDER = "/microprojets/x/structures/nouvelle"


@pytest.fixture(autouse=True)
def fresh_checkpoints(monkeypatch):
    """Les états gardés d'une autre simulation du processus feraient « reprendre » des étapes ici."""
    monkeypatch.setattr(structures_simulation, "_checkpoints", OrderedDict())


def _simulate(client, run: str | None = RUN):
    url = "/api/simulations" + (f"?run={run}" if run else "")
    return client.post(url, json={"substrate": substrate(), "steps": steps()})


def test_a_simulation_can_be_followed_under_the_id_the_page_gave_it(client):
    signup(client, "boss@example.com", name="Boss")
    assert _simulate(client).status_code == 200
    progress = assert_ok(client.get(f"/api/simulation-runs/{RUN}"))
    assert (progress["state"], progress["total"], progress["done"]) == ("done", 1, 1)
    assert progress["step"] is None and progress["elapsed"] >= 0
    assert progress["resumed"] == 0

    again = _simulate(client, "ffffeeeeddddcccc")  # le même procédé : tout est repris sans calcul
    assert again.status_code == 200
    assert assert_ok(client.get("/api/simulation-runs/ffffeeeeddddcccc"))["resumed"] == 1


def test_an_unknown_or_malformed_run_is_a_404(client):
    signup(client, "boss@example.com", name="Boss")
    assert_handler_404(client.get("/api/simulation-runs/jamais-parti-0000"), "Simulation inconnue")
    assert_handler_404(client.get("/api/simulation-runs/x"), "Simulation inconnue")


def test_a_malformed_run_id_is_refused_when_simulating(client):
    signup(client, "boss@example.com", name="Boss")
    assert _simulate(client, "pas valide!").status_code == 422
    assert _simulate(client, "court").status_code == 422


def test_a_simulation_without_an_id_works_as_before(client):
    signup(client, "boss@example.com", name="Boss")
    assert simulate(client, {"substrate": substrate(), "steps": steps()}).status_code == 200


@pytest.mark.parametrize("asset", ["simulation_progress/client.js", "simulation_progress/simulation-progress.js", "simulation_progress/simulation-progress.css"])
def test_the_builder_loads_the_bar_and_turning_the_plugin_off_removes_it(client, asset):
    signup(client, "boss@example.com", name="Boss")  # le premier compte est administrateur
    assert f"/static/{asset}" in client.get(BUILDER).text

    assert client.patch("/api/plugins/simulation_progress", json={"enabled": False}).status_code == 200
    off = client.get(BUILDER).text
    assert f"/static/{asset}" not in off and "simulation_progress" in plugins_off(off)
    refused = client.get(f"/api/simulation-runs/{RUN}")
    assert (refused.status_code, refused.json()["code"]) == (404, "plugin_disabled")
    assert _simulate(client).status_code == 200  # le constructeur simule sans lui

    assert client.patch("/api/plugins/simulation_progress", json={"enabled": True}).json()["active"]
    assert f"/static/{asset}" in client.get(BUILDER).text
