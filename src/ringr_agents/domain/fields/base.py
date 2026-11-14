"""Base de los normalizadores: `FieldNormalizer` e `InvalidFieldError`."""

from typing import Protocol


class InvalidFieldError(ValueError):
    """El valor no se puede normalizar; el mensaje explica el motivo."""


class FieldNormalizer(Protocol):
    """Algo que sabe limpiar un campo (Strategy, PC-3)."""

    def normalize(self, raw: object) -> object | None:
        """Devuelve el valor limpio, `None` si está vacío o lanza `InvalidFieldError`."""
        ...
