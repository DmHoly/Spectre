"""Comparer la structure d'une étude à celle d'une étude d'un autre µprojet (``structure-diff`` avec
``against_microproject``), qui exige d'avoir accès aux deux. Le cahier de données est testé
dans ``tests/plugins/notebook``."""

from __future__ import annotations

from support.accounts import login, signup
from support.experiments import experiment_url, launch, structure_diff
from support.microprojects import create_microproject, signup_with_microproject
from support.structures import steps


def test_cross_microproject_diff(client):
    signup(client, "cross@example.com", name="Cross")
    slug_a = create_microproject(client, "Projet A")["slug"]
    slug_b = create_microproject(client, "Projet B")["slug"]

    exp_a = launch(client, slug_a, title="Essai A")
    exp_b = launch(client, slug_b, title="Essai B", steps=steps(thickness_nm=40), entities=[{"sample_id": "W2"}])

    body = structure_diff(client, slug_a, exp_a["id"], against_microproject=slug_b, against_experiment=exp_b["id"])
    assert body["target"] == {"experiment_id": exp_b["id"], "version_id": exp_b["version_id"], "title": "Essai B", "microproject": "Projet B"}
    assert len(body["entries"]) >= 1
    # sans l'expérience à comparer, l'autre µprojet ne suffit pas
    missing = client.get(f"{experiment_url(slug_a, exp_a['id'])}/structure-diff", params={"against_microproject": slug_b})
    assert missing.status_code == 422


def test_cross_microproject_diff_requires_access_to_other_microproject(client):
    signup(client, "admin@example.com")  # le premier compte est admin : il a accès à tout µprojet
    slug_c = signup_with_microproject(client, "ownerC@example.com", "Projet C", name="C")
    exp_c = launch(client, slug_c, title="Essai C")

    slug_d = signup_with_microproject(client, "ownerD@example.com", "Projet D privé", name="D")
    exp_d = launch(client, slug_d, title="Essai D")

    login(client, "ownerC@example.com")
    response = client.get(
        f"{experiment_url(slug_c, exp_c['id'])}/structure-diff", params={"against_microproject": slug_d, "against_experiment": exp_d["id"]}
    )
    assert response.status_code == 403
