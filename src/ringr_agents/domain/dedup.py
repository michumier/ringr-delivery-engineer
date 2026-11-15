"""Control de duplicados: `fingerprint` y `SentActionRegistry` (PC-5, AMB-1)."""

from collections.abc import Mapping

# La acción y sus datos como tupla: así se puede comparar y guardar en un `set`.
Fingerprint = tuple[str, tuple[tuple[str, object], ...]]


def fingerprint(action_name: str, data: Mapping[str, object | None]) -> Fingerprint:
    """Huella de una acción: su nombre y sus datos ya normalizados (AMB-1).

    Los campos se ordenan por nombre para que el orden del diccionario no cambie la huella.
    Como los datos ya están limpios, `"150"` y `150` dan la misma huella (los dos son `150.0`).
    """
    return (str(action_name), tuple(sorted((str(name), value) for name, value in data.items())))


class SentActionRegistry:
    """Huellas de lo ya enviado con éxito en una conversación (un registro por agente).

    Guarda todo lo enviado, no solo lo último (PC-5.2): volver a un compromiso anterior
    (A → B → A) no se reenvía. Está en memoria; uno persistente cumpliría la misma interfaz.
    """

    def __init__(self) -> None:
        self._sent: set[Fingerprint] = set()

    def was_sent(self, fp: Fingerprint) -> bool:
        """Dice si esta huella ya se envió con éxito."""
        return fp in self._sent

    def mark_sent(self, fp: Fingerprint) -> None:
        """Apunta la huella. Solo se llama tras un envío correcto: un `FAILED` no cuenta."""
        self._sent.add(fp)
