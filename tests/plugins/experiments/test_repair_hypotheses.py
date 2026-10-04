"""scripts/repair_hypotheses.py : restaure, sur la dernière version d'une piste, l'hypothèse que les
anciennes évolutions légères effaçaient (B1) - à blanc par défaut, ``--apply`` pour écrire. Exercé ici
sur les données du test, jamais sur ``data/``."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from support.experiments import get_experiment, launch, tag, versions
from support.microprojects import signup_with_microproject

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "repair_hypotheses.py"


@pytest.fixture()
def script(monkeypatch):
    spec = importlib.util.spec_from_file_location("repair_hypotheses", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)  # ses dataclasses relisent leurs annotations dans le module
    spec.loader.exec_module(module)
    return module


def _lose_the_hypothesis(slug, experiment_id):
    """Ce que faisaient les anciennes évolutions légères : une version sans l'hypothèse."""
    from spectre.plugins.experiments import service

    def change(builder, parent):
        builder.hypothesis = None
        builder.tags = ["etiquette"]

    service.amend(slug, experiment_id, author="Ancien code", change=change)


def test_the_script_reports_then_restores_lost_hypotheses(client, data_dir, script, capsys):
    slug = signup_with_microproject(client, "repair@example.com")
    lost = launch(client, slug, title="Perdue", hypothesis="L'oxyde isole à 20 nm")
    _lose_the_hypothesis(slug, lost["id"])
    tag(client, slug, lost["id"], ["encore"])
    kept = launch(client, slug, title="Intacte", hypothesis="Rien à faire", entities=[{"sample_id": "W2"}])
    never = launch(client, slug, title="Jamais", entities=[{"sample_id": "W3"}])
    count = len(versions(client, slug, lost["id"]))

    assert script.main(["--data-dir", str(data_dir)]) == 0
    report = capsys.readouterr().out
    assert "à blanc" in report and f"{slug} / {lost['id']}" in report and "L'oxyde isole à 20 nm" in report
    assert kept["id"] not in report and never["id"] not in report
    assert len(versions(client, slug, lost["id"])) == count  # rien d'écrit
    assert get_experiment(client, slug, lost["id"])["hypothesis"] is None

    assert script.main(["--data-dir", str(data_dir), "--apply"]) == 0
    repaired = get_experiment(client, slug, lost["id"])
    assert repaired["hypothesis"] == "L'oxyde isole à 20 nm"
    assert repaired["tags"] == ["encore"] and repaired["author"] == script.AUTHOR  # le reste est reporté
    assert len(versions(client, slug, lost["id"])) == count + 1

    capsys.readouterr()
    assert script.main(["--data-dir", str(data_dir), "--apply"]) == 0
    assert "Aucune hypothèse à restaurer." in capsys.readouterr().out


def test_a_fork_does_not_take_the_hypothesis_of_the_track_it_left(client, data_dir, script, capsys):
    """``log`` descend au-delà du point de fourche : la piste d'origine a son hypothèse, pas la fourche."""
    slug = signup_with_microproject(client, "fork@example.com")
    origin = launch(client, slug, title="Origine", hypothesis="Trois périodes suffisent")
    fork = launch(
        client,
        slug,
        title="Fourche",
        entities=[{"sample_id": "W2"}],
        branch="fourche",
        from_version={"experiment_id": origin["id"], "version_id": origin["version_id"]},
    )
    tag(client, slug, fork["id"], ["sans-hypothese"])
    count = len(versions(client, slug, fork["id"]))

    assert script.main(["--data-dir", str(data_dir), "--apply"]) == 0
    assert "Aucune hypothèse à restaurer." in capsys.readouterr().out
    assert get_experiment(client, slug, fork["id"])["hypothesis"] is None
    assert len(versions(client, slug, fork["id"])) == count
