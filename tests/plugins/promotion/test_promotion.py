"""La promotion d'une structure comme référence (plugin promotion) : l'aperçu et ses règles, la
nouvelle référence créée avec sa première version, une variante de split, le journal, et une règle
ajoutée par un autre plugin sans que rien d'autre ne change."""

from __future__ import annotations

from support.experiments import conclude, launch, launch_campaign, launch_declared
from support.http import assert_created, assert_ok
from support.microprojects import join_as, signup_with_microproject
from support.references import create_reference, get_reference, origin, post_promotion, preview_promotion, publish
from support.structures import steps

from spectre.plugins.promotion import rules


def _levels(preview: dict) -> dict[str, str]:
    return {r["rule"]: r["level"] for r in preview["rules"]}


def _study(client, slug, thickness=20, **fields):
    return launch(client, slug, title="Epitaxie", intent="Depart", steps=steps(thickness), **fields)


def test_a_new_reference_is_created_with_its_first_version_in_one_go(client):
    slug = signup_with_microproject(client, "promo-new@example.com", "Epi")
    study = _study(client, slug)

    preview = preview_promotion(client, slug, study["id"], new_reference={"name": "Epi standard"}, note="Meilleur PL")
    assert preview["number"] == "1.0" and preview["level"] == "initial"
    assert preview["can_promote"] and preview["source"]["structure_svg"]
    levels = _levels(preview)
    assert levels["target"] == "ok" and levels["justified"] == "ok"
    assert levels["concluded"] == "warn"  # pas conclue : on peut promouvoir, en le sachant
    assert "variant" not in levels and "changes" not in levels  # sans objet

    version = assert_created(post_promotion(client, slug, study["id"], new_reference={"name": "Epi standard", "description": "La base"}, note="Meilleur PL"))
    assert (version["reference"]["name"], version["number"], version["note"]) == ("Epi standard", "1.0", "Meilleur PL")
    assert get_reference(client, "epi-standard")["description"] == "La base"


def test_without_a_target_the_reference_the_study_started_from_is_proposed(client):
    slug = signup_with_microproject(client, "promo-suggest@example.com", "Epi")
    base = _study(client, slug)
    create_reference(client, "Base")
    publish(client, "base", slug, base["id"])
    child = _study(client, slug, thickness=35, reference_origin=origin("base", "1.0"))

    preview = preview_promotion(client, slug, child["id"])
    assert preview["suggestion"]["reference"] == "base" and preview["suggestion"]["name"] == "Base"
    assert preview["target"]["reference"]["slug"] == "base"
    assert (preview["base"], preview["number"], preview["level_text"]) == ("1.0", "1.1", "changement mineur")

    # rien de choisi, rien à proposer : la règle « Référence visée » bloque
    lone = signup_with_microproject(client, "promo-lone@example.com", "Solo")
    alone = _study(client, lone)
    blocked = preview_promotion(client, lone, alone["id"])
    assert not blocked["can_promote"] and _levels(blocked)["target"] == "block"
    refused = post_promotion(client, lone, alone["id"])
    assert refused.status_code == 422 and refused.json()["code"] == "invalid_reference_name"


def test_blocking_rules_say_why_before_anything_is_written(client):
    slug = signup_with_microproject(client, "promo-block@example.com", "Epi")
    create_reference(client, "Taken")
    study = _study(client, slug)

    taken = preview_promotion(client, slug, study["id"], new_reference={"name": "taken"})
    assert _levels(taken)["target"] == "block"
    assert post_promotion(client, slug, study["id"], new_reference={"name": "taken"}).json()["code"] == "reference_name_taken"

    declared = launch_declared(client, slug)
    images = preview_promotion(client, slug, declared["id"], new_reference={"name": "Recuit"})
    assert _levels(images)["drawn_process"] == "block" and images["number"] is None

    campaign = launch_campaign(client, slug)
    split = preview_promotion(client, slug, campaign["id"], new_reference={"name": "Split"})
    assert _levels(split)["variant"] == "block"
    assert [v["index"] for v in split["source"]["variants"]] == [0, 1, 2]
    chosen = preview_promotion(client, slug, campaign["id"], variant=2, new_reference={"name": "Split"})
    assert chosen["can_promote"] and _levels(chosen)["variant"] == "ok" and chosen["source"]["variant"] == 2


def test_the_conclusion_is_read_not_required(client):
    slug = signup_with_microproject(client, "promo-concl@example.com", "Epi")
    kept = _study(client, slug)
    conclude(client, slug, kept["id"], decision="promote", summary="On la garde")
    preview = preview_promotion(client, slug, kept["id"], new_reference={"name": "Gardee"})
    assert _levels(preview)["concluded"] == "ok"

    other = _study(client, slug, thickness=40)
    conclude(client, slug, other["id"], decision="abandon")
    differs = preview_promotion(client, slug, other["id"], new_reference={"name": "Autre"})
    assert _levels(differs)["concluded"] == "warn" and differs["can_promote"]


def test_a_viewer_previews_but_cannot_promote(client):
    slug = signup_with_microproject(client, "promo-owner@example.com", "Epi")
    study = _study(client, slug)
    join_as(client, slug, "promo-viewer@example.com", owner="promo-owner@example.com", role="viewer")
    preview = preview_promotion(client, slug, study["id"], new_reference={"name": "X"})
    assert _levels(preview)["editor"] == "block"
    assert post_promotion(client, slug, study["id"], new_reference={"name": "X"}).status_code == 403
    assert assert_ok(client.get("/api/promotion-sources")) == []


def test_the_journal_keeps_who_why_and_the_rules_of_the_day(client):
    slug = signup_with_microproject(client, "promo-journal@example.com", "Epi")
    study = _study(client, slug)
    assert_created(post_promotion(client, slug, study["id"], new_reference={"name": "Journal"}))
    entries = assert_ok(client.get("/api/promotions"))
    assert len(entries) == 1
    entry = entries[0]
    assert (entry["reference"]["slug"], entry["number"], entry["created_reference"]) == ("journal", "1.0", True)
    assert entry["source"]["linked"] and entry["source"]["experiment_id"] == study["id"]
    assert {w["rule"] for w in entry["warnings"]} == {"concluded", "justified"}
    assert assert_ok(client.get("/api/promotions", params={"microproject": slug, "experiment_id": "autre"})) == []


def test_a_rule_registered_by_another_plugin_joins_the_form_and_can_block(client, monkeypatch):
    slug = signup_with_microproject(client, "promo-rule@example.com", "Epi")
    study = _study(client, slug)
    monkeypatch.setattr(rules, "_RULES", dict(rules._RULES))
    rules.register_rule(
        rules.Rule("three_wafers", "Au moins trois plaques", lambda c: rules.block("Il faut trois plaques mesurées.", "not_enough_wafers"), order=65)
    )
    preview = preview_promotion(client, slug, study["id"], new_reference={"name": "Regle"})
    labels = [r["label"] for r in preview["rules"]]
    assert "Au moins trois plaques" in labels and not preview["can_promote"]
    refused = post_promotion(client, slug, study["id"], new_reference={"name": "Regle"})
    assert refused.status_code == 409 and refused.json()["code"] == "not_enough_wafers"
    assert assert_ok(client.get("/api/references")) == []
