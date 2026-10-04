"""Corps des requêtes du cahier de données : un instantané à prendre, une entrée à ajouter ou à
modifier. Une entrée a une seule forme pour ses deux types (``kind``) ; ce que chaque type accepte
dans une mesure, et les bornes de chaque champ, sont vérifiés par :mod:`.service`."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, model_validator


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
    url: str  # http ou https
    label: str | None = None


class AttachmentRef(BaseModel):
    """Un fichier téléversé d'abord (``POST .../attachments``, ``purpose=notebook``) : son id, ou
    ``{id, caption}`` pour lui donner une légende."""

    id: str
    caption: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _from_id(cls, value: Any) -> Any:
        return {"id": value} if isinstance(value, str) else value


class AnnotationInput(BaseModel):
    """Une flèche ou un cadre posé sur une image de la mesure, en % de l'image."""

    attachment_id: str
    type: Literal["arrow", "box"]
    x: float
    y: float
    x2: float | None = None
    y2: float | None = None
    label: str | None = None


class MeasurementInput(BaseModel):
    """Une mesure de l'entrée, à une étape du procédé (``step_id``, ``None`` : non située). Une
    entrée PRISM y met une vue d'un instantané (``snapshot_id``, ``component``, ``options``) ; une
    entrée manuelle, au choix, une valeur, un texte, un tableau, des fichiers (et leurs
    annotations) et des liens."""

    step_id: str | None = None
    snapshot_id: str | None = None
    component: str | None = None
    options: dict[str, Any] | None = None
    value: ValueInput | None = None
    text: str | None = None
    table: TableInput | None = None
    attachments: list[AttachmentRef] = []
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
