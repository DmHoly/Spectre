"""Promouvoir une brique comme brique de référence (plugin promotion, ``/api/promotions/bricks``) :
l'aperçu et ses règles, la brique de µprojet qui passe en partagée avec sa référence, la liste des
briques de référence, le retrait, et la note exigée d'une nouvelle version d'une brique de
référence."""

from __future__ import annotations

from support.http import assert_created, assert_ok
from support.microprojects import join_as, signup_with_microproject
from support.process_library import create_item, get_item, list_items, tech_brick, update_item
from support.structures import deposition


def _levels(preview: dict) -> dict[str, str]:
    return {r["rule"]: r["level"] for r in preview["rules"]}


def _preview(client, brick_id: str, note: str = "") -> dict:
    return assert_ok(client.post("/api/promotions/bricks/preview", json={"brick_id": brick_id, "note": note}))


def _promote(client, brick_id: str, note: str = ""):
    return client.post("/api/promotions/bricks", json={"brick_id": brick_id, "note": note})


def test_a_microproject_brick_promoted_becomes_a_shared_reference_brick(client):
    slug = signup_with_microproject(client, "brick-promo@example.com", "Salle blanche")
    brick = create_item(client, "tech-bricks", tech_brick("Épi bleue"), microproject=slug)

    preview = _preview(client, brick["id"])
    levels = _levels(preview)
    assert preview["can_promote"] and levels == {"editor": "ok", "steps": "ok", "not_already": "ok", "name": "ok", "justified": "warn"}
    assert preview["brick"]["id"] == brick["id"]

    response = _promote(client, brick["id"], note="La brique que tout le monde reprend")
    promoted = assert_created(response)
    assert response.headers["Location"] == f"/api/tech-bricks/{brick['id']}"
    assert promoted["scope"] == "shared" and promoted["microproject"] is None
    assert promoted["reference"]["note"] == "La brique que tout le monde reprend" and promoted["reference"]["promoted_by"]
    assert promoted["version"] == "1.0"

    # même id : la brique a déménagé, elle n'est plus dans le µprojet, elle est parmi les références
    assert [b["id"] for b in list_items(client, "tech-bricks", microproject=slug, scope="microproject")] == []
    assert [b["id"] for b in list_items(client, "tech-bricks", reference="true")] == [brick["id"]]
    assert list_items(client, "tech-bricks", reference="false") == [b for b in list_items(client, "tech-bricks") if not b.get("reference")]

    # déjà une référence : la règle bloque
    preview = _preview(client, brick["id"])
    assert not preview["can_promote"] and _levels(preview)["not_already"] == "block"
    assert _promote(client, brick["id"]).status_code == 409


def test_the_rules_block_a_builtin_brick_a_taken_name_and_someone_else(client):
    slug = signup_with_microproject(client, "brick-rules@example.com", "Salle blanche")
    create_item(client, "tech-bricks", tech_brick("Masque"), scope="shared")
    mine = create_item(client, "tech-bricks", tech_brick("masque"), microproject=slug)
    preview = _preview(client, mine["id"])
    assert _levels(preview)["name"] == "block" and not preview["can_promote"]
    assert _promote(client, mine["id"]).status_code == 409

    empty = create_item(client, "tech-bricks", {**tech_brick("Vide"), "steps": []}, microproject=slug)
    assert _levels(_preview(client, empty["id"]))["steps"] == "block"
    assert _promote(client, empty["id"]).status_code == 422

    # un lecteur du µprojet ne promeut pas
    join_as(client, slug, "brick-reader@example.com", owner="brick-rules@example.com", role="viewer")
    ok_brick = mine["id"]
    assert _levels(_preview(client, ok_brick))["editor"] == "block"
    assert _promote(client, ok_brick).status_code == 403


def test_a_reference_brick_needs_a_note_for_a_new_version_and_can_be_demoted(client):
    slug = signup_with_microproject(client, "brick-note@example.com", "Salle blanche")
    brick = create_item(client, "tech-bricks", tech_brick("Épi bleue"), microproject=slug)
    assert_created(_promote(client, brick["id"], note="Référence"))

    thicker = [deposition("PGaN", "GaN", thickness_nm=80)]
    refused = client.patch(f"/api/tech-bricks/{brick['id']}", json={"steps": thicker})
    assert refused.status_code == 422 and refused.json()["code"] == "brick_note_required"
    # une retouche (un nom d'étape) passe sans note ; un vrai changement, avec
    renamed = [deposition("PGaN bis", "GaN", thickness_nm=50)]
    assert update_item(client, "tech-bricks", brick["id"], steps=renamed)["version"] == "1.0"
    updated = update_item(client, "tech-bricks", brick["id"], steps=thicker, note="Plus épais")
    assert updated["version"] == "1.1" and updated["versions"][-1]["note"] == "Plus épais"

    demoted = assert_ok(client.delete(f"/api/tech-bricks/{brick['id']}/reference"))
    assert "reference" not in demoted and demoted["scope"] == "shared" and demoted["version"] == "1.1"
    assert list_items(client, "tech-bricks", reference="true") == []
    assert get_item(client, "tech-bricks", brick["id"])["versions"][-1]["number"] == "1.1"
