"""Clase `BaseAgent` (Template Method) con `handle_turn`.

Los duplicados se integran en el paso 5.
"""

import logging
from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any, ClassVar, final

from ringr_agents.domain.constants import EMERGENCY_REPLY
from ringr_agents.domain.enums import ActionStatus, TurnError
from ringr_agents.domain.fields import FieldNormalizer, normalize
from ringr_agents.domain.ports import ActionSender
from ringr_agents.domain.results import TurnResult
from ringr_agents.infrastructure.models import (
    ConversationModel,
    ParserModel,
    ScriptExhaustedError,
)

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Orquesta el turno en orden fijo; las subclases solo declaran el «qué»."""

    action_name: ClassVar[str]  # un valor de ActionName
    action_url: ClassVar[str]  # la URL vive en el agente (PC-10)

    def __init__(
        self,
        conversation_model: ConversationModel,
        parser_model: ParserModel,
        sender: ActionSender,
    ) -> None:
        self._conversation_model = conversation_model
        self._parser_model = parser_model
        self._sender = sender

    @abstractmethod
    def fields(self) -> Mapping[str, FieldNormalizer]:
        """Esquema del agente: nombre de cada campo y su estrategia de normalización (PC-3)."""

    @abstractmethod
    def should_execute(self, data: Mapping[str, object | None]) -> bool:
        """Dice si, con estos datos ya normalizados, hay que ejecutar la acción (PC-2)."""

    @final  # la plantilla no se sobrescribe: los agentes solo cambian el «qué» (PC-1)
    def handle_turn(self) -> TurnResult:
        """Ejecuta un turno en orden fijo y devuelve su `TurnResult` (Template Method, PC-1).

        Orden (AMB-11): responder, parsear, normalizar, decidir, enviar y devolver.
        Si falla un modelo o el envío acaba en `FAILED`, el cliente recibe `EMERGENCY_REPLY`
        y el fallo queda en `errors` (AMB-11, PC-8). Si falla cualquier modelo no se envía
        (PC-8.2). `ScriptExhaustedError` no se captura: es un guion mal preparado (PC-8.3).
        Los duplicados se añaden en el paso 5.
        """
        errors: list[TurnError] = []

        # 1. Responder. Un fallo del modelo no deja al cliente sin respuesta (AMB-11).
        reply = EMERGENCY_REPLY  # se sustituye por la respuesta del modelo si no falla
        try:
            reply = self._conversation_model.answer_user()
        except ScriptExhaustedError:
            raise  # antes que `except Exception`, que también la atraparía (PC-8.3)
        except Exception:
            logger.exception("%s: falló answer_user", self.action_name)
            errors.append(TurnError.CONVERSATION_FAILED)

        # 2. Parsear. Se llama aunque haya fallado el paso 1, para que los dos modelos
        # sigan en el mismo turno y el resultado diga todo lo que ha fallado.
        raw: Mapping[str, Any] = {}
        try:
            parsed = self._parser_model.parse_data()
            # Un LLM puede devolver algo malformado: si no es un dict, cuenta como fallo.
            if not isinstance(parsed, Mapping):
                raise TypeError(f"parse_data devolvió {type(parsed).__name__}, no un dict")
            raw = parsed
        except ScriptExhaustedError:
            raise
        except Exception:
            logger.exception("%s: falló parse_data", self.action_name)
            errors.append(TurnError.PARSER_FAILED)

        # 3. Normalizar. No lanza: lo inválido pasa a None con un aviso (AMB-2).
        normalized = normalize(raw, self.fields())

        # 4. Decidir. Con un modelo caído no se registra nada (PC-8.2).
        if errors or not self.should_execute(normalized.data):
            return TurnResult(
                reply=EMERGENCY_REPLY if errors else reply,
                data=normalized.data,
                action_status=ActionStatus.NOT_REQUIRED,
                warnings=normalized.warnings,
                errors=tuple(errors),
            )

        # 5. Duplicados: en el paso 5.

        # 6. Enviar. `send` no lanza: un fallo llega como `ok=False` (AMB-4).
        send_result = self._sender.send(self.action_url, normalized.data)
        if send_result.ok:
            status = ActionStatus.SENT
        else:
            # El cliente no puede creer que está registrado si no lo está (PC-8).
            status = ActionStatus.FAILED
            errors.append(TurnError.SEND_FAILED)
            reply = EMERGENCY_REPLY

        # 7. Devolver.
        return TurnResult(
            reply=reply,
            data=normalized.data,
            action_status=status,
            warnings=normalized.warnings,
            errors=tuple(errors),
            send_result=send_result,
        )
