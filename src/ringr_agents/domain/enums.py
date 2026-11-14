"""Vocabulario del dominio (StrEnum): `ActionStatus`, `TurnError`, `FieldName` y `ActionName`.

Al ser `StrEnum`, cada miembro es a la vez una cadena: `FieldName.REQUEST == "request"`. Por eso
sirven como clave del dict del parser, como nombre de cabecera y como texto en el log.
"""

from enum import StrEnum, auto


class ActionStatus(StrEnum):
    """Qué pasó con la acción en el turno (AMB-5)."""

    NOT_REQUIRED = auto()
    DUPLICATE = auto()
    SENT = auto()
    FAILED = auto()


class TurnError(StrEnum):
    """Qué falló en el turno. Si falla un modelo, el estado sigue siendo `NOT_REQUIRED`."""

    CONVERSATION_FAILED = auto()
    PARSER_FAILED = auto()
    SEND_FAILED = auto()


class FieldName(StrEnum):
    """Nombres de los campos: claves del parser, cabeceras y body (nombres del enunciado)."""

    COMMITMENT_DATE = "commitment_date"
    COMMITTED_AMOUNT = "committed_amount"
    REQUEST = "request"


class ActionName(StrEnum):
    """Nombre de la acción de cada agente, para la huella de duplicados y el log (ENUM-2)."""

    REGISTER_COMMITMENT = "register_commitment"
    REGISTER_REQUEST = "register_request"
