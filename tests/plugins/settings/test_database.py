"""Paramètres > Base de données : un administrateur télécharge le ZIP de tout le dossier de données
et explore les tables SQL - recherche, tri, modification d'une ligne, suppression (les clés
étrangères suivent le schéma) ; colonnes secrètes masquées, tables du noyau en lecture seule ; le
tout réservé aux administrateurs."""

from __future__ import annotations

import io
import json
import sqlite3
import zipfile

from support.accounts import login, signup
from support.microprojects import create_microproject


def _admin(client) -> dict:
    return signup(client, "boss@example.com", name="Boss")  # le premier compte est administrateur


def _rows(client, table: str, **params) -> dict:
    response = client.get(f"/api/database/tables/{table}/rows", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_the_backup_is_a_zip_of_the_database_and_the_data_files(client, data_dir):
    _admin(client)
    create_microproject(client, "Projet zip")
    attachment = data_dir / "microprojects" / "projet-zip" / "note.txt"
    attachment.parent.mkdir(parents=True, exist_ok=True)
    attachment.write_text("un fichier du µprojet")
    (data_dir / "backups").mkdir(exist_ok=True)
    (data_dir / "backups" / "old.db").write_text("ancienne copie")

    summary = client.get("/api/database").json()
    assert summary["database_bytes"] > 0 and summary["files"] >= 1

    response = client.get("/api/database/backup")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "spectre-" in response.headers["content-disposition"]
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    names = archive.namelist()
    assert "spectre.db" in names and "manifest.json" in names
    assert not any(name.startswith("backups/") for name in names)
    assert any(name.startswith("microprojects/") for name in names)
    manifest = json.loads(archive.read("manifest.json"))
    assert manifest["files"] == len(names) - 1

    copy = data_dir / "restored.db"
    copy.write_bytes(archive.read("spectre.db"))
    conn = sqlite3.connect(copy)
    try:
        assert conn.execute("SELECT name FROM microprojects").fetchone() == ("Projet zip",)
    finally:
        conn.close()


def test_the_tables_are_listed_with_their_counts_and_read_only_ones(client):
    _admin(client)
    tables = {table["name"]: table for table in client.get("/api/database/tables").json()}
    assert tables["users"]["rows"] == 1 and tables["users"]["editable"]
    assert not tables["schema_migrations"]["editable"] and not tables["plugin_states"]["editable"]
    assert not any(name.startswith("sqlite_") for name in tables)


def test_rows_are_searched_sorted_paged_and_secrets_masked(client):
    _admin(client)
    for name in ("alice", "bob", "carol"):
        signup(client, f"{name}@example.com", name=name.capitalize())
    login(client, "boss@example.com")

    page = _rows(client, "users", limit=2)
    assert page["total"] == 4 and len(page["items"]) == 2
    columns = {column["name"]: column for column in page["columns"]}
    assert columns["password_hash"]["secret"] and columns["salt"]["secret"] and columns["id"]["primary_key"]
    assert all(item["values"]["password_hash"] == "••••••" for item in page["items"])

    found = _rows(client, "users", q="ALICE")
    assert [item["values"]["email"] for item in found["items"]] == ["alice@example.com"]
    assert _rows(client, "users", q="%")["total"] == 0  # un joker est cherché tel quel

    ordered = _rows(client, "users", sort="name", desc="true")
    assert [item["values"]["name"] for item in ordered["items"]] == ["Carol", "Boss", "Bob", "Alice"]
    assert client.get("/api/database/tables/users/rows", params={"sort": "nope"}).status_code == 422
    assert client.get("/api/database/tables/nope/rows").status_code == 404

    memberships = _rows(client, "memberships")
    assert {column["name"]: column["references"] for column in memberships["columns"]}["user_id"] == "users.id"


def test_an_admin_edits_and_deletes_a_row(client):
    _admin(client)
    bob = signup(client, "bob@example.com", name="Bob")
    login(client, "boss@example.com")

    edited = client.patch(f"/api/database/tables/users/rows/{bob['id']}", json={"values": {"name": "Robert"}})
    assert edited.status_code == 200 and edited.json()["values"]["name"] == "Robert"
    assert client.get("/api/users/me").json()["name"] == "Boss"

    refused = client.patch(f"/api/database/tables/users/rows/{bob['id']}", json={"values": {"password_hash": "x"}})
    assert (refused.status_code, refused.json()["code"]) == (422, "secret_column")
    duplicate = client.patch(f"/api/database/tables/users/rows/{bob['id']}", json={"values": {"email": "boss@example.com"}})
    assert (duplicate.status_code, duplicate.json()["code"]) == (409, "integrity_error")
    unknown = client.patch(f"/api/database/tables/users/rows/{bob['id']}", json={"values": {"nope": 1}})
    assert unknown.status_code == 422
    assert client.patch("/api/database/tables/users/rows/999", json={"values": {"name": "X"}}).status_code == 404

    read_only = client.delete("/api/database/tables/schema_migrations/rows/1")
    assert (read_only.status_code, read_only.json()["code"]) == (409, "read_only_table")

    assert client.delete(f"/api/database/tables/users/rows/{bob['id']}").status_code == 204
    assert [item["values"]["email"] for item in _rows(client, "users")["items"]] == ["boss@example.com"]


def test_a_delete_follows_the_foreign_keys_of_the_schema(client):
    _admin(client)
    microproject = create_microproject(client, "Projet cascade")
    row = _rows(client, "microprojects", q="Projet cascade")["items"][0]
    assert _rows(client, "memberships")["total"] == 1
    assert client.delete(f"/api/database/tables/microprojects/rows/{row['rowid']}").status_code == 204
    assert _rows(client, "memberships")["total"] == 0  # ON DELETE CASCADE
    assert client.get(f"/api/microprojects/{microproject['slug']}").status_code == 404


def test_the_database_is_reserved_to_admins(client):
    _admin(client)
    signup(client, "user@example.com")
    for method, path in (
        ("GET", "/api/database"),
        ("GET", "/api/database/backup"),
        ("GET", "/api/database/tables"),
        ("GET", "/api/database/tables/users/rows"),
        ("PATCH", "/api/database/tables/users/rows/1"),
        ("DELETE", "/api/database/tables/users/rows/1"),
    ):
        response = client.request(method, path, json={"values": {"name": "x"}} if method == "PATCH" else None)
        assert response.status_code == 403, f"{method} {path}"


def test_the_settings_gear_and_the_database_page(client):
    _admin(client)
    page = client.get("/parametres/base-de-donnees")
    assert page.status_code == 200 and "settings/database.js" in page.text
    assert 'class="topbar__icon-btn topbar__tool"' in page.text and 'aria-label="Paramètres"' in page.text
    assert 'class="topbar__link" data-match="^/parametres"' not in page.text  # plus dans la navigation texte
