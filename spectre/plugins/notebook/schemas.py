"""Corps des requêtes du cahier de données : un instantané à prendre, une entrée à ajouter ou à
modifier. Une entrée a une seule forme pour ses deux types (``kind``) ; ce que chaque type accepte
dans une mesure, et les bornes de chaque champ, sont vérifiés par :mod:`.service`."""

from __future__ import annotations

from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, model_validator

from ...kernel.annotations import ImageAnnotation


class SnapshotRequest(BaseModel):
    hook: str  # la clé d'un type de données de caractérisation
    wafers: list[str] = []
    refresh: bool = False


class ValueInput(BaseModel):
    """Une valeur mesurée : le nombre, son unité, et au besoin le nom de la grandeur (« rugosite_rms »)."""

    number: float  # fini (vérifié par le service : une erreur de validation ne sait pas renvoyer Infinity)
    unit: str | None = None
    name: str | None = None


class TableInput(BaseModel):
    """Un tableau collé (analysé en TSV par la page) : ses colonnes, puis ses lignes, une cellule par
    colonne."""

    columns: list[str]
    rows: list[list[str | int | float | bool | None]] = []


class LinkInput(BaseModel):
    url: str  # http ou https : :func:`is_web_link`
    label: str | None = None


def is_web_link(url: str) -> bool:
    """Ce qu'un lien d'une mesure peut être : une adresse ``http`` ou ``https`` avec un hôte, sans
    espace ni caractère de contrôle, de 1000 caractères au plus - la règle des liens écrits
    aujourd'hui comme de ceux que donnent les données d'avant (:mod:`.legacy`)."""
    parts = urlsplit(url)
    return parts.scheme.lower() in ("http", "https") and bool(parts.netloc) and len(url) <= 1000 and not any(c.isspace() or ord(c) < 32 for c in url)


class AttachmentRef(BaseModel):
    """Un fichier téléversé d'abord (``POST .../attachments``, ``purpose=notebook``) : son id, ou
    ``{id, caption}`` pour lui donner une légende."""

    id: str
    caption: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _from_id(cls, value: Any) -> Any:
        return {"id": value} if isinstance(value, str) else value


class ExternalImageInput(BaseModel):
    """Une image externe (TEM, scan) référencée à son emplacement sur le disque du serveur, sans être
    copiée : son chemin absolu, sous un dossier autorisé (plugin external_images), et une légende."""

    path: str
    caption: str | None = None


class AnnotationInput(ImageAnnotation):
    """Une flèche ou un cadre (la forme de :class:`spectre.kernel.annotations.ImageAnnotation`) posé
    sur une image de la mesure, désignée par une clé qui ne bouge pas quand on réordonne ses images :
    un fichier téléversé (``attachment_id``) ou une image externe (``external_image`` : son chemin,
    unique dans la mesure) - l'un ou l'autre."""

    model_config = ConfigDict(extra="ignore")

    attachment_id: str | None = None
    external_image: str | None = None

    @model_validator(mode="after")
    def _one_image(self) -> "AnnotationInput":
        if (self.attachment_id is None) == (self.external_image is None):
            raise ValueError("Une annotation désigne une image : attachment_id (un fichier) ou external_image (une image externe).")
        return self


class MeasurementInput(BaseModel):
    """Une mesure de l'entrée, à une étape du procédé (``step_id``, ``None`` : non située). Une
    entrée PRISM y met une vue d'un instantané (``snapshot_id``, ``component``, ``options``) ; une
    entrée manuelle, au choix, une valeur, un texte, un tableau, des fichiers, des images externes,
    les annotations de ses images (fichiers et images externes) et des liens - et le dossier d'images
    qu'on y a pointé (``image_folder`` : on en épingle des images externes, et on le rouvre)."""

    step_id: str | None = None
    snapshot_id: str | None = None
    component: str | None = None
    options: dict[str, Any] | None = None
    value: ValueInput | None = None
    text: str | None = None
    table: TableInput | None = None
    attachments: list[AttachmentRef] = []
    external_images: list[ExternalImageInput] = []
    image_folder: str | None = None
    links: list[LinkInput] = []
    annotations: list[AnnotationInput] = []


class EntryInput(BaseModel):
    kind: Literal["prism", "manual"]
    title: str
    note: str | None = None
    objective: str | None = None
    interpretation: str | None = None
    wafers: list[str] = []  # les plaques mesurées (clés de wafer) ; vide : toute la piste
    measurements: list[MeasurementInput]
    in_report: bool = True


class EntryUpdate(BaseModel):
    """Lu avec ``exclude_unset`` : seuls les champs envoyés changent (``objective`` vide ou nul :
    plus d'objectif ; ``measurements`` remplace toutes les mesures). Le type d'une entrée ne change
    pas."""

    title: str | None = None
    note: str | None = None
    objective: str | None = None
    interpretation: str | None = None
    wafers: list[str] | None = None
    measurements: list[MeasurementInput] | None = None
    in_report: bool | None = None
    position: int | None = None  # la place de l'entrée dans le cahier, à partir de 0
