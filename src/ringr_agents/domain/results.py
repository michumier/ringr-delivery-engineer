"""Objetos de resultado (DTO): `SendResult` (paso 3) y `TurnResult` (paso 4)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SendResult:
    """Resultado de un envío. Solo tipos simples, para que el dominio no dependa de HTTP."""

    ok: bool
    attempts: int
    status_code: int | None  # None si no hubo respuesta (error de transporte)
    idempotency_key: str  # para enlazar el turno con la request en el log
