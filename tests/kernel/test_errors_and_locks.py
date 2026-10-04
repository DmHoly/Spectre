"""Les erreurs du domaine deviennent une réponse en un seul endroit ; un verrou par clé."""

from __future__ import annotations

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from spectre.kernel import errors
from spectre.kernel.app import create_app
from spectre.kernel.locks import keyed_lock
from spectre.kernel.plugin import Plugin


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (errors.NotFound, 404, "not_found"),
        (errors.Forbidden, 403, "forbidden"),
        (errors.Conflict, 409, "conflict"),
        (errors.PreconditionFailed, 412, "precondition_failed"),
        (errors.InvalidInput, 422, "invalid_input"),
        (errors.UpstreamError, 502, "upstream_error"),
        (errors.Unavailable, 503, "unavailable"),
    ],
)
def test_a_domain_error_becomes_its_status_with_detail_and_code(data_dir, error, status, code):
    router = APIRouter()

    @router.get("/api/panne")
    def fail():
        raise error("lot « A » introuvable")

    with TestClient(create_app([Plugin("vitrine", router=router)])) as client:
        response = client.get("/api/panne")
    assert response.status_code == status
    assert response.json() == {"detail": "lot « A » introuvable", "code": code}


def test_a_domain_error_can_carry_its_own_code():
    assert errors.NotFound("aucun compte", code="no_account").code == "no_account"
    assert errors.NotFound("introuvable").code == "not_found"


def test_one_lock_per_key():
    assert keyed_lock("experiments", "recuit-mg") is keyed_lock("experiments", "recuit-mg")
    assert keyed_lock("experiments", "recuit-mg") is not keyed_lock("experiments", "autre")
    assert keyed_lock("experiments", "recuit-mg") is not keyed_lock("lots", "recuit-mg")
