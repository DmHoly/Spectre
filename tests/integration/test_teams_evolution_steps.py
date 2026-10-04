"""Les trois chantiers ensemble : un manager d'équipe (sans adhésion au µprojet) travaille sur la page
« Évolution des structures » d'un µprojet de son équipe, et une évolution qu'il enregistre garde
les ids des étapes."""

from __future__ import annotations

from support.accounts import login
from support.experiments import (
    create_ref,
    delete_ref,
    evolve,
    get_ref,
    launch,
    patch_ref,
    rename_ref,
    step_ids,
    structure_history,
)
from support.microprojects import get_microproject
from support.structures import deposition, etch, steps
from support.teams import team_world


def test_a_team_manager_works_on_the_evolution_page_and_keeps_step_ids(client):
    world = team_world(client)
    login(client, world.researcher)
    launched = launch(client, "recuit", title="Piste", intent="Depart", steps=steps(20))
    create_ref(client, "recuit", launched["id"], "depart")
    first_ids = step_ids(client, "recuit", launched["id"])

    login(client, world.manager_a)  # manager de l'équipe du thème, pas membre du µprojet
    assert get_microproject(client, "recuit")["can_edit"] is True
    history = structure_history(client, "recuit")
    assert ["depart" in node["refs"] for node in history["nodes"]] == [True]

    evolved = evolve(
        client, "recuit", launched["id"], title="Piste", intent="Ajout d'une gravure",
        steps=[{"id": first_ids[0], **deposition(thickness_nm=30)}, etch()],
    )
    ids = step_ids(client, "recuit", launched["id"])
    assert ids[0] == first_ids[0] and ids[1] != first_ids[0]  # l'étape gardée garde son id, la nouvelle en reçoit un
    create_ref(client, "recuit", launched["id"], "gravure", version_id=evolved["version_id"])
    assert rename_ref(client, "recuit", "gravure", "gravure-v2")["name"] == "gravure-v2"
    assert delete_ref(client, "recuit", "depart").status_code == 204
    nodes = structure_history(client, "recuit")["nodes"]
    assert [node["version_id"] for node in nodes] == [launched["version_id"], evolved["version_id"]]
    assert "depart" not in nodes[0]["refs"] and "gravure-v2" in nodes[1]["refs"]

    login(client, world.viewer)  # lecteur par adhésion : lit, ne touche pas aux refs
    assert get_ref(client, "recuit", "gravure-v2")["version_id"] == evolved["version_id"]
    assert patch_ref(client, "recuit", "gravure-v2", "x").status_code == 403

    for outsider in (world.manager_b, world.member_a):  # manager d'une autre équipe, simple membre de l'équipe
        login(client, outsider)
        assert client.get("/api/microprojects/recuit/structure-history").status_code == 403
