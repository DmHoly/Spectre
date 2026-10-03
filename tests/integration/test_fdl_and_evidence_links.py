"""FDL (feuilles de lancement JIRA, spectre.plugins.wafers.fdl) stacked on each wafer - normalized, carried
along the versions, searchable from the topbar - and preuves carrying links (a folder, a PowerPoint
deck) and pasted images, recorded in one version.
"""

from __future__ import annotations

from spectre.plugins.experiments.entities import clean_fdl_list, normalize_fdl

from support.experiments import (
    add_evidence,
    conclude,
    evolve,
    evolve_image,
    get_experiment,
    launch,
    launch_campaign,
    launch_image,
    tag,
    track_entities,
    upload_image,
    versions,
)
from support.microprojects import signup_with_microproject
from support.search import search as search_topbar
from support.structures import campaign_plan, steps
from support.wafers import list_wafers


def _owner_microproject(client, email="fdl@example.com", name="Lots"):
    return signup_with_microproject(client, email, name)


def test_fdl_numbers_are_spelled_one_way():
    assert normalize_fdl("fdl 1234") == "FDL-1234"
    assert normalize_fdl(" FDL_0042 ") == "FDL-42"
    assert normalize_fdl("1234") == "FDL-1234"
    assert normalize_fdl("abc-12") == "ABC-12"
    assert normalize_fdl("Lot spécial 2024/3") == "Lot spécial 2024/3"
    assert normalize_fdl("   ") is None
    assert clean_fdl_list(["1234", "FDL-1234", "", "fdl 99"]) == ["FDL-1234", "FDL-99"]


def test_fdls_stack_on_a_wafer_and_follow_the_versions(client):
    slug = _owner_microproject(client)
    launched = launch(client, slug, intent="x", entities=[{"sample_id": "W7", "fdl": ["fdl 1201"]}])
    detail = get_experiment(client, slug, launched["id"])
    assert detail["physical_tracking"] == [{"sample_id": "W7", "location": None, "fdl": ["FDL-1201"]}]

    # le wafer repasse en ligne : une deuxième FDL s'empile sur la première
    track_entities(client, slug, launched["id"], [{"sample_id": "W7", "location": "boîte 2", "fdl": ["FDL-1201", "1350"]}])
    evolved = evolve(client, slug, launched["id"], intent="Plus épais", steps=steps(40))
    assert evolved["physical_tracking"] == [
        {"sample_id": "W7", "location": "boîte 2", "fdl": ["FDL-1201", "FDL-1350"]}
    ]
    assert [w["fdl"] for w in list_wafers(client, microproject=slug)] == [["FDL-1201", "FDL-1350"]]

    # un wafer sans FDL garde exactement sa forme d'avant
    plain = launch(client, slug, title="Sans FDL", intent="x", entities=[{"sample_id": "W8"}])
    assert get_experiment(client, slug, plain["id"])["physical_tracking"] == [{"sample_id": "W8", "location": None}]


def test_a_campaign_carries_fdls_per_wafer(client):
    slug = _owner_microproject(client)
    campaign = launch_campaign(
        client,
        slug,
        campaign_plan([10, 30]),
        title="Split",
        intent="Epaisseur",
        entities=[{"sample_id": "W1", "fdl": ["FDL-10"]}, {"sample_id": "W2", "fdl": ["FDL-10", "FDL-11"]}],
    )
    tracking = get_experiment(client, slug, campaign["id"])["physical_tracking"]
    assert [e.get("fdl") for e in tracking] == [["FDL-10"], ["FDL-10", "FDL-11"]]


def test_the_topbar_finds_an_experience_by_its_fdl(client):
    slug = _owner_microproject(client, "owner-fdl@example.com", "Lots A")
    first = launch(client, slug, title="Dopage", intent="x", entities=[{"sample_id": "W7", "fdl": ["FDL-1201", "FDL-1350"]}])
    launch(client, slug, title="Autre", intent="x", entities=[{"sample_id": "W9", "fdl": ["FDL-12010"]}])

    def search(q):
        return search_topbar(client, q, types="fdl")

    hits = search("1201")
    assert [(h["label"], h["detail"]) for h in hits] == [("FDL-1201", "Dopage · W7"), ("FDL-12010", "Autre · W9")]
    assert hits[0]["url"] == f"/microprojets/{slug}/experiences/{first['id']}"
    assert [h["label"] for h in search("fdl 1350")] == ["FDL-1350"]
    assert search("dopage") == [] and search("") == []  # un FDL est un numéro

    # quelqu'un qui n'est pas membre du µprojet ne voit pas ses expériences
    _owner_microproject(client, "stranger-fdl@example.com", "Ailleurs")
    assert search("1201") == []


def test_a_preuve_with_links_and_pasted_images_is_one_version(client):
    slug = _owner_microproject(client)
    launched = launch(client, slug, intent="x", entities=[{"sample_id": "W7"}])
    before = len(versions(client, slug, launched["id"]))
    first, second = upload_image(client, slug, "tem.png"), upload_image(client, slug)

    response = client.post(
        f"/api/microprojets/{slug}/experiences/{launched['id']}/preuves",
        json={
            "description": "Coupes TEM et présentation du run",
            "links": ['"\\\\srv-data\\R&D\\Runs\\W7\\revue.pptx"', "https://aledia.sharepoint.com/sites/rd/W7", "", "https://aledia.sharepoint.com/sites/rd/W7"],
            "images": [{"image_id": first, "caption": "Vue d'ensemble"}, {"image_id": second}],
        },
    )
    assert response.status_code == 201, response.text
    evidence_id = response.json()["evidence_id"]
    detail = get_experiment(client, slug, response.json()["id"])
    assert detail["evidence_links"] == {evidence_id: ["\\\\srv-data\\R&D\\Runs\\W7\\revue.pptx", "https://aledia.sharepoint.com/sites/rd/W7"]}
    evidence = next(e for e in detail["evidence"] if e["id"] == evidence_id)
    assert evidence["source"] == "\\\\srv-data\\R&D\\Runs\\W7\\revue.pptx"  # le premier lien, faute de source
    assert evidence["kind"] == "image"  # des images collées font une preuve image
    images = [a for a in detail["attachments"] if a["evidence_id"] == evidence_id]
    assert [(a["id"], a["caption"]) for a in images] == [(first, "Vue d'ensemble"), (second, None)]
    assert client.get(f"/api/microprojects/{slug}/attachments/{first}/content").status_code == 200
    # tout en une seule version (plus une par image)
    assert len(versions(client, slug, launched["id"])) == before + 1

    # une preuve suivante garde les liens des précédentes
    later = add_evidence(client, slug, launched["id"], source="profilomètre", links=["S:\\Mesures\\W7"])
    links = get_experiment(client, slug, launched["id"])["evidence_links"]
    assert links[evidence_id] and links[later["evidence_id"]] == ["S:\\Mesures\\W7"]


def test_a_preuve_refuses_images_that_were_never_uploaded(client):
    slug = _owner_microproject(client)
    launched = launch(client, slug, intent="x", entities=[{"sample_id": "W7"}])
    url = f"/api/microprojets/{slug}/experiences/{launched['id']}/preuves"
    assert client.post(url, json={"description": "x", "images": [{"image_id": "att_" + "0" * 20}]}).status_code == 422
    assert client.post(url, json={"description": "x", "images": [{"image_id": "../secret"}]}).status_code == 422
    image = upload_image(client, slug)
    assert client.post(url, json={"description": "x", "images": [{"image_id": image}, {"image_id": image}]}).status_code == 422
    assert client.post(url, json={"description": "x", "links": [f"https://exemple.fr/{i}" for i in range(11)]}).status_code == 422


def test_the_context_description_follows_the_experience(client):
    slug = _owner_microproject(client)
    launched = launch(
        client,
        slug,
        title="Pixélisation",
        intent="Montrer que la pixélisation ne change pas la directivité",
        context="  Suite du run W40 : la directivité chutait sur les plaques pixélisées.  ",
        entities=[{"sample_id": "W7"}],
    )
    assert get_experiment(client, slug, launched["id"])["context"] == "Suite du run W40 : la directivité chutait sur les plaques pixélisées."

    # une étiquette, puis une évolution qui ne dit rien du contexte : il reste
    tag(client, slug, launched["id"], ["x"])
    evolved = evolve(client, slug, launched["id"], title="Pixélisation", intent="Idem, plus épais", steps=steps(40))
    assert evolved["context"].startswith("Suite du run W40")

    # une campagne partie de cette version le reprend aussi
    campaign = launch_campaign(
        client,
        slug,
        campaign_plan([10, 30]),
        title="Split",
        intent="Epaisseur",
        entities=[{"sample_id": "W1"}, {"sample_id": "W2"}],
        from_version={"experiment_id": evolved["id"], "version_id": evolved["version_id"]},
    )
    assert campaign["context"].startswith("Suite du run W40")

    # l'effacer explicitement
    cleared = evolve(client, slug, launched["id"], title="Pixélisation", intent="Idem", steps=steps(40), context=" ")
    assert cleared["context"] is None


def test_editing_the_fiche_without_changing_the_structure_keeps_the_conclusion(client):
    slug = _owner_microproject(client)
    launched = launch(client, slug, intent="x", entities=[{"sample_id": "W7"}])
    conclude(client, slug, launched["id"], decision="promote", summary="Directivité identique.")

    # « Éditer la fiche » : un contexte en plus, même structure -> toujours conclue
    edited = evolve(client, slug, launched["id"], intent="x", context="Suite du run W40")
    assert edited["status"] == "concluded" and edited["conclusion"]["summary"] == "Directivité identique."
    assert edited["context"] == "Suite du run W40"

    # la structure change : nouvelle itération, à conclure à nouveau
    changed = evolve(client, slug, launched["id"], intent="x", steps=steps(40))
    assert changed["status"] == "draft"


def test_editing_an_image_fiche_with_the_same_pictures_keeps_version_and_conclusion(client):
    slug = _owner_microproject(client)
    image = {"image_id": upload_image(client, slug), "kind": "schema", "caption": None}
    launched = launch_image(client, slug, [image], intent="x", entities=[{"sample_id": "W7"}])
    conclude(client, slug, launched["id"], summary="OK")
    edited = evolve_image(client, slug, launched["id"], [image], intent="x, mieux dit", context="Contexte ajouté")
    assert edited["status"] == "concluded" and edited["intent"] == "x, mieux dit"
    assert {v["version"] for v in versions(client, slug, launched["id"])} == {"1.0.0"}
