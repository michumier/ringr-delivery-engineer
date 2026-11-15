"""Clase `AssistanceAgent`: registra la petición del usuario."""

from collections.abc import Mapping

from ringr_agents.agents.base_agent import BaseAgent
from ringr_agents.domain.enums import ActionName, FieldName
from ringr_agents.domain.fields import FieldNormalizer, TextField


class AssistanceAgent(BaseAgent):
    """Agente de asistencia: solo ejecuta si hay petición (RF-10)."""

    action_name = ActionName.REGISTER_REQUEST
    action_url = "https://api.ringr.assistance/v1/request"

    def fields(self) -> Mapping[str, FieldNormalizer]:
        return {FieldName.REQUEST: TextField()}

    def should_execute(self, data: Mapping[str, object | None]) -> bool:
        return data.get(FieldName.REQUEST) is not None
