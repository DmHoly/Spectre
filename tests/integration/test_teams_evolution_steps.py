"""Les trois chantiers ensemble : un manager d'équipe (sans adhésion au µprojet) travaille sur la page
« Évolution des structures » d'un µprojet de son équipe, et une évolution qu'il enregistre garde
les ids des étapes."""

from __future__ import annotations

from support.accounts import login
from support.experiments import evolve, launch, step_ids, structure_history
from support.microprojects import get_microproject
from support.structures import deposition, etch, steps
from support.teams import team_world


def test_a_team_manager_works_on_the_evolution_page_and_keeps_step_ids(client):
    world = team_world(client)
    login(client, world.researcher)
    launched = launch(client, "recuit", title="Piste", intent="Depart", steps=steps(20))
    first_ids = step_ids(client, "recuit", launched["id"])

    login(client, world.manager_a)  # manager de l'équipe du thème, pas membre du µprojet
    assert get_microproject(client, "recuit")["can_edit"] is True
    history = structure_history(client, "recuit")
    assert [node["version_id"] for node in history["nodes"]] == [launched["version_id"]]

    evolved = evolve(
        client, "recuit", launched["id"], title="Piste", intent="Ajout d'une gravure",
        steps=[{"id": first_ids[0], **deposition(thickness_nm=30)}, etch()],
    )
    ids = step_ids(client, "recuit", launched["id"])
    assert ids[0] == first_ids[0] and ids[1] != first_ids[0]  # l'étape gardée garde son id, la nouvelle en reçoit un
    nodes = structure_history(client, "recuit")["nodes"]
    assert [(node["version_id"], node["label"]) for node in nodes] == [(launched["version_id"], "v1.0"), (evolved["version_id"], "v2.0")]

    login(client, world.viewer)  # lecteur par adhésion : lit, n'écrit pas
    assert len(structure_history(client, "recuit")["nodes"]) == 2

    login(client, world.manager_b)  # manager d'une autre équipe : rien
    assert client.get("/api/microprojects/recuit/structure-history").status_code == 403

    login(client, world.member_a)  # simple membre de l'équipe : il lit, n'écrit pas
    assert len(structure_history(client, "recuit")["nodes"]) == 2
    assert get_microproject(client, "recuit")["can_edit"] is False
