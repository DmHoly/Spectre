"""Le chemin d'écriture d'une étude (``experiments.service.amend``) : chaque écriture légère reporte
tout le parent, une page périmée (``If-Match``) est refusée sans rien écrire, une écriture sans
effet ne crée pas de version, deux écritures simultanées ne se perdent pas, et le dépôt lu par les
requêtes vient d'un cache invalidé à chaque écriture. Plus : le diff par défaut compare des
structures, et un ancien lien vers un id de version mène à sa piste."""

from __future__ import annotations

import threading
import time

import pytest

from support.experiments import (
    add_evidence,
    conclude,
    evolve,
    evolve_image,
    experiment_url,
    get_experiment,
    launch,
    launch_image,
    merge,
    post_evolve,
    replace_structure_images,
    set_status,
    structure_diff,
    tag,
    track_entities,
    upload_image,
    versions,
)
from support.external_images import create_image_set, delete_image_set, image_sets, image_sets_url, pin_image, png_files
from support.http import assert_handler_404
from support.microprojects import signup_with_microproject
from support.notebook import add_entry, entries, entries_url, take_snapshot, update_entry
from support.structures import steps, upload_structure_image

FUTURE_KEY = "champ_spectre_futur"  # un champ que Spectre rangerait demain dans les métadonnées


@pytest.fixture()
def study(client, tmp_path, monkeypatch):
    """Une étude en images (toutes les écritures légères s'y appliquent) avec tout ce qu'une
    écriture légère doit reporter : hypothèse, contexte, objectif et sa méthode de vérification,
    réponses au formulaire, une preuve à liens et image, une vue du cahier, une galerie DATA et un
    champ Spectre que l'API ne connaît pas."""
    from spectre.plugins.experiments import service

    monkeypatch.setenv("SPECTRE_DEMO_DATA", "1")
    monkeypatch.setenv("SPECTRE_EXTERNAL_IMAGE_ROOTS", str(tmp_path))
    slug = signup_with_microproject(client, "writes@example.com", name="Ada")
    schema = {"image_id": upload_structure_image(client, slug), "kind": "schema", "caption": None}
    launched = launch_image(
        client,
        slug,
        [schema],
        hypothesis="Le puits fait 3 nm",
        context="Suite du run W40",
        objectives=[{"name": "EQE", "metric": "max_EQE", "verification_method": "Banc EQE"}],
        form_answers={"operateur": "Ada"},
        entities=[{"sample_id": "W12-A3", "location": "boîte 1"}],
    )
    line = launched["id"]
    picture = upload_image(client, slug)
    evidence = add_evidence(client, slug, line, "Coupe TEM", links=["https://exemple.fr/tem"], interpretation="Net", images=[{"image_id": picture}])
    snapshot = take_snapshot(client, slug, wafers=["W12-A3"])
    entry = add_entry(client, slug, line, snapshot["snapshot_id"], title="EQE")
    paths = png_files(tmp_path)
    data = create_image_set(client, slug, line, paths)
    service.amend(slug, line, author="Ada", change=lambda builder, parent: builder.metadata.update({FUTURE_KEY: {"garde": True}}))
    other = launch_image(client, slug, [{"image_id": upload_structure_image(client, slug), "kind": "coupe"}], title="Autre", entities=[{"sample_id": "W2"}])
    return {
        "slug": slug,
        "line": line,
        "schema": schema,
        "picture": picture,
        "evidence_id": evidence["evidence_id"],
        "entry_id": entry["id"],
        "snapshot_id": snapshot["snapshot_id"],
        "data_id": data["id"],
        "paths": paths,
        "other": other["id"],
        "before": get_experiment(client, slug, line),
    }


def _old(client, method, s, path, **kwargs):
    response = client.request(method, f"/api/microprojets/{s['slug']}/experiences/{s['line']}/{path}", **kwargs)
    assert response.status_code in (200, 201), response.text


WRITES = {
    "statut": lambda c, s: set_status(c, s["slug"], s["line"], "running"),
    "pause": lambda c, s: set_status(c, s["slug"], s["line"], "hold", hold_reason="four en panne"),
    "conclusion": lambda c, s: conclude(c, s["slug"], s["line"], summary="Fini"),
    "etiquettes": lambda c, s: tag(c, s["slug"], s["line"], ["a-suivre"]),
    "entites": lambda c, s: track_entities(c, s["slug"], s["line"], [{"sample_id": "W12-A3", "location": "boîte 2"}]),
    "images-structure": lambda c, s: replace_structure_images(c, s["slug"], s["line"], [{**s["schema"], "caption": "Schéma"}]),
    "fusion": lambda c, s: merge(c, s["slug"], s["line"], s["other"]),
    "evolution-sans-hypothese": lambda c, s: evolve_image(
        c, s["slug"], s["line"], [s["schema"]], title="Coupe", intent="Mieux dit", form_answers={"operateur": "Ada"}
    ),
    "preuve": lambda c, s: add_evidence(c, s["slug"], s["line"], "Autre mesure"),
    "annotations": lambda c, s: _old(
        c, "POST", s, f"preuves/{s['evidence_id']}/annotations", json={"annotations": [{"attachment_id": s["picture"], "type": "box", "x": 1.0, "y": 2.0}]}
    ),
    "cahier": lambda c, s: update_entry(c, s["slug"], s["line"], s["entry_id"], note="Vu"),
    "galerie-epingle": lambda c, s: pin_image(c, s["slug"], s["line"], s["data_id"], 1),
    "galerie-retrait": lambda c, s: delete_image_set(c, s["slug"], s["line"], s["data_id"]),
}


@pytest.mark.parametrize("write", WRITES)
def test_every_lightweight_write_carries_the_whole_parent(client, study, write):
    before = study["before"]
    WRITES[write](client, study)
    after = get_experiment(client, study["slug"], study["line"])

    assert after["version_id"] != before["version_id"]
    assert after["hypothesis"] == "Le puits fait 3 nm"
    assert after["context"] == "Suite du run W40"
    assert after["objective_verification"] == {"EQE": "Banc EQE"}
    assert after["form_answers"] == {"operateur": "Ada"}
    assert [o["name"] for o in after["objectives"]] == ["EQE"]
    own = next(e for e in after["evidence"] if e["id"] == study["evidence_id"])
    assert own["interpretation"] == "Net" and own["kind"] == "image"
    assert after["evidence_links"][study["evidence_id"]] == ["https://exemple.fr/tem"]
    assert study["picture"] in [a["id"] for a in after["attachments"]]
    assert [e["id"] for e in entries(client, study["slug"], study["line"])] == [study["entry_id"]]
    if write != "galerie-retrait":
        assert [d["id"] for d in image_sets(client, study["slug"], study["line"])] == [study["data_id"]]
    if write != "entites":
        assert after["physical_tracking"] == before["physical_tracking"]
    if write not in ("statut", "pause", "conclusion"):
        assert after["status"] == before["status"]

    from spectre.plugins.experiments.repository import get_repository

    tip = get_repository(study["slug"]).get(after["version_id"])
    assert tip.metadata[FUTURE_KEY] == {"garde": True}


STALE_WRITES = {
    "versions": lambda c, s, h: c.post(f"{experiment_url(s['slug'], s['line'])}/versions", headers=h, json={"structure": {"kind": "images", "images": [s["schema"]]}, "title": "x", "intent": "y"}),
    "structure-images": lambda c, s, h: c.put(f"{experiment_url(s['slug'], s['line'])}/structure-images", headers=h, json={"images": [s["schema"]]}),
    "conclusion": lambda c, s, h: c.put(f"{experiment_url(s['slug'], s['line'])}/conclusion", headers=h, json={"status": "concluded"}),
    "status": lambda c, s, h: c.put(f"{experiment_url(s['slug'], s['line'])}/status", headers=h, json={"status": "running"}),
    "tags": lambda c, s, h: c.put(f"{experiment_url(s['slug'], s['line'])}/tags", headers=h, json={"tags": ["x"]}),
    "entities": lambda c, s, h: c.put(f"{experiment_url(s['slug'], s['line'])}/entities", headers=h, json={"entities": [{"sample_id": "W9"}]}),
    "merges": lambda c, s, h: c.post(f"{experiment_url(s['slug'], s['line'])}/merges", headers=h, json={"other_experiment_id": s["other"]}),
    "delete": lambda c, s, h: c.delete(experiment_url(s["slug"], s["line"]), headers=h),
    # les anciennes routes des plugins de la vague 3, qui écrivent elles aussi sur la piste
    "preuve": lambda c, s, h: c.post(f"/api/microprojets/{s['slug']}/experiences/{s['line']}/preuves", headers=h, json={"description": "x"}),
    "annotations": lambda c, s, h: c.post(
        f"/api/microprojets/{s['slug']}/experiences/{s['line']}/preuves/{s['evidence_id']}/annotations", headers=h, json={"annotations": []}
    ),
    "cahier-ajout": lambda c, s, h: c.post(entries_url(s["slug"], s["line"]), headers=h, json={"title": "x", "snapshot_id": s["snapshot_id"], "component": "table"}),
    "cahier": lambda c, s, h: c.patch(f"{entries_url(s['slug'], s['line'])}/{s['entry_id']}", headers=h, json={"note": "x"}),
    "cahier-retrait": lambda c, s, h: c.delete(f"{entries_url(s['slug'], s['line'])}/{s['entry_id']}", headers=h),
    "galerie-ajout": lambda c, s, h: c.post(image_sets_url(s["slug"], s["line"]), headers=h, json={"image_paths": s["paths"]}),
    "galerie-epingle": lambda c, s, h: c.patch(f"{image_sets_url(s['slug'], s['line'])}/{s['data_id']}", headers=h, json={"pinned_index": 1}),
    "galerie-retrait": lambda c, s, h: c.delete(f"{image_sets_url(s['slug'], s['line'])}/{s['data_id']}", headers=h),
}


@pytest.mark.parametrize("write", STALE_WRITES)
def test_a_stale_if_match_is_refused_and_nothing_is_written(client, study, write):
    slug, line = study["slug"], study["line"]
    shown = study["before"]["version_id"]
    tag(client, slug, line, ["ailleurs"])  # quelqu'un d'autre a écrit entre-temps
    current = get_experiment(client, slug, line)
    count = len(versions(client, slug, line))

    response = STALE_WRITES[write](client, study, {"If-Match": f'"{shown}"'})
    assert response.status_code == 412, response.text
    assert response.json()["code"] == "stale_version"
    assert get_experiment(client, slug, line)["version_id"] == current["version_id"]
    assert len(versions(client, slug, line)) == count
    # et aucune autre piste n'est née
    assert {e["id"] for e in client.get(f"/api/microprojects/{slug}/experiments").json()["items"]} == {study["other"], line}


def test_a_current_if_match_is_accepted_in_any_form(client):
    slug = signup_with_microproject(client, "ifmatch@example.com")
    launched = launch(client, slug)
    url = f"{experiment_url(slug, launched['id'])}/tags"
    for i, form in enumerate(('"{}"', 'W/"{}"', "{}", "*")):
        current = get_experiment(client, slug, launched["id"])["version_id"]
        response = client.put(url, headers={"If-Match": form.format(current)}, json={"tags": [f"t{i}"]})
        assert response.status_code == 200, form
        assert response.headers["ETag"] == f'"{response.json()["version_id"]}"'
        assert response.json()["version_id"] != current


NO_OP_WRITES = {
    "tags": lambda c, slug, line: tag(c, slug, line, ["a", "b"]),
    "status": lambda c, slug, line: set_status(c, slug, line, "running"),
    "conclusion": lambda c, slug, line: conclude(c, slug, line, summary="Fini", decision="promote"),
    "entities": lambda c, slug, line: track_entities(c, slug, line, [{"sample_id": "W1", "location": "boîte"}]),
}


@pytest.mark.parametrize("write", NO_OP_WRITES)
def test_a_write_without_effect_creates_no_version(client, write):
    slug = signup_with_microproject(client, "noop@example.com")
    line = launch(client, slug)["id"]
    first = NO_OP_WRITES[write](client, slug, line)
    count = len(versions(client, slug, line))

    again = NO_OP_WRITES[write](client, slug, line)
    assert again["version_id"] == first["version_id"]
    assert len(versions(client, slug, line)) == count


def test_an_evolution_without_change_answers_200_and_creates_no_version(client):
    slug = signup_with_microproject(client, "noop-evolve@example.com")
    launched = launch(client, slug, title="Essai", intent="Verifier")
    response = post_evolve(client, slug, launched["id"], title="Essai", intent="Verifier")
    assert response.status_code == 200
    assert response.json()["version_id"] == launched["version_id"]
    assert "Location" not in response.headers
    assert len(versions(client, slug, launched["id"])) == 1


def test_two_writes_on_two_lines_at_once_both_survive(client):
    from spectre.plugins.experiments import service

    slug = signup_with_microproject(client, "concurrent@example.com")
    lines = [launch(client, slug, title=f"Piste {i}", entities=[{"sample_id": f"W{i}"}])["id"] for i in range(2)]

    for round_ in range(3):
        barrier = threading.Barrier(len(lines))
        errors: list[BaseException] = []

        def write(line: str) -> None:
            def change(builder, parent):
                time.sleep(0.02)  # élargit la fenêtre entre la lecture du dépôt et l'écriture de refs.json
                builder.tags = [f"tour-{round_}"]

            try:
                barrier.wait()
                service.amend(slug, line, author="Test", change=change)
            except BaseException as exc:  # noqa: BLE001 - remonté au thread principal
                errors.append(exc)

        threads = [threading.Thread(target=write, args=(line,)) for line in lines]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert not errors

        for line in lines:
            assert get_experiment(client, slug, line)["tags"] == [f"tour-{round_}"]  # aucune pointe perdue
            assert len(versions(client, slug, line)) == round_ + 2


def test_two_writes_from_the_same_page_on_one_line_let_only_one_through(client):
    from spectre.kernel.errors import PreconditionFailed
    from spectre.plugins.experiments import service

    slug = signup_with_microproject(client, "concurrent-same@example.com")
    launched = launch(client, slug)
    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def write(label: str) -> None:
        barrier.wait()
        try:
            service.set_tags(slug, launched["id"], [label], author="Test", expected_version=launched["version_id"])
            outcomes.append("ok")
        except PreconditionFailed:
            outcomes.append("412")

    threads = [threading.Thread(target=write, args=(label,)) for label in ("a", "b")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(outcomes) == ["412", "ok"]
    assert len(versions(client, slug, launched["id"])) == 2


def test_reads_are_served_from_a_cache_that_every_write_invalidates(client):
    from spectre.plugins.experiments import repository

    slug = signup_with_microproject(client, "cache@example.com")
    launched = launch(client, slug)
    first = repository.get_repository(slug)
    assert repository.get_repository(slug) is first  # rien n'a bougé : la même instance

    with repository.writing(slug) as written:
        assert written is not first  # on n'écrit jamais dans l'instance que les lectures partagent

    tag(client, slug, launched["id"], ["apres"])
    reloaded = repository.get_repository(slug)
    assert reloaded is not first
    assert get_experiment(client, slug, launched["id"])["tags"] == ["apres"]

    # une écriture faite hors de Spectre (un script) se voit aussi : la signature du dépôt a changé
    import follow

    time.sleep(0.05)
    outside = follow.Repository(repository.follow_repo_path(slug))
    builder = outside.derive(launched["id"], title="Retouche", intent="x", hypothesis=None)
    builder.metadata = dict(outside.get(launched["id"]).metadata)
    builder.commit()
    assert repository.get_repository(slug) is not reloaded
    assert get_experiment(client, slug, launched["id"])["title"] == "Retouche"


def test_the_default_diff_after_a_tag_compares_structures(client):
    # avant : le diff comparait au parent immédiat - « identique à la version précédente » dès
    # qu'une étiquette s'y glissait
    slug = signup_with_microproject(client, "diff-tag@example.com")
    launched = launch(client, slug, steps=steps(20))
    evolve(client, slug, launched["id"], intent="Plus mince", steps=steps(10))
    tag(client, slug, launched["id"], ["a-suivre"])

    diff = structure_diff(client, slug, launched["id"])
    assert diff["target"]["version_id"] == launched["version_id"]
    assert diff["entries"]


def test_the_first_structure_has_nothing_to_compare_with(client):
    slug = signup_with_microproject(client, "diff-first@example.com")
    launched = launch(client, slug)
    tag(client, slug, launched["id"], ["x"])
    assert structure_diff(client, slug, launched["id"]) == {"target": None, "entries": []}


def test_an_old_version_link_resolves_to_its_line(client):
    slug = signup_with_microproject(client, "legacy-link@example.com")
    launched = launch(client, slug)
    tagged = tag(client, slug, launched["id"], ["x"])

    resolved = client.get(f"/api/microprojects/{slug}/experiment-versions/{launched['version_id']}")
    assert resolved.json() == {"experiment_id": launched["id"], "version_id": launched["version_id"]}
    assert_handler_404(client.get(f"/api/microprojects/{slug}/experiment-versions/exp_0000000000000000"))

    page = client.get(f"/microprojets/{slug}/experiences/{launched['version_id']}", follow_redirects=False)
    assert page.status_code == 302
    assert page.headers["location"] == f"/microprojets/{slug}/experiences/{launched['id']}?version={launched['version_id']}"
    tip = client.get(f"/microprojets/{slug}/experiences/{tagged['version_id']}", follow_redirects=False)
    assert tip.headers["location"] == f"/microprojets/{slug}/experiences/{launched['id']}"  # la pointe : la page de la piste
    assert client.get(f"/microprojets/{slug}/experiences/{launched['id']}").status_code == 200  # la page elle-même

    unknown = client.get(f"/microprojets/{slug}/experiences/exp_0000000000000000", follow_redirects=False)
    assert unknown.headers["location"] == f"/microprojets/{slug}"

    client.cookies.clear()
    anonymous = client.get(f"/microprojets/{slug}/experiences/{launched['version_id']}", follow_redirects=False)
    assert anonymous.status_code == 302 and anonymous.headers["location"].startswith("/connexion?suite=")
