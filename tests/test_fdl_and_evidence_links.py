"""FDL (feuilles de lancement JIRA, spectre.core.fdl) stacked on each wafer - normalized, carried
along the versions, searchable from the topbar - and preuves carrying links (a folder, a PowerPoint
deck) and pasted images, recorded in one version.
"""

from __future__ import annotations

from spectre.core.fdl import clean_fdl_list, normalize_fdl


def _substrate():
    return {"material": "Si", "domain_width": {"value": 200, "unit": "nm"}, "thickness": {"value": 50, "unit": "nm"}}


def _steps(thickness=20):
    return [{"kind": "deposition", "name": "Oxyde", "material": "SiO2", "recipe": "CVD Conformal", "thickness": {"value": thickness, "unit": "nm"}}]


def _register_and_microproject(client, email="fdl@example.com", name="Lots"):
    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={"email": email, "password": "supersecret", "name": "T"})
    return client.post("/api/microprojets", json={"name": name}).json()["slug"]


def _launch(client, slug, entities, title="Essai"):
    return client.post(
        f"/api/microprojets/{slug}/experiences",
        json={"substrate": _substrate(), "steps": _steps(), "title": title, "intent": "x", "entities": entities},
    ).json()


def _detail(client, slug, experience_id):
    return client.get(f"/api/microprojets/{slug}/experiences/{experience_id}").json()


def _png_bytes():
    return bytes.fromhex(
        "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753"
        "de000000097048597300000b1300000b1301009a9c1800000010494441545805"
        "0763f8ffff3f0005fe02fea739667e0000000049454e44ae426082"
    )


def _upload(client, slug, name="mesure.png"):
    response = client.post(f"/api/microprojets/{slug}/images", files={"file": (name, _png_bytes(), "image/png")})
    assert response.status_code == 201, response.text
    return response.json()["image_id"]


def test_fdl_numbers_are_spelled_one_way():
    assert normalize_fdl("fdl 1234") == "FDL-1234"
    assert normalize_fdl(" FDL_0042 ") == "FDL-42"
    assert normalize_fdl("1234") == "FDL-1234"
    assert normalize_fdl("abc-12") == "ABC-12"
    assert normalize_fdl("Lot spécial 2024/3") == "Lot spécial 2024/3"
    assert normalize_fdl("   ") is None
    assert clean_fdl_list(["1234", "FDL-1234", "", "fdl 99"]) == ["FDL-1234", "FDL-99"]


def test_fdls_stack_on_a_wafer_and_follow_the_versions(client):
    slug = _register_and_microproject(client)
    launched = _launch(client, slug, [{"sample_id": "W7", "fdl": ["fdl 1201"]}])
    detail = _detail(client, slug, launched["id"])
    assert detail["physical_tracking"] == [{"sample_id": "W7", "location": None, "fdl": ["FDL-1201"]}]

    # le wafer repasse en ligne : une deuxième FDL s'empile sur la première
    stacked = client.post(
        f"/api/microprojets/{slug}/experiences/{launched['id']}/entites",
        json={"entities": [{"sample_id": "W7", "location": "boîte 2", "fdl": ["FDL-1201", "1350"]}]},
    ).json()
    evolved = client.post(
        f"/api/microprojets/{slug}/experiences/{stacked['id']}/evoluer",
        json={"substrate": _substrate(), "steps": _steps(40), "title": "Essai", "intent": "Plus épais", "objectives": []},
    ).json()
    assert _detail(client, slug, evolved["id"])["physical_tracking"] == [
        {"sample_id": "W7", "location": "boîte 2", "fdl": ["FDL-1201", "FDL-1350"]}
    ]
    history = client.get(f"/api/microprojets/{slug}/entites/historique").json()
    assert history["fdls"] == ["FDL-1201", "FDL-1350"]

    # un wafer sans FDL garde exactement sa forme d'avant
    plain = _launch(client, slug, [{"sample_id": "W8"}], title="Sans FDL")
    assert _detail(client, slug, plain["id"])["physical_tracking"] == [{"sample_id": "W8", "location": None}]


def test_a_campaign_carries_fdls_per_wafer(client):
    slug = _register_and_microproject(client)
    campaign = client.post(
        f"/api/microprojets/{slug}/experiences/campagne",
        json={
            "substrate": _substrate(),
            "steps": _steps(),
            "plan": {"factors": [{"step_index": 0, "field": "thickness", "values": [10, 30]}]},
            "title": "Split",
            "intent": "Epaisseur",
            "entities": [{"sample_id": "W1", "fdl": ["FDL-10"]}, {"sample_id": "W2", "fdl": ["FDL-10", "FDL-11"]}],
        },
    ).json()
    tracking = _detail(client, slug, campaign["id"])["physical_tracking"]
    assert [e.get("fdl") for e in tracking] == [["FDL-10"], ["FDL-10", "FDL-11"]]


def test_the_topbar_finds_an_experience_by_its_fdl(client):
    slug = _register_and_microproject(client, "owner-fdl@example.com", "Lots A")
    first = _launch(client, slug, [{"sample_id": "W7", "fdl": ["FDL-1201", "FDL-1350"]}], title="Dopage")
    _launch(client, slug, [{"sample_id": "W9", "fdl": ["FDL-12010"]}], title="Autre")

    def search(q):
        return client.get(f"/api/microprojets/recherche-fdl?q={q}").json()

    hits = search("1201")
    assert [(h["fdl"], h["experience"]["title"]) for h in hits] == [("FDL-1201", "Dopage"), ("FDL-12010", "Autre")]
    assert hits[0]["sample_id"] == "W7" and hits[0]["microproject"]["slug"] == slug and hits[0]["experience"]["id"] == first["id"]
    assert [h["fdl"] for h in search("fdl 1350")] == ["FDL-1350"]
    assert search("dopage") == [] and search("") == []  # un FDL est un numéro

    # quelqu'un qui n'est pas membre du µprojet ne voit pas ses expériences
    _register_and_microproject(client, "stranger-fdl@example.com", "Ailleurs")
    assert search("1201") == []


def test_a_preuve_with_links_and_pasted_images_is_one_version(client):
    slug = _register_and_microproject(client)
    launched = _launch(client, slug, [{"sample_id": "W7"}])
    before = len(client.get(f"/api/microprojets/{slug}/experiences/{launched['id']}/timeline").json()["items"])
    first, second = _upload(client, slug, "tem.png"), _upload(client, slug)

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
    detail = _detail(client, slug, response.json()["id"])
    assert detail["evidence_links"] == {evidence_id: ["\\\\srv-data\\R&D\\Runs\\W7\\revue.pptx", "https://aledia.sharepoint.com/sites/rd/W7"]}
    evidence = next(e for e in detail["evidence"] if e["id"] == evidence_id)
    assert evidence["source"] == "\\\\srv-data\\R&D\\Runs\\W7\\revue.pptx"  # le premier lien, faute de source
    images = [a for a in detail["attachments"] if a["evidence_id"] == evidence_id]
    assert [(a["id"], a["caption"]) for a in images] == [(first, "Vue d'ensemble"), (second, None)]
    assert client.get(f"/api/microprojets/{slug}/pieces-jointes/{first}").status_code == 200
    # tout en une seule version (plus une par image)
    items = client.get(f"/api/microprojets/{slug}/experiences/{response.json()['id']}/timeline").json()["items"]
    assert len(items) == before + 1

    # une preuve suivante garde les liens des précédentes
    later = client.post(
        f"/api/microprojets/{slug}/experiences/{response.json()['id']}/preuves",
        json={"description": "Mesure", "source": "profilomètre", "links": ["S:\\Mesures\\W7"]},
    ).json()
    links = _detail(client, slug, later["id"])["evidence_links"]
    assert links[evidence_id] and links[later["evidence_id"]] == ["S:\\Mesures\\W7"]


def test_a_preuve_refuses_images_that_were_never_uploaded(client):
    slug = _register_and_microproject(client)
    launched = _launch(client, slug, [{"sample_id": "W7"}])
    url = f"/api/microprojets/{slug}/experiences/{launched['id']}/preuves"
    assert client.post(url, json={"description": "x", "images": [{"image_id": "att_" + "0" * 20}]}).status_code == 422
    assert client.post(url, json={"description": "x", "images": [{"image_id": "../secret"}]}).status_code == 422
    image = _upload(client, slug)
    assert client.post(url, json={"description": "x", "images": [{"image_id": image}, {"image_id": image}]}).status_code == 422
    assert client.post(url, json={"description": "x", "links": [f"https://exemple.fr/{i}" for i in range(11)]}).status_code == 422


def test_the_context_description_follows_the_experience(client):
    slug = _register_and_microproject(client)
    launched = client.post(
        f"/api/microprojets/{slug}/experiences",
        json={
            "substrate": _substrate(),
            "steps": _steps(),
            "title": "Pixélisation",
            "intent": "Montrer que la pixélisation ne change pas la directivité",
            "context": "  Suite du run W40 : la directivité chutait sur les plaques pixélisées.  ",
            "entities": [{"sample_id": "W7"}],
        },
    ).json()
    assert _detail(client, slug, launched["id"])["context"] == "Suite du run W40 : la directivité chutait sur les plaques pixélisées."

    # une étiquette, puis une évolution qui ne dit rien du contexte : il reste
    tagged = client.post(f"/api/microprojets/{slug}/experiences/{launched['id']}/etiquettes", json={"tags": ["x"]}).json()
    evolved = client.post(
        f"/api/microprojets/{slug}/experiences/{tagged['id']}/evoluer",
        json={"substrate": _substrate(), "steps": _steps(40), "title": "Pixélisation", "intent": "Idem, plus épais", "objectives": []},
    ).json()
    assert _detail(client, slug, evolved["id"])["context"].startswith("Suite du run W40")

    # une campagne partie de cette version le reprend aussi
    campaign = client.post(
        f"/api/microprojets/{slug}/experiences/campagne",
        json={
            "substrate": _substrate(),
            "steps": _steps(),
            "plan": {"factors": [{"step_index": 0, "field": "thickness", "values": [10, 30]}]},
            "title": "Split",
            "intent": "Epaisseur",
            "entities": [{"sample_id": "W1"}, {"sample_id": "W2"}],
            "from_ref": evolved["id"],
        },
    ).json()
    assert _detail(client, slug, campaign["id"])["context"].startswith("Suite du run W40")

    # l'effacer explicitement
    cleared = client.post(
        f"/api/microprojets/{slug}/experiences/{evolved['id']}/evoluer",
        json={"substrate": _substrate(), "steps": _steps(40), "title": "Pixélisation", "intent": "Idem", "objectives": [], "context": " "},
    ).json()
    assert _detail(client, slug, cleared["id"])["context"] is None


def test_editing_the_fiche_without_changing_the_structure_keeps_the_conclusion(client):
    slug = _register_and_microproject(client)
    launched = _launch(client, slug, [{"sample_id": "W7"}])
    concluded = client.post(
        f"/api/microprojets/{slug}/experiences/{launched['id']}/conclure",
        json={"status": "concluded", "decision": "promote", "summary": "Directivité identique."},
    ).json()

    # « Éditer la fiche » : un contexte en plus, même structure -> toujours conclue
    edited = client.post(
        f"/api/microprojets/{slug}/experiences/{concluded['id']}/evoluer",
        json={"substrate": _substrate(), "steps": _steps(), "title": "Essai", "intent": "x", "objectives": [], "context": "Suite du run W40"},
    ).json()
    detail = _detail(client, slug, edited["id"])
    assert detail["status"] == "concluded" and detail["conclusion"]["summary"] == "Directivité identique."
    assert detail["context"] == "Suite du run W40"

    # la structure change : nouvelle itération, à conclure à nouveau
    changed = client.post(
        f"/api/microprojets/{slug}/experiences/{edited['id']}/evoluer",
        json={"substrate": _substrate(), "steps": _steps(40), "title": "Essai", "intent": "x", "objectives": []},
    ).json()
    assert _detail(client, slug, changed["id"])["status"] == "draft"


def test_editing_an_image_fiche_with_the_same_pictures_keeps_version_and_conclusion(client):
    slug = _register_and_microproject(client)
    image = {"image_id": _upload(client, slug), "kind": "schema", "caption": None}
    launched = client.post(
        f"/api/microprojets/{slug}/experiences/image",
        json={"images": [image], "title": "Coupe", "intent": "x", "entities": [{"sample_id": "W7"}]},
    ).json()
    concluded = client.post(
        f"/api/microprojets/{slug}/experiences/{launched['id']}/conclure", json={"status": "concluded", "summary": "OK"}
    ).json()
    edited = client.post(
        f"/api/microprojets/{slug}/experiences/{concluded['id']}/evoluer-image",
        json={"images": [image], "title": "Coupe", "intent": "x, mieux dit", "context": "Contexte ajouté"},
    ).json()
    detail = _detail(client, slug, edited["id"])
    assert detail["status"] == "concluded" and detail["intent"] == "x, mieux dit"
    versions = client.get(f"/api/microprojets/{slug}/experiences/{edited['id']}/timeline").json()["versions"]
    assert [v["version"] for v in versions] == ["1.0.0"]
