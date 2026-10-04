"""L'appartenance des étapes aux briques, l'unité des paramètres déclarés et le diff des étiquettes
(TODO § 3 ter) : une étude enregistre ses briques par ids d'étape (``process_bricks``), à part du
procédé, et les rend par positions au constructeur (``GET .../process``) ; lancement, évolution,
fourche, campagne, combinaison et écritures légères les gardent ; seules, elles ne changent pas la
version (au plus un correctif, quand elles regroupent des étiquettes) ; une unité ajoutée seule est
un correctif ; ``structure-diff`` dit, à part, ce qui change aux étiquettes."""

from __future__ import annotations

from support.experiments import (
    combine,
    conclude,
    evolve,
    get_experiment,
    launch,
    launch_campaign,
    post_evolve,
    process,
    structure_diff,
    tag,
    variants,
    versions,
)
from support.microprojects import signup_with_microproject
from support.structures import campaign_plan, deposition, fixed_step_id, identified, label_texts, layer_label

STACK = identified(
    [
        deposition("n-GaN", "GaN", recipe="MOCVD Epitaxial", thickness_nm=400),
        deposition("Puits", "In0.20Ga0.80N", recipe="MOCVD Epitaxial", thickness_nm=30),
        deposition("p-GaN", "GaN", recipe="MOCVD Epitaxial", thickness_nm=120),
    ]
)
BRICK = {"group_id": "brick-zone", "name": "Zone active", "source": "b-001", "step_indexes": [1, 2]}
LABELS = {"1": layer_label("Puits", "thickness"), "2": layer_label("p-GaN", "thickness", "declared:dopage Mg")}
DOPING = {"2": [{"name": "dopage Mg", "value": 3e18, "unit": "cm⁻³"}]}


def _metadata(slug: str, version_id: str) -> dict:
    from spectre.plugins.experiments.repository import get_repository

    return get_repository(slug).get(version_id).metadata


def _levels(client, slug: str, ref: str) -> list[str]:
    return [v["change_level"] for v in versions(client, slug, ref)]


def test_the_bricks_are_recorded_by_step_id_and_given_back_by_position(client):
    slug = signup_with_microproject(client, "bricks-launch@example.com", "Briques")
    study = launch(client, slug, steps=STACK, bricks=[BRICK])
    assert _metadata(slug, study["version_id"])["process_bricks"] == [
        {"group_id": "brick-zone", "name": "Zone active", "source": "b-001", "step_ids": [fixed_step_id(2), fixed_step_id(3)]}
    ]
    assert process(client, slug, study["id"])["bricks"] == [BRICK]
    # sans brique, la forme d'avant
    plain = launch(client, slug, title="Sans", steps=STACK)
    assert "process_bricks" not in _metadata(slug, plain["version_id"]) and process(client, slug, plain["id"])["bricks"] == []


def test_the_bricks_follow_their_steps_through_evolutions_forks_and_light_writes(client):
    slug = signup_with_microproject(client, "bricks-follow@example.com", "Suivi")
    study = launch(client, slug, steps=STACK, bricks=[BRICK])
    # une étape ajoutée en tête : la brique passe aux positions 2 et 3, mêmes ids d'étape
    contact = deposition("Tampon", "AlN", recipe="MOCVD Epitaxial", thickness_nm=50)
    evolved = evolve(client, slug, study["id"], steps=[contact, *STACK], bricks=[{**BRICK, "step_indexes": [2, 3]}])
    assert _metadata(slug, evolved["version_id"])["process_bricks"][0]["step_ids"] == [fixed_step_id(2), fixed_step_id(3)]
    assert process(client, slug, study["id"])["bricks"] == [{**BRICK, "step_indexes": [2, 3]}]

    # une écriture légère les reporte ; une version passée garde les siennes
    tagged = tag(client, slug, study["id"], ["bleu"])
    assert _metadata(slug, tagged["version_id"])["process_bricks"] == _metadata(slug, evolved["version_id"])["process_bricks"]
    assert process(client, slug, study["id"], study["version_id"])["bricks"] == [BRICK]

    # une fourche (nouvelle piste depuis une version) garde celles qu'elle envoie
    fork = launch(
        client, slug, title="Fourche", steps=process(client, slug, study["id"])["steps"], bricks=[{**BRICK, "step_indexes": [2, 3]}],
        from_version={"experiment_id": study["id"]},
    )
    assert process(client, slug, fork["id"])["bricks"] == [{**BRICK, "step_indexes": [2, 3]}]

    # une évolution sans brique n'en a plus
    cleared = evolve(client, slug, study["id"], steps=[contact, *STACK])
    assert "process_bricks" not in _metadata(slug, cleared["version_id"])


def test_a_campaign_and_a_combination_keep_the_bricks(client):
    slug = signup_with_microproject(client, "bricks-campaign@example.com", "Campagne")
    campaign = launch_campaign(
        client, slug, steps=STACK, bricks=[BRICK], layer_labels=LABELS, declared_params=DOPING,
        plan=campaign_plan([100, 150], step_id=fixed_step_id(3)), entities=[{"sample_id": "W1"}],
    )
    assert process(client, slug, campaign["id"])["bricks"] == [BRICK]
    # chaque variante : une étiquette pour la brique, avec ses propres valeurs
    assert [label_texts(svg) for svg in variants(client, slug, campaign["id"])["svgs"]] == [
        ["Zone active", "p-GaN : 100 nm · dopage Mg 3e18 cm⁻³", "Puits : 30 nm"],
        ["Zone active", "p-GaN : 150 nm · dopage Mg 3e18 cm⁻³", "Puits : 30 nm"],
    ]

    first = launch(client, slug, title="A", steps=STACK, bricks=[BRICK])
    second = launch(client, slug, title="B", steps=STACK, entities=[{"sample_id": "W2"}])
    combined = combine(client, slug, first["id"], second["id"])
    assert process(client, slug, combined["id"])["bricks"] == [BRICK]


def test_the_fiche_draws_one_label_for_the_brick(client):
    slug = signup_with_microproject(client, "bricks-fiche@example.com", "Fiche")
    study = launch(client, slug, steps=STACK, bricks=[BRICK], layer_labels=LABELS, declared_params=DOPING)
    assert label_texts(study["structure_svg"]) == ["Zone active", "p-GaN : 120 nm · dopage Mg 3e18 cm⁻³", "Puits : 30 nm"]
    # une version légère redessine de même
    assert label_texts(tag(client, slug, study["id"], ["x"])["structure_svg"]) == label_texts(study["structure_svg"])


def test_bricks_alone_never_change_the_structure(client):
    slug = signup_with_microproject(client, "bricks-version@example.com", "Version")
    study = launch(client, slug, steps=STACK)
    conclude(client, slug, study["id"], summary="Concluante", decision="promote")

    # une brique ajoutée, sans étiquette : une version, mais pas de structure (ni conclusion perdue)
    grouped = evolve(client, slug, study["id"], steps=STACK, bricks=[BRICK])
    assert _levels(client, slug, study["id"])[-1] == "none"
    assert grouped["conclusion"]["summary"] == "Concluante"
    # les mêmes briques renvoyées : rien de nouveau
    assert post_evolve(client, slug, study["id"], steps=STACK, bricks=[BRICK], title="Essai", intent="Suite").status_code == 200

    # avec deux étapes étiquetées dans la brique, la regrouper change le dessin : un correctif, au plus
    labelled = evolve(client, slug, study["id"], steps=STACK, layer_labels=LABELS)
    regrouped = evolve(client, slug, study["id"], steps=STACK, layer_labels=LABELS, bricks=[BRICK])
    assert _levels(client, slug, study["id"])[-2:] == ["patch", "patch"]
    assert regrouped["conclusion"]["summary"] == labelled["conclusion"]["summary"]
    # renommer la brique sans étiquette regroupée ne se voit pas : aucun niveau
    single = {"2": LABELS["2"]}
    evolve(client, slug, study["id"], steps=STACK, layer_labels=single, bricks=[BRICK])
    evolve(client, slug, study["id"], steps=STACK, layer_labels=single, bricks=[{**BRICK, "name": "Autre nom"}])
    assert _levels(client, slug, study["id"])[-1] == "none"
    assert [v["version"] for v in versions(client, slug, study["id"])][-1].startswith("1.0.")


def test_a_unit_written_down_alone_is_a_patch_that_keeps_the_conclusion(client):
    slug = signup_with_microproject(client, "units-version@example.com", "Unités")
    bare = {"2": [{"name": "dopage Mg", "value": 3e18}]}
    study = launch(client, slug, steps=STACK, declared_params=bare)
    conclude(client, slug, study["id"], summary="Concluante", decision="promote")

    with_unit = evolve(client, slug, study["id"], steps=STACK, declared_params=DOPING)
    assert _levels(client, slug, study["id"])[-1] == "patch"
    assert with_unit["conclusion"]["summary"] == "Concluante"
    assert process(client, slug, study["id"])["declared_params"] == {"2": [{"name": "dopage Mg", "value": 3e18, "obtention": {}, "unit": "cm⁻³"}]}
    # une autre unité change la valeur : un réglage (mineur), la conclusion repart
    other = evolve(client, slug, study["id"], steps=STACK, declared_params={"2": [{"name": "dopage Mg", "value": 3e18, "unit": "m⁻³"}]})
    assert _levels(client, slug, study["id"])[-1] == "minor" and not other["conclusion"]["summary"]
    # l'ancienne astuce de l'obtention passée au champ, la même unité : un correctif
    study2 = launch(client, slug, title="Astuce", steps=STACK, declared_params={"2": [{"name": "dopage Mg", "value": 3e18, "obtention": {"unit": "cm⁻³"}}]})
    evolve(client, slug, study2["id"], steps=STACK, declared_params=DOPING)
    assert _levels(client, slug, study2["id"])[-1] == "patch"
    # sans unité, un paramètre garde sa forme d'avant : le renvoyer tel quel ne change rien
    assert post_evolve(client, slug, study2["id"], steps=STACK, declared_params=DOPING, title="Essai", intent="Suite").status_code == 200


def test_the_structure_diff_tells_the_label_changes_apart(client):
    slug = signup_with_microproject(client, "labels-diff@example.com", "Diff")
    study = launch(client, slug, steps=STACK, declared_params=DOPING, layer_labels={"2": layer_label("p-GaN", "thickness")})
    # une version qui ne change que les étiquettes : un dopage ajouté au p-GaN, le puits étiqueté
    relabelled = evolve(client, slug, study["id"], steps=STACK, declared_params=DOPING, layer_labels=LABELS)
    diff = structure_diff(client, slug, study["id"], version=relabelled["version_id"])
    assert diff["entries"] == [] and diff["target"]["version_id"] == study["version_id"]
    assert [(c.get("step_id"), c["change"]) for c in diff["label_changes"]] == [(fixed_step_id(2), "added"), (fixed_step_id(3), "modified")]
    assert [c["line"] for c in diff["label_changes"]] == ["Puits — étiquette ajoutée", "p-GaN — ajout : dopage Mg"]
    assert diff["label_changes"][1]["values_added"] == ["dopage Mg"] and diff["label_changes"][1]["values_removed"] == []

    # regrouper les deux étiquettes dans la brique, renommer une étiquette, retirer une valeur
    grouped = evolve(
        client, slug, study["id"], steps=STACK, declared_params=DOPING, bricks=[BRICK],
        layer_labels={"1": layer_label("MQW", "thickness"), "2": layer_label("p-GaN", "declared:dopage Mg")},
    )
    lines = [c["line"] for c in structure_diff(client, slug, study["id"], version=grouped["version_id"])["label_changes"]]
    assert lines == ["MQW — texte « Puits » → « MQW »", "p-GaN — retrait : épaisseur", "brique Zone active — étiquettes regroupées"]
    # une étiquette retirée ; la brique renommée
    last = evolve(client, slug, study["id"], steps=STACK, declared_params=DOPING, bricks=[{**BRICK, "name": "Région active"}],
                  layer_labels={"1": layer_label("MQW", "thickness"), "2": layer_label("p-GaN", "declared:dopage Mg")})
    lines = [c["line"] for c in structure_diff(client, slug, study["id"], version=last["version_id"])["label_changes"]]
    assert lines == ["brique « Zone active » renommée « Région active »"]
    dropped = evolve(client, slug, study["id"], steps=STACK, declared_params=DOPING, layer_labels={"2": layer_label("p-GaN", "declared:dopage Mg")})
    lines = [c["line"] for c in structure_diff(client, slug, study["id"], version=dropped["version_id"])["label_changes"]]
    assert lines == ["MQW — étiquette retirée", "brique Région active — étiquettes séparées"]
    # sans étiquette de part et d'autre : rien ; sans cible (la première structure), la réponse d'avant
    plain = launch(client, slug, title="Nue", steps=STACK)
    assert structure_diff(client, slug, plain["id"]) == {"target": None, "entries": []}
    unlabelled = evolve(client, slug, plain["id"], steps=[*STACK, deposition("Contact", "ITO", recipe="Sputter Metal (normal)")])
    diff = structure_diff(client, slug, plain["id"], version=unlabelled["version_id"])
    assert diff["entries"] and diff["label_changes"] == []
    assert get_experiment(client, slug, plain["id"])["structure_svg"]
