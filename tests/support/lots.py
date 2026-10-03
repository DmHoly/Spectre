"""Lots de fabrication (plugin lots) : chaque aide encapsule une route et vérifie son code de
succès. Un lot est désigné par son id ; :func:`find_lot` le retrouve par son code."""

from __future__ import annotations

from typing import Any

from .http import assert_created, assert_ok


def lot_url(lot_id: int) -> str:
    return f"/api/lots/{lot_id}"


def create_lot(client: Any, code: str | None = None, **fields: Any) -> dict:
    """Un lot (``title``, ``priority``, ``wafers``, ``started_on``, ``thematic_ids``...) - sans
    ``code``, le suivant de la numérotation LOT-0001. Renvoie le lot créé."""
    body = {**({"code": code} if code else {}), **fields}
    response = client.post("/api/lots", json=body)
    lot = assert_created(response)
    assert response.headers["Location"] == lot_url(lot["id"])
    return lot


def list_lots(client: Any, **params: Any) -> list[dict]:
    """GET /api/lots (``status``, ``q``, ``wafer``, ``code``, ``view``)."""
    return assert_ok(client.get("/api/lots", params=params))


def find_lot(client: Any, code: str) -> dict:
    """Le lot de code ``code`` (sans la casse), comme la page ``/lots/{code}`` le résout."""
    found = list_lots(client, code=code)
    assert len(found) == 1, f"{len(found)} lot(s) de code {code!r}"
    return found[0]


def get_lot(client: Any, lot_id: int) -> dict:
    return assert_ok(client.get(lot_url(lot_id)))


def patch_lot(client: Any, lot_id: int, *, if_match: str | None = None, **fields: Any) -> Any:
    """PATCH /api/lots/{lot_id}, tel quel (la réponse, pour en vérifier un refus)."""
    headers = {"If-Match": f'"{if_match}"'} if if_match else {}
    return client.patch(lot_url(lot_id), json=fields, headers=headers)


def update_lot(client: Any, lot_id: int, *, if_match: str | None = None, **fields: Any) -> dict:
    """Modifie les champs ``fields`` du lot (les autres restent) - renvoie le lot."""
    return assert_ok(patch_lot(client, lot_id, if_match=if_match, **fields))


def add_wafers(client: Any, lot_id: int, lasermarks: list[str]) -> dict:
    """Ajoute des wafers (au moins un nouveau) - renvoie le lot."""
    return assert_created(client.post(f"{lot_url(lot_id)}/wafers", json={"lasermarks": lasermarks}))


def remove_wafer(client: Any, lot_id: int, wafer_key: str) -> None:
    response = client.delete(f"{lot_url(lot_id)}/wafers/{wafer_key}")
    assert response.status_code == 204, f"{response.status_code} au lieu de 204 : {response.text}"


def set_thematics(client: Any, lot_id: int, thematic_ids: list[int]) -> dict:
    return assert_ok(client.put(f"{lot_url(lot_id)}/thematics", json={"thematic_ids": thematic_ids}))


def delete_lot(client: Any, lot_id: int) -> None:
    response = client.delete(lot_url(lot_id))
    assert response.status_code == 204, f"{response.status_code} au lieu de 204 : {response.text}"
