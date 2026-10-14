"""GET /api/wafer-twins : les plaques dont la structure est celle d'une ligne du comparateur, ou n'en
diffère que d'une ou deux variations - les plus proches d'abord, jamais la plaque de départ."""

from __future__ import annotations

from support.accounts import logout
from support.comparator import compare
from support.experiments import from_wafers, launch, launch_campaign, launch_declared, launch_image
from support.microprojects import signup_with_microproject
from support.structures import deposition, etch, upload_structure_image
from support.twins import find_twins, get_twins, lasermarks


def stack(*, oxide_nm: float = 20, etch_nm: float = 10, extra: bool = False) -> list[dict]:
    layers = [deposition("Oxyde", "SiO2", thickness_nm=oxide_nm), etch("Gravure", depth_nm=etch_nm)]
    return [*layers, deposition("Contact", "ITO", thickness_nm=50)] if extra else layers


def study(client, slug: str, title: str, wafers: list[str], **variations) -> dict:
    return launch(client, slug, title=title, intent="x", steps=stack(**variations), entities=[{"sample_id": w} for w in wafers])


def test_exact_twins_are_the_wafers_of_the_same_structure_whatever_their_study(client):
    slug = signup_with_microproject(client, "twins-exact@example.com", "Epi")
    study(client, slug, "Référence", ["W1", "W2"])  # deux réplicats d'une même étude
    study(client, slug, "Refaite", ["W3"])  # une autre étude, la même structure
    study(client, slug, "Plus épaisse", ["W4"], oxide_nm=30)

    found = find_twins(client, "wafer:W1")
    assert sorted(lasermarks(found)) == ["W2", "W3"]
    assert found["max_variations"] == 0 and found["truncated"] is False
    assert found["scanned"] == 3  # W2, W3, W4 : la plaque de départ n'est pas cherchée
    assert found["base"]["label"] == "W1" and found["base"]["item"] == "wafer:W1"
    assert all(twin["variations"] == 0 and twin["differences"] == [] and twin["item"] == f"wafer:{twin['lasermark']}" for twin in found["twins"])
    # l'étude de chaque plaque est dite, pour la reconnaître
    assert {twin["lasermark"]: twin["study"] for twin in found["twins"]} == {"W2": "Référence", "W3": "Refaite"}
    assert {twin["microproject"] for twin in found["twins"]} == {"Epi"}


def test_one_or_two_variations_bring_in_the_nearest_wafers_first(client):
    slug = signup_with_microproject(client, "twins-near@example.com", "Epi")
    study(client, slug, "Base", ["W1"])
    study(client, slug, "Même", ["W2"])
    study(client, slug, "Oxyde épais", ["W3"], oxide_nm=35)
    study(client, slug, "Deux écarts", ["W4"], oxide_nm=35, etch_nm=12)
    study(client, slug, "Trois écarts", ["W5"], oxide_nm=35, etch_nm=12, extra=True)

    assert lasermarks(find_twins(client, "wafer:W1", 0)) == ["W2"]

    one = find_twins(client, "wafer:W1", 1)
    assert lasermarks(one) == ["W2", "W3"]
    assert [twin["variations"] for twin in one["twins"]] == [0, 1]
    assert one["twins"][1]["differences"] == [{"kind": "changed", "step": "Oxyde", "parameter": "Épaisseur", "from": "20 nm", "to": "35 nm"}]

    two = find_twins(client, "wafer:W1", 2)
    assert lasermarks(two) == ["W2", "W3", "W4"]
    assert [twin["variations"] for twin in two["twins"]] == [0, 1, 2]
    assert {(d["step"], d["parameter"]) for d in two["twins"][2]["differences"]} == {("Oxyde", "Épaisseur"), ("Gravure", "Profondeur")}

    # la couche en plus, avec tous ses paramètres, ne fait qu'une variation : W5 = deux écarts + une couche
    three = find_twins(client, "wafer:W1", 3)
    assert lasermarks(three) == ["W2", "W3", "W4", "W5"]
    assert three["twins"][-1]["variations"] == 3
    layers = [d for d in three["twins"][-1]["differences"] if d["kind"] == "added_layer"]
    assert layers == [{"kind": "added_layer", "step": "Contact", "parameter": None, "from": None, "to": None}]


def test_the_variations_are_the_ones_the_comparator_shows(client):
    slug = signup_with_microproject(client, "twins-same@example.com", "Epi")
    study(client, slug, "Base", ["W1"])
    study(client, slug, "Autre", ["W2"], oxide_nm=35, etch_nm=12, extra=True)

    twin = find_twins(client, "wafer:W1", 5)["twins"][0]
    summary = compare(client, "wafer:W1", "wafer:W2")["rows"][1]["summary"]
    assert twin["variations"] == sum(summary.values()) == len(twin["differences"])


def test_a_study_or_a_campaign_variant_is_a_starting_point_too(client):
    slug = signup_with_microproject(client, "twins-start@example.com", "Epi")
    first = study(client, slug, "Étude", ["W1"])
    study(client, slug, "Jumelle", ["W2"])
    # la campagne : trois épaisseurs d'oxyde (10, 20, 30 nm) sur W11, W12, W13
    launch_campaign(client, slug, entities=[{"sample_id": "W11"}, {"sample_id": "W12"}, {"sample_id": "W13"}])

    # une étude de départ garde ses propres plaques parmi les jumelles
    assert sorted(lasermarks(find_twins(client, f"study:{slug}/{first['id']}"))) == ["W1", "W2"]
    # W11 (10 nm) : W12 et W13 n'en diffèrent que par l'épaisseur de l'oxyde, W1 et W2 par l'oxyde seulement aussi
    assert find_twins(client, "wafer:W11", 0)["twins"] == []
    near = find_twins(client, "wafer:W11", 1)
    assert {"W12", "W13"} <= set(lasermarks(near)) and {twin["variations"] for twin in near["twins"]} == {1}


def test_a_wafer_is_found_by_the_structure_of_its_latest_study(client):
    slug = signup_with_microproject(client, "twins-latest@example.com", "Epi")
    study(client, slug, "Base", ["W1"])
    old = study(client, slug, "Ancienne", ["W2"], oxide_nm=99)
    assert find_twins(client, "wafer:W1")["twins"] == []

    # W2 est reprise par une étude plus récente, à la structure de W1
    from_wafers(client, slug, slug, old["id"], ["W2"], title="Reprise", steps=stack())
    found = find_twins(client, "wafer:W1")
    assert lasermarks(found) == ["W2"] and found["twins"][0]["study"] == "Reprise"


def test_structures_without_the_same_columns_are_skipped_not_twins(client):
    slug = signup_with_microproject(client, "twins-skip@example.com", "Epi")
    study(client, slug, "Base", ["W1"])
    study(client, slug, "Jumelle", ["W2"])
    image = {"image_id": upload_structure_image(client, slug), "kind": "coupe", "caption": None}
    launch_image(client, slug, [image], title="Coupe TEM", intent="x", entities=[{"sample_id": "W3"}])
    launch_declared(client, slug, entities=[{"sample_id": "W4"}, {"sample_id": "W5"}])

    found = find_twins(client, "wafer:W1", 5)
    assert lasermarks(found) == ["W2"]
    assert found["scanned"] == 4 and found["skipped"] == 3  # l'image et les deux lignes du split


def test_a_base_with_nothing_to_compare_is_refused(client):
    slug = signup_with_microproject(client, "twins-refused@example.com", "Epi")
    image = {"image_id": upload_structure_image(client, slug), "kind": "coupe", "caption": None}
    pictured = launch_image(client, slug, [image], title="Coupe TEM", intent="x")

    refused = get_twins(client, f"study:{slug}/{pictured['id']}")
    assert (refused.status_code, refused.json()["code"]) == (422, "nothing_to_compare")
    unknown = get_twins(client, "wafer:W-99")
    assert (unknown.status_code, unknown.json()["code"]) == (422, "nothing_to_compare")
    malformed = get_twins(client, "plaque-12")
    assert (malformed.status_code, malformed.json()["code"]) == (422, "invalid_comparison_item")
    assert get_twins(client, "wafer:W1", 6).status_code == 422
    assert get_twins(client, "wafer:W1", -1).status_code == 422


def test_wafers_of_a_microproject_you_are_not_in_are_not_searched(client):
    other = signup_with_microproject(client, "twins-owner@example.com", "Secret")
    study(client, other, "Cachée", ["W-SECRET"])
    logout(client)
    mine = signup_with_microproject(client, "twins-reader@example.com", "Mien")
    study(client, mine, "Base", ["W1"])

    found = find_twins(client, "wafer:W1")
    assert found["twins"] == [] and found["scanned"] == 0


def test_anonymous_callers_get_a_401(client):
    assert get_twins(client, "wafer:W1").status_code == 401
