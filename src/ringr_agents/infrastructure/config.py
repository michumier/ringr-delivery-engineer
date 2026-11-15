"""Configuración: `Settings` y `Settings.from_env()` (token y reintentos)."""

import math
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import TypeVar

Number = TypeVar("Number", int, float)

# Token de pruebas del enunciado: solo es el valor por defecto si no hay variable (PC-10).
DEFAULT_API_TOKEN = "ringr_test_token_9f3a2c1d"


class ConfigError(ValueError):
    """Una variable de entorno tiene un valor que no se puede usar."""


@dataclass(frozen=True)
class Settings:
    """Lo que cambia entre entornos. Solo lo usa la raíz de composición."""

    # Fuera del repr: el token no debe salir si se imprime la configuración (PC-10).
    api_token: str = field(default=DEFAULT_API_TOKEN, repr=False)
    max_attempts: int = 3
    base_delay: float = 0.2

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        """Lee `RINGR_API_TOKEN`, `RINGR_MAX_ATTEMPTS` y `RINGR_RETRY_BASE_DELAY`.

        Lo que falte toma su valor por defecto. Un número inválido lanza `ConfigError`.
        """
        env = os.environ if env is None else env
        defaults = cls()
        max_attempts = _read_number(env, "RINGR_MAX_ATTEMPTS", int, defaults.max_attempts)
        base_delay = _read_number(env, "RINGR_RETRY_BASE_DELAY", float, defaults.base_delay)
        if max_attempts < 1:
            raise ConfigError(f"RINGR_MAX_ATTEMPTS debe ser al menos 1, no {max_attempts}")
        if base_delay < 0:
            raise ConfigError(f"RINGR_RETRY_BASE_DELAY no puede ser negativo, no {base_delay}")
        return cls(
            api_token=(env.get("RINGR_API_TOKEN") or "").strip() or defaults.api_token,
            max_attempts=max_attempts,
            base_delay=base_delay,
        )


def _read_number(
    env: Mapping[str, str], name: str, convert: Callable[[str], Number], default: Number
) -> Number:
    raw = env.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = convert(raw)
    except ValueError:
        raise ConfigError(f"{name} debe ser un número válido, no {raw!r}") from None
    # float() acepta "nan" e "inf" sin error, pero no sirven como espera ni como retardo.
    if not math.isfinite(value):
        raise ConfigError(f"{name} debe ser un número finito, no {raw!r}")
    return value
