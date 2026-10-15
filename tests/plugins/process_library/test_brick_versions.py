"""Les briques et leurs copies : une brique de départ garde son substrat (prise dans une structure
vide seulement, côté constructeur), une brique a une version que ses copies gardent, et on sait dans
quelles études elle sert. Les macro-étapes d'avant (rôle gabarit SAG / épitaxie / procédé) n'existent
plus : un rôle encore enregistré est ignoré."""

from __future__ import annotations

import json

from support.accounts import login
from support.experiments import launch, process
from support.microprojects import signup_with_microproject
from support.process_library import create_item, get_item, tech_brick, update_item
from support.structures import deposition, identified, length, simulate

from spectre.plugins.process_library import migrations

SAG_SUBSTRATE = {"material": "GaN", "domain_width": length(400), "thickness": length(50), "lattice": {"pitch": 400, "wires": 1}}
STACK = identified(
    [
        deposition("Masque", "Si3N4", thickness_nm=30),
        deposition("n-GaN", "GaN", recipe="MOCVD Epitaxial", thickness_nm=200),
        deposition("Puits", "In0.20Ga0.80N", recipe="MOCVD Epitaxial", thickness_nm=30),
        deposition("Passivation", "SiO2", thickness_nm=20),
    ]
)
SAG = {"group_id": "brick-sag", "name": "SAG 400", "source": "b-sag", "step_indexes": [0]}
EPI = {"group_id": "brick-epi", "name": "Épi bleue", "source": "b-epi", "step_indexes": [1, 2]}
PROCESS = {"group_id": "brick-proc", "name": "Passivation", "step_indexes": [3]}


def test_a_starting_brick_keeps_its_substrate_and_the_others_have_none(client):
    slug = signup_with_microproject(client, "brick-start@example.com", "Salle blanche")
    sag = create_item(client, "tech-bricks", tech_brick("SAG 400", substrate=SAG_SUBSTRATE), microproject=slug)
    assert get_item(client, "tech-bricks", sag["id"])["substrate"]["lattice"] == {"pitch": 400, "wires": 1}

    # une brique ordinaire s'applique par-dessus ce qui existe : pas de substrat dans sa forme
    epi = create_item(client, "tech-bricks", tech_brick("Épi bleue"), microproject=slug)
    assert "substrate" not in epi
    # le substrat se retire, et se donne après coup
    assert "substrate" not in update_item(client, "tech-bricks", sag["id"], substrate=None)
    assert update_item(client, "tech-bricks", epi["id"], substrate=SAG_SUBSTRATE)["substrate"]["material"] == "GaN"


def test_the_old_macro_step_role_is_ignored(client):
    signup_with_microproject(client, "brick-roles@example.com", "Salle blanche")
    body = {"substrate": SAG_SUBSTRATE, "steps": STACK, "bricks": [{**SAG, "role": "sag"}, {**EPI, "role": "epi"}, {**PROCESS, "role": "epi"}]}
    response = simulate(client, body)
    assert response.status_code == 200, response.text
    # la requête d'une brique de bibliothèque de l'ancienne forme passe aussi : le rôle et les briques
    # d'aperçu n'ont plus de sens, ils sont ignorés
    old = client.post("/api/tech-bricks", json={**tech_brick("Vieille", role="epi", preview_on=["x"]), "scope": "shared"})
    assert old.status_code == 201 and "role" not in old.json() and "preview_on" not in old.json()


def test_the_migration_drops_the_roles_of_the_bricks_on_disk(client, data_dir):
    slug = signup_with_microproject(client, "brick-migration@example.com", "Salle blanche")
    brick = create_item(client, "tech-bricks", tech_brick("SAG 400", substrate=SAG_SUBSTRATE), microproject=slug)
    path = data_dir / "microprojects" / slug / "briques.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["items"][0].update({"role": "sag", "preview_on": [], "bricks": [{"group_id": "g", "name": "Interne", "step_indexes": [0], "role": "epi"}]})
    path.write_text(json.dumps(data), encoding="utf-8")

    # avant la migration, la brique se lit déjà sans son rôle
    read = get_item(client, "tech-bricks", brick["id"])
    assert "role" not in read and "preview_on" not in read and "role" not in read["bricks"][0]

    migrations.drop_macro_step_roles()
    migrations.drop_macro_step_roles()  # déjà migré : rien ne change
    [raw] = json.loads(path.read_text(encoding="utf-8"))["items"]
    assert "role" not in raw and "preview_on" not in raw and "role" not in raw["bricks"][0]
    assert raw["substrate"]["lattice"]["pitch"] == 400  # un gabarit SAG garde son substrat : une brique de départ


def test_a_brick_has_a_version_that_its_copies_keep(client):
    slug = signup_with_microproject(client, "brick-version@example.com", "Salle blanche")
    epi = create_item(client, "tech-bricks", tech_brick("Épi bleue"), microproject=slug)
    assert epi["version"] == 1
    # son nom, ses notes : la même version ; ses étapes : une nouvelle
    assert update_item(client, "tech-bricks", epi["id"], name="Épi bleue 2", notes="LED")["version"] == 1
    thicker = [deposition("PGaN", "GaN", thickness_nm=80)]
    assert update_item(client, "tech-bricks", epi["id"], steps=thicker)["version"] == 2

    # la copie dans une étude garde la version d'alors, d'une version de l'étude à l'autre
    copy = {**EPI, "source": epi["id"], "version": 1}
    study = launch(client, slug, substrate=SAG_SUBSTRATE, steps=STACK, bricks=[SAG, copy])
    assert process(client, slug, study["id"])["bricks"][1]["version"] == 1
    assert "version" not in process(client, slug, study["id"])["bricks"][0]  # une brique sans version : la forme d'avant


def test_the_studies_that_use_a_brick_are_listed_with_the_version_they_copied(client):
    slug = signup_with_microproject(client, "brick-usages@example.com", "Salle blanche")
    sag = create_item(client, "tech-bricks", tech_brick("SAG 400", substrate=SAG_SUBSTRATE), scope="shared")
    epi = create_item(client, "tech-bricks", tech_brick("Épi bleue"), microproject=slug)
    unused = create_item(client, "tech-bricks", tech_brick("Procédé seul"), microproject=slug)
    copies = [{**SAG, "source": sag["id"], "version": 1}, {**EPI, "source": epi["id"], "version": 1}]
    study = launch(client, slug, title="Pixel bleu", substrate=SAG_SUBSTRATE, steps=STACK, bricks=copies)
    update_item(client, "tech-bricks", epi["id"], steps=[deposition("PGaN", "GaN", thickness_nm=80)])  # v2

    usages = client.get("/api/tech-brick-usages", params={"microproject": slug}).json()
    assert usages[unused["id"]] == []
    [use] = usages[epi["id"]]
    assert use["linked"] and use["experiment_id"] == study["id"] and use["title"] == "Pixel bleu"
    assert use["version"] == 1 and use["microproject"]["slug"] == slug

    # la brique de départ est partagée : un compte d'un autre µprojet la voit servir, sans voir l'étude
    other = signup_with_microproject(client, "brick-usages-other@example.com", "Autre salle")
    [hidden] = client.get("/api/tech-brick-usages", params={"microproject": other}).json()[sag["id"]]
    assert hidden == {"microproject": {"name": "Salle blanche"}, "linked": False, "version": 1}
    assert epi["id"] not in client.get("/api/tech-brick-usages", params={"microproject": other}).json()
    login(client, "brick-usages@example.com")
