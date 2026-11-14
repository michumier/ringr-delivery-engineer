"""Estrategias concretas: `TextField`, `DateField` y `AmountField` (reglas de AMB-2 y AMB-3)."""

import math
import re
from collections.abc import Callable
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from ringr_agents.domain.fields.base import InvalidFieldError

# `fromisoformat` de Python 3.11 acepta también "20261201" y "2026-W49-2"; aquí solo AAAA-MM-DD.
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}", re.ASCII)
# Un solo separador (punto o coma) y 2 cifras decimales como máximo: "1.500,50" y "1,500" no casan
# a propósito, porque son ambiguos y no se adivina (AMB-3).
_AMOUNT = re.compile(r"[+-]?\d+(?:[.,]\d{1,2})?", re.ASCII)
_CENTS = Decimal("0.01")


def _clean_text(raw: object, kind: str) -> str | None:
    """Quita espacios; `None` y el texto vacío dan `None`; lo que no es texto es inválido."""
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise InvalidFieldError(f"se esperaba texto para {kind} y llegó {type(raw).__name__}")
    return raw.strip() or None


class TextField:
    """Texto libre: sin espacios sobrantes; vacío -> `None`."""

    def normalize(self, raw: object) -> str | None:
        return _clean_text(raw, "el texto")


class DateField:
    """Fecha ISO (AAAA-MM-DD) que no sea pasada; la de hoy vale (AMB-3)."""

    def __init__(self, today: Callable[[], date] = date.today) -> None:
        # «Hoy» se inyecta para poder probar el borde sin depender del reloj (PC-4).
        self._today = today

    def normalize(self, raw: object) -> str | None:
        text = _clean_text(raw, "la fecha")
        if text is None:
            return None
        if not _ISO_DATE.fullmatch(text):
            raise InvalidFieldError("la fecha debe tener el formato AAAA-MM-DD")
        try:
            parsed = date.fromisoformat(text)
        except ValueError as exc:
            raise InvalidFieldError("la fecha no existe en el calendario") from exc
        if parsed < self._today():
            raise InvalidFieldError("la fecha es pasada")
        return parsed.isoformat()


class AmountField:
    """Importe mayor que 0, redondeado a céntimos y devuelto como `float` (AMB-2, AMB-3, PC-11)."""

    def normalize(self, raw: object) -> float | None:
        amount = self._to_decimal(raw)
        if amount is None:
            return None
        # ROUND_HALF_UP con Decimal: `round()` sobre float da 2.67 para 2.675.
        rounded = amount.quantize(_CENTS, rounding=ROUND_HALF_UP)
        if rounded <= 0:
            raise InvalidFieldError("el importe debe ser mayor que 0")
        return float(rounded)

    @staticmethod
    def _to_decimal(raw: object) -> Decimal | None:
        if raw is None:
            return None
        # `bool` es subclase de `int`: sin esta comprobación `True` valdría 1 euro.
        if isinstance(raw, bool):
            raise InvalidFieldError("un booleano no es un importe")
        if isinstance(raw, int):
            return Decimal(raw)
        if isinstance(raw, float):
            if not math.isfinite(raw):
                raise InvalidFieldError("el importe debe ser un número finito")
            # `str(float)` da la forma corta (2.675) en vez de la binaria exacta (2.67499...).
            return Decimal(str(raw))
        if isinstance(raw, str):
            text = raw.strip()
            if not text:
                return None
            if not _AMOUNT.fullmatch(text):
                raise InvalidFieldError(
                    "el importe en texto no tiene un formato válido o es ambiguo"
                )
            return Decimal(text.replace(",", "."))
        raise InvalidFieldError(f"tipo no válido para un importe: {type(raw).__name__}")
