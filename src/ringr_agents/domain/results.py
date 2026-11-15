"""Objetos de resultado (DTO): `SendResult` (paso 3) y `TurnResult` (paso 4)."""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from ringr_agents.domain.enums import ActionStatus, TurnError


@dataclass(frozen=True)
class SendResult:
    """Resultado de un envío. Solo tipos simples, para que el dominio no dependa de HTTP."""

    ok: bool
    attempts: int
    status_code: int | None  # None si no hubo respuesta (error de transporte)
    idempotency_key: str  # para enlazar el turno con la request en el log


@dataclass(frozen=True)
class TurnResult:
    """Resultado de un turno: lo que ve el usuario y lo que pasó con la acción."""

    reply: str
    data: Mapping[str, object | None]  # normalizados; claves = valores de FieldName
    action_status: ActionStatus
    warnings: tuple[str, ...] = ()  # datos descartados (AMB-2)
    errors: tuple[TurnError, ...] = ()
    send_result: SendResult | None = None  # detalle del envío (intentos incluidos), si lo hubo

    def __post_init__(self) -> None:
        # `frozen` impide cambiar los atributos, pero no el dict de dentro: se guarda una
        # copia de solo lectura para que el resultado sea inmutable de verdad.
        object.__setattr__(self, "data", MappingProxyType(dict(self.data)))
