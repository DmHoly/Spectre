"""La source PRISM (paquet ``prism-aledia-datahook``, voir
https://gitlab-it.aledia.com/sda/tools/soft/prism) : le seul module de Spectre qui importe ``prism``.

Spectre ne porte aucune requête ni formule KPI : tout vit dans PRISM, partagé avec les autres
projets. PRISM parle à de vraies bases externes (profils de ``~/.prism/connections.yml``) : les
erreurs de configuration, de connexion ou de requête sont attendues et deviennent des erreurs du
domaine lisibles (503 configuration absente, 502 base injoignable ou requête en échec) plutôt
qu'une trace brute.
"""

from __future__ import annotations

import logging
from typing import Any

import prism

from ...kernel.errors import NotFound, Unavailable, UpstreamError
from .source import WAFER_PARAMETER, DataType, QueryResult, json_safe

logger = logging.getLogger(__name__)


def _column(col: prism.ColumnDoc) -> dict[str, Any]:
    return {
        "name": col.name,
        "description": col.description,
        "example": json_safe(col.example),
        "source": col.source,
        "formula": col.formula,
        "unit": col.unit,
    }


def _data_type(hook: prism.DataHook) -> DataType:
    return DataType(
        key=hook.key,
        title=hook.title,
        description=hook.description,
        category=hook.category,
        status=hook.status,
        parameters=tuple(hook.parameters),
        cacheable=bool(hook.cache_key_column) and WAFER_PARAMETER in hook.parameters,
        postprocessing=tuple(hook.postprocessing),
        raw_columns=tuple(_column(c) for c in hook.raw_columns),
        kpi_columns=tuple(_column(c) for c in hook.kpi_columns),
        example_rows=tuple(json_safe(row) for row in hook.example_rows),
        representative_column=hook.representative_column,
        charts=tuple({"key": c.key, "title": c.title, "description": c.description} for c in hook.charts),
    )


class PrismSource:
    name = "prism"

    def list_types(self) -> list[DataType]:
        """Tout le catalogue, implémenté ou non. Une fiche invalide est écartée et journalisée : elle
        ne doit pas priver la page de toutes les autres."""
        types = []
        for key in prism.list_hooks():
            try:
                types.append(_data_type(prism.load_hook(key)))
            except prism.PrismError as exc:
                logger.warning("type de données %r écarté du catalogue : hook.yml invalide (%s)", key, exc)
        return types

    def describe(self, key: str) -> DataType:
        try:
            return _data_type(prism.load_hook(key))
        except prism.HookNotFoundError as exc:
            raise NotFound(f"type de données inconnu : {key}") from exc
        except prism.HookDefinitionError as exc:
            raise UpstreamError(f"la fiche PRISM de « {key} » est invalide : {exc}") from exc

    def query(self, key: str, parameters: dict[str, list[str]], *, refresh: bool = False) -> QueryResult:
        data_type = self.describe(key)
        from_cache = fetched = None
        try:
            if data_type.cacheable:
                result = prism.run_hook_cached(key, wafer_names=parameters[WAFER_PARAMETER], refresh=refresh)
                df, from_cache, fetched = result.df, result.from_cache, result.fetched
            else:
                df = prism.run_hook(key, **parameters)
        except prism.ConfigError as exc:
            raise Unavailable(f"configuration de connexion PRISM incomplète : {exc}") from exc
        except prism.HookDefinitionError as exc:
            raise UpstreamError(f"la fiche PRISM de « {key} » est invalide : {exc}") from exc
        except Exception as exc:  # base injoignable, requête ou post-traitement en échec
            logger.warning("type de données %r : requête PRISM en échec (%s)", key, exc)
            raise UpstreamError(f"la requête PRISM a échoué : {exc}") from exc
        columns = [str(c) for c in df.columns]
        rows = [[json_safe(v) for v in row] for row in df.itertuples(index=False, name=None)]
        return QueryResult(source=self.name, columns=columns, rows=rows, from_cache=from_cache, fetched=fetched)

    def chart(self, key: str, chart_key: str) -> bytes:
        """Un graphique documentaire, toujours dessiné sur l'exemple figé de la fiche
        (``charts[].example``), jamais sur une vraie requête."""
        if not any(c["key"] == chart_key for c in self.describe(key).charts):
            raise NotFound(f"graphique inconnu pour « {key} » : {chart_key}")
        try:
            return prism.render_chart(key, chart_key)
        except Exception as exc:
            logger.warning("type de données %r : échec du graphique %r (%s)", key, chart_key, exc)
            raise UpstreamError(f"le graphique a échoué : {exc}") from exc
