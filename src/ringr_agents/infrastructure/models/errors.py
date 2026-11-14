"""Excepción `ScriptExhaustedError`, cuando un guion simulado se agota."""


class ScriptExhaustedError(Exception):
    """Se pidió un turno más de los que tiene el guion.

    Indica un test o una demo mal preparados, así que `handle_turn` no la captura (PC-8.3).
    """
