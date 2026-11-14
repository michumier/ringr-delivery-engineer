"""Función `normalize` y su resultado `Normalized`."""

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ringr_agents.domain.fields.base import FieldNormalizer, InvalidFieldError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Normalized:
    """Datos limpios (solo las claves que declara el agente) y avisos de lo descartado."""

    data: dict[str, object | None]
    warnings: tuple[str, ...]


def normalize(raw: Mapping[str, Any], fields: Mapping[str, FieldNormalizer]) -> Normalized:
    """Aplica a cada campo declarado su estrategia (AMB-2).

    Las claves que faltan cuentan como `None`, las que sobran se ignoran y un valor inválido
    pasa a `None` con un aviso (en el resultado y en el log); el turno sigue.
    """
    data: dict[str, object | None] = {}
    warnings: list[str] = []
    for name, normalizer in fields.items():
        try:
            data[name] = normalizer.normalize(raw.get(name))
        except InvalidFieldError as exc:
            data[name] = None
            warning = f"Campo '{name}' descartado: {exc}"
            warnings.append(warning)
            logger.warning(warning)
    return Normalized(data=data, warnings=tuple(warnings))
