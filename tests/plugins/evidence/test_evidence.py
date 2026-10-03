"""Les preuves d'une étude (plugin evidence), sous ``.../experiments/{experiment_id}/evidence`` :
chacune est une écriture légère sur la piste (une nouvelle version qui reporte tout le reste), avec
ses champs propres à Spectre (type, objectif, interprétation, annotations), ses liens et ses images -
téléversées d'abord (plugin attachments, ``purpose=evidence``), rattachées dans la même version. Le
détail de l'étude n'en porte plus que le nombre."""

from __future__ import annotations

from support.accounts import login
from support.evidence import (
    add_evidence,
    annotate,
    evidence_by_id,
    evidence_url,
    list_evidence,
    post_evidence,
    put_annotations,
    upload_image,
)
from support.experiments import conclude, evolve, get_experiment, launch, tag, versions
from support.http import assert_handler_404
from support.microprojects import create_microproject, join_as, signup_with_microproject
from support.structures import steps


def test_adding_evidence_creates_a_version_and_answers_the_evidence(client):
    slug = signup_with_microproject(client, "evidence-add@example.com")
    launched = launch(client, slug)

    response = post_evidence(
        client,
        slug,
        launched["id"],
        "Mesure d'epaisseur au profilometre",
        source="https://labo.example/mesures/142",
        metric_name="thickness_nm",
        metric_value=20.3,
        metric_unit="nm",
        if_match=launched["version_id"],
    )
    assert response.status_code == 201, response.text
    added = response.json()
    assert response.headers["Location"] == f"{evidence_url(slug, launched['id'])}/{added['id']}"
    assert added["description"] == "Mesure d'epaisseur au profilometre"
    assert (added["metrics"]["thickness_nm"]["value"], added["metrics"]["thickness_nm"]["unit"]) == (20.3, "nm")

    detail = get_experiment(client, slug, launched["id"])
    assert detail["id"] == launched["id"]  # la même piste
    assert detail["version_id"] != launched["version_id"]  # une nouvelle version
    assert response.headers["ETag"] == f'"{detail["version_id"]}"'
    assert detail["evidence_count"] == 1
    assert not {"evidence", "evidence_links", "attachments"} & detail.keys()  # le détail ne fusionne plus les preuves

    single = client.get(response.headers["Location"])
    assert single.status_code == 200 and single.json() == added

    # une deuxième preuve reporte la première ; la version d'avant reste lisible
    add_evidence(client, slug, launched["id"], "Deuxieme mesure", source="https://labo.example/mesures/143")
    assert [e["description"] for e in list_evidence(client, slug, launched["id"])] == ["Mesure d'epaisseur au profilometre", "Deuxieme mesure"]
    assert [e["id"] for e in list_evidence(client, slug, launched["id"], detail["version_id"])] == [added["id"]]
    assert list_evidence(client, slug, launched["id"], launched["version_id"]) == []


def test_the_evidence_list_carries_the_etag_of_the_version_read(client):
    slug = signup_with_microproject(client, "evidence-etag@example.com")
    launched = launch(client, slug)
    response = client.get(evidence_url(slug, launched["id"]), params={"version": launched["version_id"]})
    assert response.status_code == 200 and response.headers["ETag"] == f'"{launched["version_id"]}"'
    assert_handler_404(client.get(evidence_url(slug, launched["id"]), params={"version": "exp_0000000000000000"}))
    assert_handler_404(client.get(evidence_url(slug, "piste-inconnue")))
    assert_handler_404(client.get(f"{evidence_url(slug, launched['id'])}/inconnue"), "Preuve introuvable")


def test_the_old_evidence_routes_are_gone(client):
    slug = signup_with_microproject(client, "evidence-old@example.com")
    launched = launch(client, slug)
    old = f"/api/microprojets/{slug}/experiences/{launched['id']}/preuves"
    assert client.post(old, json={"description": "x"}).status_code == 404
    assert client.post(f"{old}/abc/annotations", json={"annotations": []}).status_code == 404


def test_concluding_or_evolving_keeps_the_evidence(client):
    slug = signup_with_microproject(client, "evidence-carry@example.com")
    launched = launch(client, slug)
    add_evidence(client, slug, launched["id"], "Mesure avant evolution", source="https://labo.example/mesures/1")
    tag(client, slug, launched["id"], ["important"])

    assert conclude(client, slug, launched["id"])["evidence_count"] == 1
    evolved = evolve(client, slug, launched["id"], intent="Reduire l'epaisseur", steps=steps(thickness_nm=10))
    assert evolved["tags"] == ["important"] and evolved["evidence_count"] == 1
    assert [e["description"] for e in list_evidence(client, slug, launched["id"])] == ["Mesure avant evolution"]


def test_a_viewer_reads_the_evidence_but_cannot_add_any(client):
    slug = signup_with_microproject(client, "evidence-owner@example.com")
    launched = launch(client, slug)
    add_evidence(client, slug, launched["id"])
    image_id = upload_image(client, slug)

    join_as(client, slug, "evidence-viewer@example.com", owner="evidence-owner@example.com", role="viewer")
    assert len(list_evidence(client, slug, launched["id"])) == 1
    assert post_evidence(client, slug, launched["id"]).status_code == 403
    assert post_evidence(client, slug, launched["id"], images=[{"image_id": image_id}]).status_code == 403


def test_the_step_index_round_trips_and_must_be_within_the_process(client):
    slug = signup_with_microproject(client, "evidence-step@example.com")
    launched = launch(client, slug)  # un procédé d'une seule étape (support.structures.steps)

    assert add_evidence(client, slug, launched["id"], "Apres depot", metric_name="perf", metric_value=12.5, step_index=0)["step_index"] == 0
    assert add_evidence(client, slug, launched["id"], "Preuve generale")["step_index"] is None
    for index in (5, -1):
        assert post_evidence(client, slug, launched["id"], step_index=index).status_code == 422


def test_a_named_measure_needs_a_value(client):
    slug = signup_with_microproject(client, "evidence-metric@example.com")
    launched = launch(client, slug)
    response = post_evidence(client, slug, launched["id"], metric_name="epaisseur")
    assert response.status_code == 422 and response.json()["detail"] == "Une valeur est requise pour la mesure nommée."


def test_the_kind_defaults_to_standard_with_empty_spectre_fields(client):
    slug = signup_with_microproject(client, "evidence-default@example.com")
    launched = launch(client, slug)
    added = add_evidence(client, slug, launched["id"], "x", source="y")
    assert (added["kind"], added["objective"], added["interpretation"], added["graph_config"]) == ("standard", None, None, None)
    assert (added["annotations"], added["links"], added["images"]) == ([], [], [])


def test_the_objective_must_exist_on_the_experience(client):
    slug = signup_with_microproject(client, "evidence-objective@example.com")
    launched = launch(client, slug, objectives=[{"name": "Isolation", "metric": "r", "direction": "observe"}])
    assert post_evidence(client, slug, launched["id"], objective="Objectif inexistant").status_code == 422
    added = add_evidence(client, slug, launched["id"], objective="Isolation", interpretation="Monte")
    assert (added["objective"], added["interpretation"]) == ("Isolation", "Monte")


def test_a_graph_evidence_is_no_longer_created_but_an_old_one_still_reads(client):
    from spectre.plugins.experiments import service

    slug = signup_with_microproject(client, "evidence-graph@example.com")
    launched = launch(client, slug)
    refused = post_evidence(client, slug, launched["id"], kind="graph", graph_config={"query": "http://ailleurs.example"})
    assert refused.status_code == 422
    assert get_experiment(client, slug, launched["id"])["version_id"] == launched["version_id"]  # rien d'écrit

    # une preuve « graphique » d'avant : sa description se lit toujours
    config = {"title": "Split vs PL", "x_label": "Epaisseur (nm)", "y_label": "Intensite PL", "query": "TODO"}

    def old_graph(builder, parent):
        builder.add_evidence(id="ancien", description="Split vs PL", source="—")
        builder.metadata["evidence_extra"] = {"ancien": {"kind": "graph", "graph_config": config}}

    service.amend(slug, launched["id"], author="Test", change=old_graph)
    [old] = list_evidence(client, slug, launched["id"])
    assert (old["kind"], old["graph_config"]) == ("graph", config)


def test_spectre_fields_survive_lightweight_and_real_evolutions(client):
    # les champs propres à Spectre sont rangés dans les métadonnées de l'étude (pas sur
    # follow.Evidence, dont les champs dépendent du Follow installé) : chaque version suivante les montre
    slug = signup_with_microproject(client, "evidence-own-fields@example.com")
    launched = launch(client, slug, objectives=[{"name": "Isolation", "metric": "r", "direction": "observe"}])
    image_id = upload_image(client, slug)
    own = add_evidence(client, slug, launched["id"], "Coupe", objective="Isolation", interpretation="Monte", links=["S:\\Runs"], images=[{"image_id": image_id}])
    tag(client, slug, launched["id"], ["a-suivre"])
    other = add_evidence(client, slug, launched["id"], "Autre mesure")
    conclude(client, slug, launched["id"])
    evolve(client, slug, launched["id"], steps=steps(40))

    later = [v["version_id"] for v in versions(client, slug, launched["id"])][2:]
    assert len(later) == 4
    for version in later:
        evidence = evidence_by_id(client, slug, launched["id"], version)[own["id"]]
        assert (evidence["kind"], evidence["objective"], evidence["interpretation"], evidence["links"]) == ("image", "Isolation", "Monte", ["S:\\Runs"])
        assert [image["id"] for image in evidence["images"]] == [image_id]
    assert evidence_by_id(client, slug, launched["id"])[other["id"]]["kind"] == "standard"  # chaque preuve garde les siens


def test_a_preuve_with_links_and_pasted_images_is_one_version(client):
    slug = signup_with_microproject(client, "evidence-links@example.com")
    launched = launch(client, slug, entities=[{"sample_id": "W7"}])
    before = len(versions(client, slug, launched["id"]))
    first, second = upload_image(client, slug, "tem.png"), upload_image(client, slug)

    added = add_evidence(
        client,
        slug,
        launched["id"],
        "Coupes TEM et présentation du run",
        source="",
        links=['"\\\\srv-data\\R&D\\Runs\\W7\\revue.pptx"', "https://aledia.sharepoint.com/sites/rd/W7", "", "https://aledia.sharepoint.com/sites/rd/W7"],
        images=[{"image_id": first, "caption": " Vue d'ensemble "}, {"image_id": second}],
    )
    assert added["links"] == ["\\\\srv-data\\R&D\\Runs\\W7\\revue.pptx", "https://aledia.sharepoint.com/sites/rd/W7"]
    assert added["source"] == "\\\\srv-data\\R&D\\Runs\\W7\\revue.pptx"  # le premier lien, faute de source
    assert added["kind"] == "image"  # des images collées font une preuve image
    assert [(image["id"], image["filename"], image["caption"]) for image in added["images"]] == [(first, "tem.png", "Vue d'ensemble"), (second, "mesure.png", None)]
    content = client.get(added["images"][0]["url"])  # l'url vient du serveur
    assert content.status_code == 200 and content.headers["content-type"] == "image/png"
    # tout en une seule version (pas une par image)
    assert len(versions(client, slug, launched["id"])) == before + 1

    # une preuve suivante garde les liens des précédentes
    later = add_evidence(client, slug, launched["id"], source="profilomètre", links=["S:\\Mesures\\W7"])
    links = {key: e["links"] for key, e in evidence_by_id(client, slug, launched["id"]).items()}
    assert links == {added["id"]: added["links"], later["id"]: ["S:\\Mesures\\W7"]}


def test_a_preuve_refuses_images_that_are_not_uploaded_images_of_this_microproject(client):
    slug = signup_with_microproject(client, "evidence-images@example.com")
    elsewhere = create_microproject(client, "Ailleurs")["slug"]
    launched = launch(client, slug)
    image = upload_image(client, slug)
    for images in (
        [{"image_id": "att_" + "0" * 20}],  # jamais téléversée
        [{"image_id": "../secret"}],  # pas un id
        [{"image_id": upload_image(client, elsewhere)}],  # téléversée dans un autre µprojet
        [{"image_id": image}, {"image_id": image}],  # deux fois la même
    ):
        assert post_evidence(client, slug, launched["id"], images=images).status_code == 422, images
    assert post_evidence(client, slug, launched["id"], links=[f"https://exemple.fr/{i}" for i in range(11)]).status_code == 422
    assert get_experiment(client, slug, launched["id"])["version_id"] == launched["version_id"]  # rien d'écrit


def test_an_evidence_image_can_be_annotated(client):
    slug = signup_with_microproject(client, "evidence-annotate@example.com")
    launched = launch(client, slug)
    image_id = upload_image(client, slug, "sem.png")
    added = add_evidence(client, slug, launched["id"], "SEM du bord", images=[{"image_id": image_id}])
    shown = get_experiment(client, slug, launched["id"])["version_id"]
    annotations = [
        {"attachment_id": image_id, "type": "box", "x": 10.0, "y": 20.0, "x2": 30.0, "y2": 40.0, "label": "défaut ici"},
        {"attachment_id": image_id, "type": "arrow", "x": 5.0, "y": 5.0, "x2": 15.0, "y2": 15.0, "label": None},
    ]

    response = put_annotations(client, slug, launched["id"], added["id"], annotations, if_match=shown)
    assert response.status_code == 200, response.text
    annotated = response.json()
    assert annotated["id"] == added["id"]
    assert [a["label"] for a in annotated["annotations"]] == ["défaut ici", None]
    assert annotated["kind"] == "image"  # les champs de la preuve ont survécu à cette version aussi
    assert [image["id"] for image in annotated["images"]] == [image_id]  # l'image elle-même, reportée telle quelle
    after = get_experiment(client, slug, launched["id"])["version_id"]
    assert after != shown and response.headers["ETag"] == f'"{after}"'

    # les mêmes annotations : 200, et pas de nouvelle version
    count = len(versions(client, slug, launched["id"]))
    annotate(client, slug, launched["id"], added["id"], annotations, if_match=after)
    assert len(versions(client, slug, launched["id"])) == count


def test_annotations_reject_an_image_that_does_not_belong_to_the_preuve(client):
    slug = signup_with_microproject(client, "evidence-annotate-other@example.com")
    launched = launch(client, slug)
    first = add_evidence(client, slug, launched["id"], "SEM", images=[{"image_id": upload_image(client, slug)}])
    other_image = upload_image(client, slug, "autre.png")
    add_evidence(client, slug, launched["id"], "Autre", images=[{"image_id": other_image}])

    response = put_annotations(client, slug, launched["id"], first["id"], [{"attachment_id": other_image, "type": "box", "x": 1.0, "y": 1.0}])
    assert response.status_code == 422


def test_annotations_on_an_unknown_preuve_are_404(client):
    slug = signup_with_microproject(client, "evidence-annotate-404@example.com")
    launched = launch(client, slug)
    assert_handler_404(put_annotations(client, slug, launched["id"], "inconnue", []), "Preuve introuvable")


def test_a_viewer_cannot_annotate(client):
    slug = signup_with_microproject(client, "evidence-annotate-owner@example.com")
    launched = launch(client, slug)
    image_id = upload_image(client, slug)
    added = add_evidence(client, slug, launched["id"], images=[{"image_id": image_id}])
    join_as(client, slug, "evidence-annotate-viewer@example.com", owner="evidence-annotate-owner@example.com", role="viewer")
    assert put_annotations(client, slug, launched["id"], added["id"], []).status_code == 403
    login(client, "evidence-annotate-owner@example.com")
    assert annotate(client, slug, launched["id"], added["id"], [])["annotations"] == []

