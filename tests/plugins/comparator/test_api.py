"""GET /api/comparisons et /api/comparison-candidates : comparer des versions d'étude, les variantes
d'une campagne, des plaques et des versions de référence, chacune désignée par son jeton - une
ligne qu'on ne peut pas lire garde sa place avec son erreur."""

from __future__ import annotations

from support.accounts import logout
from support.comparator import candidates, cell, compare, get_comparison, group
from support.experiments import evolve, launch, launch_campaign, launch_declared, launch_image
from support.microprojects import signup_with_microproject
from support.references import create_reference, publish
from support.structures import deposition, identified, upload_structure_image

STACK = identified([deposition("n-GaN", "GaN", thickness_nm=400), deposition("p-GaN", "GaN", thickness_nm=150)])


def test_two_versions_of_a_study(client):
    slug = signup_with_microproject(client, "cmp-versions@example.com", "Epi")
    study = launch(client, slug, title="LED", intent="x", steps=STACK)
    first = study["version_id"]
    second = evolve(client, slug, study["id"], title="LED", intent="y", steps=[STACK[0], {**STACK[1], "thickness": {"value": 200, "unit": "nm"}}])

    table = compare(client, f"study:{slug}/{study['id']}@{first}", f"study:{slug}/{study['id']}")
    base, other = table["rows"]
    assert (base["label"], base["version"], base["baseline"]) == ("LED", "v1.0", True)
    assert (other["version"], other["item"]) == ("v1.1", f"study:{slug}/{study['id']}@{second['version_id']}")
    assert base["url"] == f"/microprojets/{slug}/experiences/{study['id']}?version={first}"
    assert other["url"] == f"/microprojets/{slug}/experiences/{study['id']}"
    assert base["wafers"] == ["W1"] and base["context"] == "Epi"
    assert cell(table, 1, "p-GaN", "Épaisseur") == {"text": "200 nm", "status": "changed", "title": "base : 150 nm"}
    assert table["summary"]["changed"] == 1


def test_a_renamed_step_is_a_retouche_note(client):
    slug = signup_with_microproject(client, "cmp-rename@example.com", "Epi")
    study = launch(client, slug, title="LED", intent="x", steps=STACK)
    evolve(client, slug, study["id"], title="LED", intent="y", steps=[{**STACK[0], "name": "n-GaN dopé"}, STACK[1]])
    table = compare(client, f"study:{slug}/{study['id']}@{study['version_id']}", f"study:{slug}/{study['id']}")
    assert table["summary"]["changed"] == 0
    assert table["rows"][1]["notes"] == ["étape « n-GaN » renommée « n-GaN dopé »"]


def test_a_campaign_gives_one_row_per_variant_reference_first(client):
    slug = signup_with_microproject(client, "cmp-campaign@example.com", "Epi")
    campaign = launch_campaign(client, slug, entities=[{"sample_id": "W1"}, {"sample_id": "W2"}, {"sample_id": "W3"}], reference_place=1)

    table = compare(client, f"study:{slug}/{campaign['id']}")
    rows = table["rows"]
    assert [r["label"] for r in rows] == ["W2", "W1", "W3"]  # la plaque de référence d'abord
    assert [r["badge"] for r in rows] == ["RÉF", None, None]
    assert [r["item"] for r in rows] == [f"study:{slug}/{campaign['id']}@{campaign['version_id']}~{i}" for i in (1, 0, 2)]
    assert [cell(table, i, "Oxyde", "Épaisseur")["text"] for i in range(3)] == ["20 nm", "10 nm", "30 nm"]
    assert [cell(table, i, "Oxyde", "Épaisseur")["status"] for i in range(3)] == ["same", "changed", "changed"]

    # une variante désignée seule
    one = compare(client, f"study:{slug}/{campaign['id']}@{campaign['version_id']}~2")
    assert [r["label"] for r in one["rows"]] == ["W3"]


def test_a_wafer_shows_the_structure_of_its_latest_study(client):
    slug = signup_with_microproject(client, "cmp-wafer@example.com", "Epi")
    launch(client, slug, title="Première", intent="x", steps=STACK, entities=[{"sample_id": "W-12"}])
    launch_campaign(client, slug, title="Balayage", entities=[{"sample_id": "W-20"}, {"sample_id": "W-21"}])

    table = compare(client, "wafer:w12", "wafer:W-21", "wafer:W-99")
    first, second, unknown = table["rows"]
    assert (first["item"], first["label"], first["source"]) == ("wafer:W-12", "W-12", "wafer")
    assert first["sublabel"] == "Première"
    assert (second["label"], second["version"]) == ("W-21", "v1.0")
    assert "Balayage" in second["sublabel"]
    assert unknown["cells"] is None and "W-99" in unknown["error"]


def test_a_reference_version(client):
    slug = signup_with_microproject(client, "cmp-ref@example.com", "Epi")
    study = launch(client, slug, title="LED", intent="x", steps=STACK)
    create_reference(client, "LED")
    publish(client, "led", slug, study["id"])
    evolve(client, slug, study["id"], title="LED", intent="y", steps=[*STACK, deposition("Contact", "ITO", thickness_nm=100)])
    publish(client, "led", slug, study["id"])

    table = compare(client, "reference:led@1.0", "reference:led", f"study:{slug}/{study['id']}")
    assert [(r["label"], r["version"]) for r in table["rows"]] == [("LED", "1.0"), ("LED", "2.0"), ("LED", "v2.0")]
    assert table["rows"][1]["url"] == "/references/led?version=2.0"
    contact = group(table, "Contact")
    assert contact["status"] == "added_layer"  # la couche en plus de 2.0, appariée par id avec l'étude
    assert cell(table, 2, "Contact", "Épaisseur")["status"] == "added_layer"
    assert table["summary"]["added_layers"] == 1


def test_images_and_declared_splits(client):
    slug = signup_with_microproject(client, "cmp-kinds@example.com", "Epi")
    image = {"image_id": upload_structure_image(client, slug), "kind": "coupe", "caption": None}
    pictured = launch_image(client, slug, [image], title="Coupe TEM", intent="x")
    declared = launch_declared(client, slug)

    table = compare(client, f"study:{slug}/{declared['id']}", f"study:{slug}/{pictured['id']}")
    assert [r["label"] for r in table["rows"]] == ["réf", "Recuit = long", "Coupe TEM"]
    assert cell(table, 1, "Split déclaré", "Recuit") == {"text": "long", "status": "changed", "title": "base : standard"}
    assert table["rows"][2]["cells"] is None and "images" in table["rows"][2]["note"]


def test_a_row_you_cannot_read_keeps_its_place(client):
    other = signup_with_microproject(client, "cmp-owner@example.com", "Secret")
    hidden = launch(client, other, title="Cachée", intent="x", entities=[{"sample_id": "W-SECRET"}])
    logout(client)
    mine = signup_with_microproject(client, "cmp-reader@example.com", "Mien")
    study = launch(client, mine, title="Visible", intent="x")

    table = compare(client, f"study:{mine}/{study['id']}", f"study:{other}/{hidden['id']}", f"study:{mine}/inconnue", "reference:absente")
    readable, forbidden, missing, no_reference = table["rows"]
    assert readable["cells"] is not None
    assert forbidden["cells"] is None and forbidden["error"] == "Vous n'avez pas accès à ce µprojet."
    assert missing["error"] and no_reference["error"]
    # une plaque suivie seulement ailleurs : on sait qu'elle existe, pas sa structure
    assert "pas membre" in compare(client, "wafer:W-SECRET")["rows"][0]["error"]


def test_malformed_items_are_refused(client):
    signup_with_microproject(client, "cmp-bad@example.com", "Epi")
    for items in (("nimporte:quoi",), ("study:sans-piste",), ("wafer:",)):
        response = get_comparison(client, *items)
        assert response.status_code == 422, items
        assert response.json()["code"] == "invalid_comparison_item"
    assert get_comparison(client).json()["code"] == "no_comparison_items"


def test_candidates_cover_wafers_studies_and_references(client):
    slug = signup_with_microproject(client, "cmp-search@example.com", "Epi")
    study = launch(client, slug, title="Croissance GaN", intent="x", steps=STACK, entities=[{"sample_id": "GAN-7"}])
    create_reference(client, "GaN standard")
    publish(client, "gan-standard", slug, study["id"])

    found = candidates(client, "gan")
    assert {(c["source"], c["item"]) for c in found} >= {
        ("wafer", "wafer:GAN-7"),
        ("study", f"study:{slug}/{study['id']}"),
        ("reference", "reference:gan-standard@1.0"),
    }
    assert [c["source"] for c in found] == sorted((c["source"] for c in found), key=["wafer", "study", "reference"].index)
    assert candidates(client, "  ") == []


def test_variants_share_their_step_ids(client):
    slug = signup_with_microproject(client, "cmp-ids@example.com", "Epi")
    campaign = launch_campaign(client, slug, entities=[{"sample_id": "W1"}, {"sample_id": "W2"}, {"sample_id": "W3"}])
    base = f"study:{slug}/{campaign['id']}@{campaign['version_id']}"
    table = compare(client, f"{base}~0", f"{base}~2")
    # les variantes ont les mêmes étapes (mêmes ids) : une seule colonne d'étape, seule l'épaisseur change
    assert [g["label"] for g in table["groups"]] == ["Substrat", "Oxyde"]
    assert cell(table, 1, "Oxyde", "Épaisseur") == {"text": "30 nm", "status": "changed", "title": "base : 10 nm"}
    assert table["summary"] == {"changed": 1, "added_params": 0, "added_layers": 0, "moved_layers": 0, "absent_layers": 0}
