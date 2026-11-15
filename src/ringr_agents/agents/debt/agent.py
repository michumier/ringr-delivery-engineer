"""Clase `DebtAgent`: registra el compromiso de pago (fecha e importe)."""

from collections.abc import Callable, Mapping
from datetime import date

from ringr_agents.agents.base_agent import BaseAgent
from ringr_agents.domain.enums import ActionName, FieldName
from ringr_agents.domain.fields import AmountField, DateField, FieldNormalizer
from ringr_agents.domain.ports import ActionSender
from ringr_agents.infrastructure.models import ConversationModel, ParserModel


class DebtAgent(BaseAgent):
    """Agente de deuda: solo ejecuta si hay fecha e importe (RF-8)."""

    action_name = ActionName.REGISTER_COMMITMENT
    action_url = "https://api.ringr.debt/v1/commitment"

    def __init__(
        self,
        conversation_model: ConversationModel,
        parser_model: ParserModel,
        sender: ActionSender,
        *,
        today: Callable[[], date] = date.today,
    ) -> None:
        super().__init__(conversation_model, parser_model, sender)
        # `today` se inyecta para poder probar el borde de «fecha pasada» (PC-4).
        self._fields: dict[str, FieldNormalizer] = {
            FieldName.COMMITMENT_DATE: DateField(today),
            FieldName.COMMITTED_AMOUNT: AmountField(),
        }

    def fields(self) -> Mapping[str, FieldNormalizer]:
        return self._fields

    def should_execute(self, data: Mapping[str, object | None]) -> bool:
        return (
            data.get(FieldName.COMMITMENT_DATE) is not None
            and data.get(FieldName.COMMITTED_AMOUNT) is not None
        )
