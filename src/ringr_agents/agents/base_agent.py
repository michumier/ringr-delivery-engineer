"""Clase `BaseAgent` (Template Method) con `handle_turn`."""

import logging
from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any, ClassVar, final

from ringr_agents.domain.constants import EMERGENCY_REPLY
from ringr_agents.domain.dedup import SentActionRegistry, fingerprint
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
        registry: SentActionRegistry | None = None,
    ) -> None:
        self._conversation_model = conversation_model
        self._parser_model = parser_model
        self._sender = sender
        # Opcional (PC-9): por defecto, uno nuevo y vacío por agente, es decir, por conversación.
        self._registry = registry if registry is not None else SentActionRegistry()

    @abstractmethod
    def fields(self) -> Mapping[str, FieldNormalizer]:
        """Esquema del agente: nombre de cada campo y su estrategia de normalización (PC-3)."""

    @abstractmethod
    def should_execute(self, data: Mapping[str, object | None]) -> bool:
        """Dice si, con estos datos ya normalizados, hay que ejecutar la acción (PC-2)."""

    @final  # la plantilla no se sobrescribe: los agentes solo cambian el «qué» (PC-1)
    def handle_turn(self) -> TurnResult:
        """Ejecuta un turno en orden fijo y devuelve su `TurnResult` (Template Method, PC-1).

        Orden (AMB-11): responder, parsear, normalizar, decidir, duplicados, enviar y devolver.
        Si falla un modelo o el envío acaba en `FAILED`, el cliente recibe `EMERGENCY_REPLY`
        y el fallo queda en `errors` (AMB-11, PC-8). Si falla cualquier modelo no se envía
        (PC-8.2). `ScriptExhaustedError` no se captura: es un guion mal preparado (PC-8.3).
        Lo ya enviado con éxito en la conversación no se reenvía: queda `DUPLICATE` (AMB-1).
        """
        logger.info("%s: empieza el turno", self.action_name)
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
            self._log_not_executed(bool(errors), normalized.data)
            return TurnResult(
                reply=EMERGENCY_REPLY if errors else reply,
                data=normalized.data,
                action_status=ActionStatus.NOT_REQUIRED,
                warnings=normalized.warnings,
                errors=tuple(errors),
            )

        # 5. Duplicados. La misma acción con los mismos datos limpios ya se envió: no se repite,
        # y el cliente recibe la respuesta normal porque ya está registrado (AMB-1, PC-5).
        fp = fingerprint(self.action_name, normalized.data)
        if self._registry.was_sent(fp):
            logger.info(
                "%s: estos mismos datos ya se enviaron en la conversación; no se reenvía",
                self.action_name,
            )
            return TurnResult(
                reply=reply,
                data=normalized.data,
                action_status=ActionStatus.DUPLICATE,
                warnings=normalized.warnings,
            )

        # 6. Enviar. `send` no lanza: un fallo llega como `ok=False` (AMB-4).
        logger.info("%s: datos completos y nuevos; se ejecuta la acción", self.action_name)
        send_result = self._sender.send(self.action_url, normalized.data)
        if send_result.ok:
            status = ActionStatus.SENT
            # Solo se marca lo que ha llegado: un FAILED se puede reenviar en otro turno.
            self._registry.mark_sent(fp)
            logger.info(
                "%s: acción registrada (código %s, intentos %s)",
                self.action_name,
                send_result.status_code,
                send_result.attempts,
            )
        else:
            # El cliente no puede creer que está registrado si no lo está (PC-8).
            logger.warning(
                "%s: la acción no se ha podido registrar (código %s, intentos %s); se "
                "responde con el mensaje de emergencia y se podrá reenviar en otro turno",
                self.action_name,
                send_result.status_code,
                send_result.attempts,
            )
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

    def _log_not_executed(self, model_failed: bool, data: Mapping[str, object | None]) -> None:
        """Explica en el log por qué no se ejecuta la acción en este turno.

        Nombra los campos que faltan, nunca sus valores: son datos del cliente (LOGS, PASO3).
        """
        if model_failed:
            logger.warning(
                "%s: ha fallado un modelo; no se ejecuta la acción y se responde con el "
                "mensaje de emergencia",
                self.action_name,
            )
            return
        missing = [str(name) for name, value in data.items() if value is None]
        if missing:
            logger.info(
                "%s: faltan datos (%s); no se ejecuta la acción",
                self.action_name,
                ", ".join(missing),
            )
        else:
            logger.info(
                "%s: no se cumplen las condiciones; no se ejecuta la acción", self.action_name
            )
