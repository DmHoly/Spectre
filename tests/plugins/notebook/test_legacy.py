"""Les données d'une étude d'avant le cahier unique, écrites ici comme l'ancien code les écrivait
(``support.notebook.write_legacy`` : Follow seul, hors de Spectre) : les vues de l'ancien cahier
(``data_notebook``) et les preuves Follow avec ce que Spectre rangeait pour elles (``evidence_extra``,
``evidence_links``, images dans ``attachments``). Elles se lisent comme des entrées du cahier, sans
qu'aucune version soit réécrite ; la première écriture dans le cahier enregistre le cahier converti
dans la version qu'elle crée, et les anciennes clés n'y sont plus écrites."""

from __future__ import annotations

import follow
import pytest

from spectre.plugins.experiments import service as experiments
from spectre.plugins.experiments.repository import get_repository
from support.experiments import conclude, evolve, get_experiment, launch, step_ids, tag, versions
from support.microprojects import signup_with_microproject
from support.notebook import (
    add_manual,
    as_input,
    entries,
    entries_by_id,
    legacy_evidence,
    legacy_view,
    objects_checksums,
    step_counts,
    take_snapshot,
    update_entry,
    upload_notebook_file,
    write_legacy,
)
from support.structures import deposition, etch


@pytest.fixture()
def demo_data(monkeypatch):
    monkeypatch.setenv("SPECTRE_DEMO_DATA", "1")


def _three_steps() -> list[dict]:
    return [deposition("Épitaxie", "GaN", thickness_nm=200), etch("Etch back", depth_nm=50), deposition("Contacts", "Ti", thickness_nm=30)]


def _old_study(client, slug):
    """Une étude d'avant : un procédé de trois étapes enregistré sans ids d'étape, une vue de l'ancien
    cahier, et des preuves de chaque sorte - mesure chiffrée à une étape, liens web et chemin réseau,
    images légendées et annotées, objectif et interprétation ; plusieurs mesures ; un ancien
    graphique. Renvoie ce qu'il faut pour les relire."""
    line = launch(client, slug, steps=_three_steps(), objectives=[{"name": "Rugosité", "metric": "rugosite_rms", "direction": "minimize"}])["id"]
    snapshot = take_snapshot(client, slug)
    tem = upload_notebook_file(client, slug, "tem.png")
    sem = upload_notebook_file(client, slug, "sem.png")
    images = [
        {"id": tem, "filename": "tem.png", "content_type": "image/png", "size": 68, "caption": "Vue d'ensemble"},
        {"id": sem, "filename": "sem.png", "content_type": "image/png", "size": 68, "caption": None},
    ]
    annotations = [
        {"attachment_id": sem, "type": "box", "x": 10.0, "y": 20.0, "x2": 30.0, "y2": 40.0, "label": "défaut"},
        {"type": "arrow", "x": 1.0, "y": 2.0, "x2": 3.0, "y2": 4.0, "label": None},  # d'avant l'image désignée : la première
    ]

    def old(builder, parent):
        legacy_view(builder, "nb_ancienne", snapshot, title="EQE vs J", component="eqe-curves", note="Pas d'écart", objective="Rugosité", in_report=False)
        legacy_evidence(
            builder,
            "a1b2c3d4e5f6",
            "Imagerie AFM : rugosité RMS mesurée à 1.2 nm",
            source="AFM salle blanche",
            metrics={"rugosite_rms": {"value": 1.2, "unit": "nm"}},
            step_index=1,
            links=["https://aledia.sharepoint.com/sites/rd/W1", "\\\\srv-data\\R&D\\Runs\\W1"],
            images=images,
            kind="image",
            objective="Rugosité",
            interpretation="Nette amélioration",
            image_annotations=annotations,
        )
        legacy_evidence(
            builder,
            "ev-mesures",
            "Mesures 4 pointes",
            source="https://labo.example/run/42",
            metrics={"rs": {"value": 4.2, "unit": "Ω·mm²", "uncertainty": 0.1}, "operateur": {"value": "Léa"}},
            links=["https://labo.example/run/42"],
        )
        legacy_evidence(builder, "ev-graphe", "Split vs PL", source="—", kind="graph", graph_config={"title": "Split vs PL", "x_label": "Épaisseur (nm)", "y_label": "PL", "query": "TODO"})
        builder.conclusion = follow.Conclusion(
            status="concluded",
            objective_results=[follow.ObjectiveResult(objective="Rugosité", status="met", evidence_ids=["a1b2c3d4e5f6"])],
        )

    version = write_legacy(slug, line, old, keep_step_ids=False)
    return {"line": line, "version": version, "snapshot": snapshot, "tem": tem, "sem": sem}


def test_old_views_and_old_evidence_read_as_notebook_entries(client, demo_data):
    slug = signup_with_microproject(client, "legacy-read@example.com")
    study = _old_study(client, slug)
    line = study["line"]
    notebook = entries_by_id(client, slug, line)
    assert list(notebook) == ["nb_ancienne", "a1b2c3d4e5f6", "ev-mesures", "ev-graphe"]
    assert get_experiment(client, slug, line)["notebook_count"] == 4

    view = notebook["nb_ancienne"]
    assert (view["kind"], view["title"], view["note"], view["objective"], view["in_report"], view["wafers"], view["applies"]) == (
        "prism", "EQE vs J", "Pas d'écart", "Rugosité", False, [], True
    )
    [measurement] = view["measurements"]
    assert (measurement["step_id"], measurement["snapshot_id"], measurement["component"]) == (None, study["snapshot"]["snapshot_id"], "eqe-curves")
    assert measurement["snapshot"]["hook"] == "eqe" and measurement["snapshot"]["wafers"] == study["snapshot"]["wafers"]
    assert view["created_by"] == "Ada"

    # une preuve garde son id ; son step_index devient l'id de l'étape, celui que lit la version
    afm = notebook["a1b2c3d4e5f6"]
    assert (afm["kind"], afm["title"], afm["objective"], afm["interpretation"]) == ("manual", "Imagerie AFM : rugosité RMS mesurée à 1.2 nm", "Rugosité", "Nette amélioration")
    [measurement] = afm["measurements"]
    assert measurement["step_id"] == step_ids(client, slug, line)[1] and measurement["step_retired"] is False
    assert measurement["value"] == {"number": 1.2, "unit": "nm", "name": "rugosite_rms"}
    assert measurement["links"] == [{"label": None, "url": "https://aledia.sharepoint.com/sites/rd/W1"}]
    assert measurement["text"] == "Référence : AFM salle blanche\nChemin : \\\\srv-data\\R&D\\Runs\\W1"
    assert [(a["id"], a["caption"]) for a in measurement["attachments"]] == [(study["tem"], "Vue d'ensemble"), (study["sem"], None)]
    assert all(client.get(a["url"]).status_code == 200 for a in measurement["attachments"])
    assert [(a["attachment_id"], a["type"], a["label"]) for a in measurement["annotations"]] == [(study["sem"], "box", "défaut"), (study["tem"], "arrow", None)]
    # l'auteur et la date de la version qui l'a ajoutée
    added = next(v for v in versions(client, slug, line) if v["version_id"] == study["version"])
    assert (afm["created_by"], afm["created_at"]) == ("Ada", added["created_at"])

    # plusieurs mesures, ou une valeur non chiffrée : un tableau ; la source qui est un lien n'est pas répétée
    several = notebook["ev-mesures"]["measurements"][0]
    assert several["value"] is None and several["text"] is None
    assert several["table"] == {"columns": ["Mesure", "Valeur", "Unité", "Incertitude"], "rows": [["rs", 4.2, "Ω·mm²", 0.1], ["operateur", "Léa", None, None]]}
    assert several["links"] == [{"label": None, "url": "https://labo.example/run/42"}]
    # un ancien graphique : sa description, rien n'est relu
    assert notebook["ev-graphe"]["measurements"][0]["text"] == "Référence : —\nGraphique (description seule) - Split vs PL ; axes : Épaisseur (nm) / PL ; requête : TODO"

    # filtres et décompte par étape, comme pour une entrée écrite aujourd'hui
    assert [e["id"] for e in entries(client, slug, line, kind="prism")] == ["nb_ancienne"]
    assert client.get(f"/api/microprojects/{slug}/experiments/{line}/notebook-entries", params={"summary": "steps"}).json() == {step_ids(client, slug, line)[1]: 1}
    # la conclusion cite toujours la preuve, par son id
    assert get_experiment(client, slug, line)["conclusion"]["objective_results"][0]["evidence_ids"] == ["a1b2c3d4e5f6"]


def test_reading_and_unrelated_writes_rewrite_nothing(client, demo_data):
    slug = signup_with_microproject(client, "legacy-immutable@example.com")
    study = _old_study(client, slug)
    line = study["line"]
    before = objects_checksums(slug)
    first = entries(client, slug, line)

    # une écriture qui ne touche pas au cahier le reporte tel quel, dans l'ancien format
    tag(client, slug, line, ["relu"])
    tip = get_repository(slug).get(get_experiment(client, slug, line)["version_id"])
    assert "data_notebook" in tip.metadata and [e.id for e in tip.evidence] == ["a1b2c3d4e5f6", "ev-mesures", "ev-graphe"]
    assert experiments.NOTEBOOK_KEY not in tip.metadata
    assert entries(client, slug, line) == first
    # une modification sans effet d'une entrée convertie n'écrit rien non plus
    count = len(versions(client, slug, line))
    afm = next(e for e in first if e["id"] == "a1b2c3d4e5f6")
    assert update_entry(client, slug, line, "a1b2c3d4e5f6", interpretation="Nette amélioration", measurements=[as_input(m) for m in afm["measurements"]]) == afm
    assert len(versions(client, slug, line)) == count
    after = objects_checksums(slug)
    assert {name: after[name] for name in before} == before  # aucun objet Follow réécrit


def test_the_first_notebook_write_stores_the_converted_notebook(client, demo_data):
    slug = signup_with_microproject(client, "legacy-persist@example.com")
    study = _old_study(client, slug)
    line, old_version = study["line"], study["version"]
    converted = entries_by_id(client, slug, line)
    before = objects_checksums(slug)

    edited = update_entry(client, slug, line, "a1b2c3d4e5f6", interpretation="Revue en réunion")
    assert edited["interpretation"] == "Revue en réunion" and edited["updated_by"] == "T"

    # la nouvelle version porte le cahier converti, et plus les anciennes clés ni les preuves Follow
    tip = get_repository(slug).get(get_experiment(client, slug, line)["version_id"])
    assert [entry["id"] for entry in tip.metadata[experiments.NOTEBOOK_KEY]] == ["nb_ancienne", "a1b2c3d4e5f6", "ev-mesures", "ev-graphe"]
    assert not {"data_notebook", "evidence_extra", "evidence_links", "attachments"} & tip.metadata.keys()
    assert tip.evidence == []
    # ce qui se lit n'a pas changé, hors du champ modifié
    now = entries_by_id(client, slug, line)
    assert {key: entry for key, entry in now.items() if key != "a1b2c3d4e5f6"} == {key: entry for key, entry in converted.items() if key != "a1b2c3d4e5f6"}
    assert {**now["a1b2c3d4e5f6"], "interpretation": None, "updated_at": None, "updated_by": None} == {
        **converted["a1b2c3d4e5f6"],
        "interpretation": None,
        "updated_at": None,
        "updated_by": None,
    }
    assert get_experiment(client, slug, line)["notebook_count"] == 4
    # la conclusion cite toujours la preuve, devenue une entrée, et peut la citer de nouveau
    assert get_experiment(client, slug, line)["conclusion"]["objective_results"][0]["evidence_ids"] == ["a1b2c3d4e5f6"]
    result = {"objective": "Rugosité", "status": "met", "evidence_ids": ["a1b2c3d4e5f6", "ev-mesures"]}
    assert conclude(client, slug, line, objective_results=[result])["conclusion"]["objective_results"][0]["evidence_ids"] == ["a1b2c3d4e5f6", "ev-mesures"]

    # l'ancienne version, intacte, se lit toujours convertie
    assert entries_by_id(client, slug, line, old_version) == converted
    after = objects_checksums(slug)
    assert {name: after[name] for name in before} == before
    # les écritures suivantes partent du nouveau format
    added = add_manual(client, slug, line, "Nouvelle mesure")
    assert list(entries_by_id(client, slug, line)) == ["nb_ancienne", "a1b2c3d4e5f6", "ev-mesures", "ev-graphe", added["id"]]


def test_an_old_evidence_keeps_its_step_across_evolutions_and_its_images_on_write(client, demo_data):
    slug = signup_with_microproject(client, "legacy-steps@example.com")
    study = _old_study(client, slug)
    line = study["line"]
    ids = step_ids(client, slug, line)
    # une évolution qui garde les étapes (le constructeur renvoie leurs ids) et ajoute une passivation
    evolve(client, slug, line, steps=[{"id": step_id, **step} for step_id, step in zip(ids, _three_steps())] + [deposition("Passivation", "SiO2")])
    afm = entries_by_id(client, slug, line)["a1b2c3d4e5f6"]
    assert afm["measurements"][0]["step_id"] == ids[1] and afm["measurements"][0]["step_retired"] is False
    assert step_counts(client, slug, line) == {ids[1]: 1}
    # renvoyer ses mesures (ses images d'avant comprises) suffit pour les modifier
    kept = update_entry(client, slug, line, "a1b2c3d4e5f6", measurements=[{**as_input(m), "annotations": []} for m in afm["measurements"]])
    assert [a["id"] for a in kept["measurements"][0]["attachments"]] == [study["tem"], study["sem"]]
    assert kept["measurements"][0]["annotations"] == []


def test_old_links_are_read_under_todays_rule_so_the_entry_saves_as_read(client, demo_data):
    """L'ancien code gardait un lien tel que collé (espaces compris) : relu, il suit la règle des
    liens d'aujourd'hui, et la mesure se réenregistre telle quelle (une annotation, un titre)."""
    slug = signup_with_microproject(client, "legacy-links@example.com")
    line = launch(client, slug, steps=_three_steps())["id"]
    image = upload_notebook_file(client, slug, "afm.png")

    def old(builder, parent):
        legacy_evidence(
            builder,
            "ev-liens",
            "Rapport AFM",
            links=[
                "https://sharepoint.example/Documents partages/rapport AFM.pptx",
                "https://sharepoint.example/Documents%20partages/rapport%20AFM.pptx",  # le même, déjà encodé
                "https://",
                "\\srv-data\R&D\Mes runs",
            ],
            images=[{"id": image, "filename": "afm.png", "content_type": "image/png", "size": 68, "caption": None}],
            image_annotations=[{"attachment_id": image, "type": "box", "x": 1.0, "y": 2.0, "x2": 3.0, "y2": 4.0, "label": "grain"}],
        )

    write_legacy(slug, line, old)
    [measurement] = entries_by_id(client, slug, line)["ev-liens"]["measurements"]
    assert measurement["links"] == [{"label": None, "url": "https://sharepoint.example/Documents%20partages/rapport%20AFM.pptx"}]
    assert measurement["text"] == "Lien : https://\nChemin : \\srv-data\R&D\Mes runs"

    # retirer l'annotation (ce qu'envoie la fiche : toute la mesure), puis changer le titre
    saved = update_entry(client, slug, line, "ev-liens", measurements=[{**as_input(measurement), "annotations": []}])
    assert saved["measurements"][0]["links"] == measurement["links"] and saved["measurements"][0]["annotations"] == []
    assert update_entry(client, slug, line, "ev-liens", title="Rapport AFM revu")["measurements"][0]["links"] == measurement["links"]
