"""Liens entre µprojets et entre entités physiques (plugin links) : la seule relation qui traverse deux
dépôts Follow. Créer un lien demande le rôle editor des deux côtés, le retirer d'un seul ; un lien ne
se lit que si l'on est membre de ses deux µprojets. Une entité désigne la piste, jamais une version.
"""

from __future__ import annotations

import sqlite3

from support.accounts import login, me, signup
from support.areas import create_area
from support.experiments import conclude, delete_experiment, launch, post_launch, tag, track_entities
from support.http import assert_handler_404
from support.links import (
    entity,
    entity_links,
    link_entities,
    link_microprojects,
    microproject_links,
    post_entity_link,
    post_microproject_link,
)
from support.microprojects import create_microproject, delete_microproject, get_microproject, join_as, move_microproject, signup_with_microproject


def _two_microprojects(client, email):
    """Deux µprojets dont le compte ``email`` est propriétaire."""
    slug_a = signup_with_microproject(client, email, "Projet A")
    return slug_a, create_microproject(client, "Projet B")["slug"]


def _two_tracked_studies(client, email):
    """Deux µprojets, chacun avec une étude qui suit deux plaques - renvoie leurs slugs et pistes."""
    slug_a, slug_b = _two_microprojects(client, email)
    exp_a = launch(client, slug_a, title="Etude A", intent="Depart", entities=[{"sample_id": "W-A1"}, {"sample_id": "W-A2"}])
    exp_b = launch(client, slug_b, title="Etude B", intent="Depart", entities=[{"sample_id": "W-B1"}, {"sample_id": "W-B2"}])
    return slug_a, exp_a["id"], slug_b, exp_b["id"]


# -- liens entre µprojets -------------------------------------------------------------------------


def test_an_editor_on_both_microprojects_links_them(client):
    slug_a, slug_b = _two_microprojects(client, "linker@example.com")

    created = link_microprojects(client, slug_a, slug_b, " Même famille de matériaux ")
    assert created["a"] == {"slug": slug_a, "name": "Projet A"}
    assert created["b"] == {"slug": slug_b, "name": "Projet B"}
    assert created["note"] == "Même famille de matériaux"
    assert microproject_links(client) == [created]
    assert microproject_links(client, microproject=slug_b) == [created]


def test_a_microproject_cannot_be_linked_to_itself(client):
    slug = signup_with_microproject(client, "selflink@example.com")
    response = post_microproject_link(client, slug, slug)
    assert response.status_code == 422 and response.json()["code"] == "self_link"


def test_two_microprojects_are_linked_once_in_either_direction(client):
    slug_a, slug_b = _two_microprojects(client, "twice@example.com")
    link_microprojects(client, slug_a, slug_b)
    for a, b in ((slug_a, slug_b), (slug_b, slug_a)):
        response = post_microproject_link(client, a, b)
        assert response.status_code == 409 and response.json()["code"] == "already_linked"
    assert len(microproject_links(client)) == 1


def test_linking_needs_the_editor_role_on_both_sides(client):
    owner_slug = signup_with_microproject(client, "owner-links@example.com", "Chez le propriétaire")
    join_as(client, owner_slug, "viewer-links@example.com", owner="owner-links@example.com", role="viewer")
    own_slug = create_microproject(client, "Chez le viewer")["slug"]
    assert get_microproject(client, owner_slug)["role"] == "viewer"

    assert post_microproject_link(client, own_slug, owner_slug).status_code == 403
    assert microproject_links(client) == []


def test_linking_an_unknown_microproject_is_invalid(client):
    slug = signup_with_microproject(client, "unknown-links@example.com")
    response = post_microproject_link(client, slug, "ne-existe-pas")
    assert response.status_code == 422 and response.json()["code"] == "unknown_microproject"


def test_a_link_is_listed_only_to_members_of_both_sides(client):
    slug_a, slug_b = _two_microprojects(client, "visibility-a@example.com")
    link_microprojects(client, slug_a, slug_b)

    # membre d'un seul côté : le lien nommerait un µprojet qu'il ne peut pas ouvrir
    join_as(client, slug_a, "visibility-half@example.com", owner="visibility-a@example.com", role="editor")
    assert microproject_links(client) == []
    assert microproject_links(client, microproject=slug_a) == []

    # sans aucun lien avec l'un ou l'autre : ?microproject= est refusé
    signup(client, "visibility-c@example.com")
    assert microproject_links(client) == []
    assert client.get("/api/microproject-links", params={"microproject": slug_a}).status_code == 403
    assert_handler_404(client.get("/api/microproject-links", params={"microproject": "ne-existe-pas"}))


def test_links_are_filtered_by_corporate_project(client):
    slug_a, slug_b = _two_microprojects(client, "area-links@example.com")
    slug_c = create_microproject(client, "Projet C")["slug"]
    ab = link_microprojects(client, slug_a, slug_b)
    bc = link_microprojects(client, slug_b, slug_c)

    login(client, "area-links@example.com")  # le premier compte est administrateur
    area = create_area(client, "Fiabilité")
    move_microproject(client, area["slug"], slug_c)

    # un lien est retenu dès que l'un de ses bouts est dans le projet
    assert microproject_links(client, area=area["slug"]) == [bc]
    assert microproject_links(client, area="non-classe") == [ab, bc]
    assert_handler_404(client.get("/api/microproject-links", params={"area": "ne-existe-pas"}))


def test_retracting_a_link_needs_the_editor_role_on_one_side(client):
    slug_a, slug_b = _two_microprojects(client, "delete-links-a@example.com")
    link_id = link_microprojects(client, slug_a, slug_b)["id"]

    signup(client, "delete-links-stranger@example.com")
    assert client.delete(f"/api/microproject-links/{link_id}").status_code == 403

    join_as(client, slug_a, "delete-links-viewer@example.com", owner="delete-links-a@example.com", role="viewer")
    assert client.delete(f"/api/microproject-links/{link_id}").status_code == 403

    join_as(client, slug_b, "delete-links-editor@example.com", owner="delete-links-a@example.com", role="editor")
    response = client.delete(f"/api/microproject-links/{link_id}")
    assert response.status_code == 204 and response.content == b""

    login(client, "delete-links-a@example.com")
    assert microproject_links(client) == []
    assert_handler_404(client.delete(f"/api/microproject-links/{link_id}"))


# -- liens entre entités --------------------------------------------------------------------------


def test_an_editor_on_both_sides_links_two_entities_by_their_piste(client):
    slug_a, exp_a, slug_b, exp_b = _two_tracked_studies(client, "entity-link@example.com")

    created = link_entities(client, entity(slug_a, exp_a, 1), entity(slug_b, exp_b, 0), "Même lot de substrat")
    assert created["a"] == {"microproject": slug_a, "experiment_id": exp_a, "entity_index": 1}
    assert created["b"] == {"microproject": slug_b, "experiment_id": exp_b, "entity_index": 0}
    assert created["note"] == "Même lot de substrat"
    assert entity_links(client) == [created]
    assert entity_links(client, microproject=slug_b) == [created]
    assert entity_links(client, area="non-classe") == [created]


def test_an_entity_link_survives_writes_on_both_studies(client):
    slug_a, exp_a, slug_b, exp_b = _two_tracked_studies(client, "entity-link-writes@example.com")
    created = link_entities(client, entity(slug_a, exp_a), entity(slug_b, exp_b))

    conclude(client, slug_a, exp_a, decision="promote")
    tag(client, slug_b, exp_b, ["suivi"])
    assert entity_links(client) == [created]


def test_an_entity_link_target_must_exist(client):
    slug_a, exp_a, slug_b, exp_b = _two_tracked_studies(client, "entity-link-target@example.com")
    cases = {
        "unknown_experiment": entity(slug_b, "piste-inconnue"),
        "unknown_entity": entity(slug_b, exp_b, 2),  # deux plaques suivies : 0 et 1
        "unknown_microproject": entity("ne-existe-pas", exp_b),
    }
    for code, b in cases.items():
        response = post_entity_link(client, entity(slug_a, exp_a), b)
        assert response.status_code == 422 and response.json()["code"] == code, response.text
    negative = post_entity_link(client, entity(slug_a, exp_a), entity(slug_b, exp_b, -1))
    assert negative.status_code == 422 and negative.json()["code"] == "unknown_entity"

    itself = post_entity_link(client, entity(slug_a, exp_a), entity(slug_a, exp_a))
    assert itself.status_code == 422 and itself.json()["code"] == "self_link"
    assert entity_links(client) == []


def test_a_deleted_line_never_hands_its_entity_links_to_a_new_study(client):
    # un lien d'entité désigne la piste par son nom : supprimer la piste laisse le lien (listé,
    # supprimable), et le nom n'est jamais redonné - sinon le lien passerait à une étude sans rapport
    slug_a, exp_a, slug_b, exp_b = _two_tracked_studies(client, "entity-link-retired@example.com")
    created = link_entities(client, entity(slug_a, exp_a), entity(slug_b, exp_b))
    assert exp_b == "etude-b"

    assert delete_experiment(client, slug_b, exp_b).status_code == 204
    assert entity_links(client) == [created]
    again = launch(client, slug_b, title="Etude B", intent="Autre", entities=[{"sample_id": "AUTRE-PLAQUE"}])
    assert again["id"] == "etude-b-2"
    taken = post_launch(client, slug_b, title="Etude B", intent="Autre", branch="etude-b")
    assert taken.status_code == 409 and taken.json()["code"] == "branch_name_taken"
    assert entity_links(client) == [created]  # toujours vers la piste supprimée
    assert post_entity_link(client, entity(slug_a, exp_a), entity(slug_b, "etude-b")).json()["code"] == "unknown_experiment"


def test_the_entity_index_is_checked_against_the_tip(client):
    slug_a, exp_a, slug_b, exp_b = _two_tracked_studies(client, "entity-link-tip@example.com")
    track_entities(client, slug_b, exp_b, [{"sample_id": "W-B1"}])  # la pointe ne suit plus qu'une plaque
    assert post_entity_link(client, entity(slug_a, exp_a), entity(slug_b, exp_b, 1)).status_code == 422


def test_linking_entities_needs_the_editor_role_on_both_sides(client):
    slug_a, exp_a, slug_b, exp_b = _two_tracked_studies(client, "entity-link-owner@example.com")
    join_as(client, slug_b, "entity-link-viewer@example.com", owner="entity-link-owner@example.com", role="viewer")
    own = create_microproject(client, "Chez le viewer")["slug"]
    own_exp = launch(client, own)["id"]

    assert post_entity_link(client, entity(own, own_exp), entity(slug_b, exp_b)).status_code == 403


def test_retracting_an_entity_link_needs_the_editor_role_on_one_side(client):
    slug_a, exp_a, slug_b, exp_b = _two_tracked_studies(client, "entity-delete@example.com")
    link_id = link_entities(client, entity(slug_a, exp_a), entity(slug_b, exp_b))["id"]

    signup(client, "entity-delete-stranger@example.com")
    assert client.delete(f"/api/entity-links/{link_id}").status_code == 403

    join_as(client, slug_a, "entity-delete-editor@example.com", owner="entity-delete@example.com", role="editor")
    assert client.delete(f"/api/entity-links/{link_id}").status_code == 204
    assert_handler_404(client.delete(f"/api/entity-links/{link_id}"))


# -- stockage -------------------------------------------------------------------------------------


def test_deleting_a_microproject_purges_its_links(client):
    slug_a, exp_a, slug_b, exp_b = _two_tracked_studies(client, "purge@example.com")
    slug_c = create_microproject(client, "Projet C")["slug"]
    link_microprojects(client, slug_a, slug_b)
    kept = link_microprojects(client, slug_b, slug_c)
    link_entities(client, entity(slug_a, exp_a), entity(slug_b, exp_b))

    assert delete_microproject(client, slug_a, "Projet A").status_code == 204
    assert microproject_links(client) == [kept]
    assert entity_links(client) == []


# Les liens d'entités tels que les écrivait le plugin avant la piste (0001_initial), recopiés plutôt
# qu'importés : une version désignée par son id, le µprojet par son slug.
LEGACY_ENTITY_LINKS = """
DROP TABLE entity_links;
CREATE TABLE entity_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    a_microproject_slug TEXT NOT NULL,
    a_experience_id TEXT NOT NULL,
    a_entity_index INTEGER NOT NULL,
    b_microproject_slug TEXT NOT NULL,
    b_experience_id TEXT NOT NULL,
    b_entity_index INTEGER NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_entity_links_a ON entity_links(a_microproject_slug);
CREATE INDEX idx_entity_links_b ON entity_links(b_microproject_slug);
DELETE FROM schema_migrations WHERE plugin = 'links' AND migration_id = '0002_entity_links_by_experiment';
"""


def _replay_migrations(data_dir, script: str, insert: str, rows: list[tuple]) -> None:
    """Ramène la base à l'état d'avant une migration (``script``), y écrit ``rows``, puis rejoue les migrations."""
    from spectre.kernel.db import run_migrations
    from spectre.plugins import PLUGINS

    conn = sqlite3.connect(data_dir / "spectre.db")
    conn.executescript(script)
    conn.executemany(insert, rows)
    conn.commit()
    conn.close()
    run_migrations(PLUGINS)


def test_legacy_entity_links_move_from_a_version_to_its_piste(client, data_dir):
    slug_a, exp_a, slug_b, exp_b = _two_tracked_studies(client, "legacy@example.com")
    old_version = launch(client, slug_a, title="Autre", intent="Depart", branch="autre")["version_id"]
    conclude(client, slug_a, "autre", decision="promote")  # old_version n'est plus la pointe de sa piste
    tip_b = tag(client, slug_b, exp_b, ["suivi"])["version_id"]
    user_id = me(client)["id"]

    insert = (
        "INSERT INTO entity_links (a_microproject_slug, a_experience_id, a_entity_index, b_microproject_slug, "
        "b_experience_id, b_entity_index, note, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
    )
    _replay_migrations(
        data_dir,
        LEGACY_ENTITY_LINKS,
        insert,
        [
            (slug_a, old_version, 0, slug_b, tip_b, 1, "par version", user_id),
            (slug_a, exp_a, 1, slug_b, tip_b, 0, "déjà par piste", user_id),
            (slug_a, "exp_0000000000000000", 0, slug_b, tip_b, 0, "version disparue", user_id),
            ("projet-supprime", "exp_0000000000000001", 0, slug_b, tip_b, 0, "µprojet disparu", user_id),
        ],
    )

    assert [(link["a"], link["b"], link["note"]) for link in entity_links(client)] == [
        (entity(slug_a, "autre", 0), entity(slug_b, exp_b, 1), "par version"),
        (entity(slug_a, exp_a, 1), entity(slug_b, exp_b, 0), "déjà par piste"),
    ]
    conn = sqlite3.connect(data_dir / "spectre.db")
    unresolved = [row[0] for row in conn.execute("SELECT note FROM entity_links_unresolved ORDER BY id")]
    conn.close()
    assert unresolved == ["version disparue", "µprojet disparu"]  # mises de côté, pas perdues


def test_duplicate_microproject_links_keep_the_oldest(client, data_dir):
    slug_a, slug_b = _two_microprojects(client, "duplicates@example.com")
    first = link_microprojects(client, slug_a, slug_b, "le premier")
    conn = sqlite3.connect(data_dir / "spectre.db")
    ids = [conn.execute("SELECT id FROM microprojects WHERE slug = ?", (slug,)).fetchone()[0] for slug in (slug_a, slug_b)]
    conn.close()

    _replay_migrations(
        data_dir,
        "DROP INDEX idx_microproject_links_pair;\nDROP TABLE microproject_links_duplicates;\n"
        "DELETE FROM schema_migrations WHERE plugin = 'links' AND migration_id = '0003_unique_microproject_pair';",
        "INSERT INTO microproject_links (microproject_a_id, microproject_b_id, note, created_by) VALUES (?, ?, ?, ?)",
        [(ids[1], ids[0], "le doublon", me(client)["id"])],
    )
    assert microproject_links(client) == [first]
    assert post_microproject_link(client, slug_b, slug_a).status_code == 409
    conn = sqlite3.connect(data_dir / "spectre.db")
    set_aside = [row[0] for row in conn.execute("SELECT note FROM microproject_links_duplicates")]
    conn.close()
    assert set_aside == ["le doublon"]  # mis de côté avec sa note, pas perdu
