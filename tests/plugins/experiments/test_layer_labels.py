"""Les étiquettes de couches d'une étude (TODO § 3 ter) : réglées dans le constructeur, enregistrées
avec la version, par id d'étape (``process_layer_labels``) avec la provenance des couches
(``process_layer_steps``) ; dessinées sur la fiche, le carrousel d'une campagne et la page
d'évolution ; une évolution qui ne change qu'elles est une version de niveau correctif, qui garde
la conclusion. Les anciennes versions n'en ont pas."""

from __future__ import annotations

from support.experiments import (
    combine,
    conclude,
    evolve,
    evolve_image,
    get_experiment,
    get_version,
    launch,
    launch_campaign,
    post_evolve,
    process,
    tag,
    variants,
    versions,
)
from support.microprojects import signup_with_microproject
from support.structures import campaign_plan, deposition, fixed_step_id, identified, label_texts, layer_label, upload_structure_image

STACK = identified(
    [
        deposition("n-GaN", "GaN", recipe="MOCVD Epitaxial", thickness_nm=400),
        deposition("Puits", "In0.20Ga0.80N", recipe="MOCVD Epitaxial", thickness_nm=3),
        deposition("p-GaN", "GaN", recipe="MOCVD Epitaxial", thickness_nm=150),
    ]
)
DOPING = {"2": [{"name": "dopage", "value": 2e19}]}
LABELS = {"1": layer_label("", "composition"), "2": layer_label("p-GaN", "thickness", "declared:dopage")}


def _metadata(slug: str, version_id: str) -> dict:
    from spectre.plugins.experiments.repository import get_repository

    return get_repository(slug).get(version_id).metadata


def _labelled(client, email: str) -> tuple[str, dict]:
    slug = signup_with_microproject(client, email, "Étiquettes")
    return slug, launch(client, slug, steps=STACK, declared_params=DOPING, layer_labels=LABELS)


def test_labels_are_recorded_by_step_id_and_drawn_on_the_fiche(client):
    slug, study = _labelled(client, "labels-launch@example.com")
    assert label_texts(study["structure_svg"]) == ["p-GaN", "150 nm", "dopage : 2e19", "In0.20Ga0.80N", "In 20 %"]

    metadata = _metadata(slug, study["version_id"])
    assert metadata["process_layer_labels"] == {
        fixed_step_id(2): {"text": "", "values": ["composition"]},
        fixed_step_id(3): {"text": "p-GaN", "values": ["thickness", "declared:dopage"]},
    }
    # la provenance de chaque couche de la structure enregistrée (None : le substrat)
    assert metadata["process_layer_steps"] == [[None, fixed_step_id(1), fixed_step_id(2), fixed_step_id(3)]]
    # le constructeur les relit par position d'étape, comme les paramètres déclarés
    assert process(client, slug, study["id"])["layer_labels"] == {
        "1": {"text": "", "values": ["composition"]},
        "2": {"text": "p-GaN", "values": ["thickness", "declared:dopage"]},
    }


def test_a_study_without_labels_keeps_its_former_shape(client):
    slug = signup_with_microproject(client, "labels-none@example.com", "Sans")
    study = launch(client, slug, steps=STACK)
    metadata = _metadata(slug, study["version_id"])
    assert "process_layer_labels" not in metadata and "process_layer_steps" not in metadata
    assert "sp-layer-labels" not in study["structure_svg"]
    assert process(client, slug, study["id"])["layer_labels"] == {}
    # renvoyer la même structure, sans étiquette : rien ne change
    assert post_evolve(client, slug, study["id"], steps=STACK, title="Essai", intent="Verifier").status_code == 200


def test_changing_only_the_labels_is_a_patch_version_that_keeps_the_conclusion(client):
    slug, study = _labelled(client, "labels-patch@example.com")
    conclude(client, slug, study["id"], summary="Concluante", decision="promote")

    relabelled = evolve(
        client, slug, study["id"], title="Essai", intent="Verifier", steps=STACK, declared_params=DOPING, layer_labels={"2": layer_label("p++", "thickness")}
    )
    frise = versions(client, slug, study["id"])
    assert [(v["version"], v["change_level"]) for v in frise if v["change_level"] != "none"] == [("1.0.0", "initial"), ("1.0.1", "patch")]
    assert relabelled["conclusion"]["summary"] == "Concluante"
    assert label_texts(relabelled["structure_svg"]) == ["p++", "150 nm"]

    # les mêmes étiquettes : rien de nouveau ; plus aucune : une version, sans étiquettes
    same = post_evolve(
        client, slug, study["id"], steps=STACK, declared_params=DOPING, layer_labels={"2": layer_label("p++", "thickness")}, title="Essai", intent="Verifier"
    )
    assert same.status_code == 200
    cleared = evolve(client, slug, study["id"], title="Essai", intent="Verifier", steps=STACK, declared_params=DOPING)
    assert "sp-layer-labels" not in cleared["structure_svg"]
    assert "process_layer_labels" not in _metadata(slug, cleared["version_id"])
    assert versions(client, slug, study["id"])[-1]["change_level"] == "patch"


def test_a_label_follows_its_step_when_the_process_evolves(client):
    slug, study = _labelled(client, "labels-follow@example.com")
    # une étape ajoutée en tête : le p-GaN passe en position 3, il garde son id et son étiquette
    contact = deposition("Contact", "ITO", recipe="Sputter Metal (normal)", thickness_nm=100)
    evolved = evolve(
        client,
        slug,
        study["id"],
        steps=[contact, *STACK],
        declared_params={"3": DOPING["2"]},
        layer_labels={"3": layer_label("p-GaN", "thickness", "declared:dopage"), "0": layer_label("ITO", "thickness")},
    )
    labels = _metadata(slug, evolved["version_id"])["process_layer_labels"]
    assert labels[fixed_step_id(3)] == {"text": "p-GaN", "values": ["thickness", "declared:dopage"]}
    assert fixed_step_id(2) not in labels and len(labels) == 2
    assert process(client, slug, study["id"])["layer_labels"]["3"]["text"] == "p-GaN"

    # une écriture légère (une étiquette de fiche) les reporte telles quelles
    tagged = tag(client, slug, study["id"], ["bleu"])
    assert _metadata(slug, tagged["version_id"])["process_layer_labels"] == labels
    assert label_texts(tagged["structure_svg"]) == label_texts(evolved["structure_svg"])
    # une version passée garde les siennes
    assert label_texts(get_version(client, slug, study["id"], study["version_id"])["structure_svg"])[0] == "p-GaN"


def test_each_variant_of_a_campaign_writes_its_own_values(client):
    slug = signup_with_microproject(client, "labels-campaign@example.com", "Campagne")
    campaign = launch_campaign(
        client, slug, plan=campaign_plan([10, 20, 30]), layer_labels={"0": layer_label("Oxyde", "thickness")}, entities=[{"sample_id": "W1"}]
    )
    svgs = variants(client, slug, campaign["id"])["svgs"]
    assert [label_texts(svg) for svg in svgs] == [["Oxyde", "10 nm"], ["Oxyde", "20 nm"], ["Oxyde", "30 nm"]]
    assert label_texts(campaign["structure_svg"]) == ["Oxyde", "10 nm"]
    assert len(_metadata(slug, campaign["version_id"])["process_layer_steps"]) == 3


def test_a_combination_takes_the_labels_of_its_first_study_and_pictures_drop_them(client):
    slug, study = _labelled(client, "labels-combine@example.com")
    other = launch(client, slug, title="Autre", steps=STACK, entities=[{"sample_id": "W2"}])
    combined = combine(client, slug, study["id"], other["id"])
    assert label_texts(combined["structure_svg"]) == label_texts(study["structure_svg"])

    image_id = upload_structure_image(client, slug)
    pictured = evolve_image(client, slug, study["id"], [{"image_id": image_id}])
    metadata = _metadata(slug, pictured["version_id"])
    assert "process_layer_labels" not in metadata and "process_layer_steps" not in metadata
    assert get_experiment(client, slug, study["id"])["structure_svg"] is None
