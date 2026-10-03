"""Galerie d'images externes (plugin external_images) : les jeux d'images d'une étude et le parcours
des dossiers autorisés. Les aides ``post_*``, ``patch_*``, ``delete_*`` et ``browse`` renvoient la
réponse telle quelle (pour en vérifier un refus) ; les autres vérifient leur code de succès.
``if_match`` envoie l'en-tête ``If-Match``."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .http import PNG_1PX, assert_created, assert_ok


def image_sets_url(slug: str, experiment_id: str) -> str:
    return f"/api/microprojects/{slug}/experiments/{experiment_id}/image-sets"


def _headers(if_match: str | None) -> dict:
    return {"If-Match": f'"{if_match}"'} if if_match else {}


def png_files(directory: Path, *names: str) -> list[str]:
    """De vraies images PNG écrites dans ``directory`` - leurs chemins absolus."""
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    for name in names or ("tem-1.png", "tem-2.png"):
        (directory / name).write_bytes(PNG_1PX)
        paths.append(str(directory / name))
    return paths


def image_sets(client: Any, slug: str, experiment_id: str, version: str | None = None) -> list[dict]:
    """Les jeux d'images (de la pointe, ou de ``version``)."""
    return assert_ok(client.get(image_sets_url(slug, experiment_id), params={"version": version} if version else {}))


def post_image_set(client: Any, slug: str, experiment_id: str, image_paths: list[str], *, if_match: str | None = None, **fields: Any) -> Any:
    return client.post(image_sets_url(slug, experiment_id), json={"image_paths": image_paths, **fields}, headers=_headers(if_match))


def create_image_set(client: Any, slug: str, experiment_id: str, image_paths: list[str], *, if_match: str | None = None, **fields: Any) -> dict:
    """POST /image-sets - renvoie le jeu créé (``title``, ``note``, ``entity_index``, ``pinned_index``)."""
    return assert_created(post_image_set(client, slug, experiment_id, image_paths, if_match=if_match, **fields))


def patch_image_set(client: Any, slug: str, experiment_id: str, set_id: str, pinned_index: int, *, if_match: str | None = None) -> Any:
    return client.patch(f"{image_sets_url(slug, experiment_id)}/{set_id}", json={"pinned_index": pinned_index}, headers=_headers(if_match))


def pin_image(client: Any, slug: str, experiment_id: str, set_id: str, pinned_index: int, *, if_match: str | None = None) -> dict:
    """PATCH /image-sets/{set_id} : épingle une autre image du jeu - renvoie le jeu."""
    return assert_ok(patch_image_set(client, slug, experiment_id, set_id, pinned_index, if_match=if_match))


def delete_image_set(client: Any, slug: str, experiment_id: str, set_id: str, *, if_match: str | None = None) -> Any:
    return client.delete(f"{image_sets_url(slug, experiment_id)}/{set_id}", headers=_headers(if_match))


def get_image(client: Any, slug: str, experiment_id: str, set_id: str, index: int, **params: Any) -> Any:
    return client.get(f"{image_sets_url(slug, experiment_id)}/{set_id}/images/{index}", params=params)


def browse(client: Any, slug: str, directory: str) -> Any:
    """GET /external-images?directory= (la réponse)."""
    return client.get(f"/api/microprojects/{slug}/external-images", params={"directory": directory})
