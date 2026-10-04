"""Assertions sur les réponses HTTP, indépendantes de toute route."""

from __future__ import annotations

from typing import Any

# Un PNG 1x1 valide (vrais octets magiques - aucune route ne les inspecte, elles se fient au type
# annoncé par le navigateur) : de quoi envoyer une image ou une pièce jointe.
PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753"
    "de000000097048597300000b1300000b1301009a9c1800000010494441545805"
    "0763f8ffff3f0005fe02fea739667e0000000049454e44ae426082"
)

# Le detail du 404 que Starlette renvoie quand aucune route ne correspond à l'URL.
ROUTER_NOT_FOUND = "Not Found"


def assert_handler_404(response: Any, detail: str | None = None) -> None:
    """Un 404 levé par le handler (une ressource introuvable), pas le 404 générique du routeur :
    après un renommage de route, une URL restée à l'ancienne répond aussi 404, et un simple
    ``status_code == 404`` passerait alors pour une mauvaise raison. ``detail``, si donné, doit
    figurer dans le message."""
    assert response.status_code == 404, f"{response.status_code} au lieu de 404 : {response.text}"
    message = response.json().get("detail")
    assert message != ROUTER_NOT_FOUND, f"aucune route ne correspond à {response.request.method} {response.request.url.path}"
    if detail is not None:
        assert detail in str(message), message


def assert_created(response: Any) -> Any:
    assert response.status_code == 201, f"{response.status_code} au lieu de 201 : {response.text}"
    return response.json()


def assert_ok(response: Any) -> Any:
    assert response.status_code == 200, f"{response.status_code} au lieu de 200 : {response.text}"
    return response.json()
