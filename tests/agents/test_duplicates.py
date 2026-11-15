"""Duplicados en los agentes: no se reenvía lo ya enviado (CA-7, CA-8, AMB-1, PC-5, PC-9, RF-17)."""

from datetime import date

import pytest

from ringr_agents.agents import AssistanceAgent, DebtAgent
from ringr_agents.domain.constants import EMERGENCY_REPLY
from ringr_agents.domain.dedup import SentActionRegistry, fingerprint
from ringr_agents.domain.enums import ActionName, ActionStatus

DEBT = {"commitment_date": "2026-12-01", "committed_amount": 150.0}
EMPTY_DEBT = {"commitment_date": None, "committed_amount": None}
ADDRESS = {"request": "Quiero cambiar mi dirección"}


@pytest.fixture
def make_debt(make_deps, today):
    def _make(conversation, parser, http_results=(), registry=None):
        conversation_model, parser_model, sender, client = make_deps(
            conversation, parser, http_results
        )
        agent = DebtAgent(conversation_model, parser_model, sender, registry, today=today)
        return agent, client

    return _make


@pytest.fixture
def make_assistance(make_deps):
    def _make(conversation, parser, http_results=(), registry=None):
        conversation_model, parser_model, sender, client = make_deps(
            conversation, parser, http_results
        )
        return AssistanceAgent(conversation_model, parser_model, sender, registry), client

    return _make


class TestSameDataTwice:
    def test_debt_second_turn_with_same_data_is_duplicate(self, make_debt):
        """CA-7: mismos datos en dos turnos son 1 sola request y el 2.º es DUPLICATE."""
        agent, client = make_debt(["Anotado.", "Ya lo tengo."], [DEBT, DEBT])

        first = agent.handle_turn()
        second = agent.handle_turn()

        assert first.action_status is ActionStatus.SENT
        assert second.action_status is ActionStatus.DUPLICATE
        assert second.reply == "Ya lo tengo."
        assert second.errors == ()
        assert second.send_result is None
        assert len(client.requests) == 1

    def test_assistance_second_turn_with_same_data_is_duplicate(self, make_assistance):
        """CA-7: el agente de asistencia tampoco reenvía la misma solicitud."""
        agent, client = make_assistance(["Anotado.", "Ya lo tengo."], [ADDRESS, ADDRESS])

        first = agent.handle_turn()
        second = agent.handle_turn()

        assert first.action_status is ActionStatus.SENT
        assert second.action_status is ActionStatus.DUPLICATE
        assert second.reply == "Ya lo tengo."
        assert second.errors == ()
        assert second.send_result is None
        assert len(client.requests) == 1

    def test_duplicate_keeps_the_normalized_data(self, make_debt):
        """RF-17: el turno duplicado devuelve igualmente los datos normalizados."""
        agent, _ = make_debt(["a", "b"], [DEBT, DEBT])
        agent.handle_turn()

        second = agent.handle_turn()

        assert dict(second.data) == DEBT

    def test_equivalent_data_after_normalizing_is_duplicate(self, make_debt):
        """AMB-1: «150» y una fecha con espacios son lo mismo que 150.0 tras normalizar."""
        raw_text = {"commitment_date": " 2026-12-01 ", "committed_amount": "150"}
        agent, client = make_debt(["a", "b"], [raw_text, DEBT])

        first = agent.handle_turn()
        second = agent.handle_turn()

        assert first.action_status is ActionStatus.SENT
        assert second.action_status is ActionStatus.DUPLICATE
        assert len(client.requests) == 1

    def test_amount_as_comma_text_and_float_are_duplicate(self, make_debt):
        """AMB-1: «150,00» y 150.0 dan la misma huella."""
        text = {"commitment_date": "2026-12-01", "committed_amount": "150,00"}
        agent, client = make_debt(["a", "b"], [text, DEBT])

        agent.handle_turn()
        second = agent.handle_turn()

        assert second.action_status is ActionStatus.DUPLICATE
        assert len(client.requests) == 1


class TestChangesAreSent:
    def test_corrected_date_is_sent_again(self, make_debt):
        """CA-8: una corrección (2026-12-15 tras 2026-12-01) se envía: 2 requests."""
        corrected = {**DEBT, "commitment_date": "2026-12-15"}
        agent, client = make_debt(["a", "b"], [DEBT, corrected])

        first = agent.handle_turn()
        second = agent.handle_turn()

        assert first.action_status is ActionStatus.SENT
        assert second.action_status is ActionStatus.SENT
        assert len(client.requests) == 2

    def test_going_back_to_a_previous_commitment_is_duplicate(self, make_debt):
        """PC-5.2: A, B, A: el 3.er turno es DUPLICATE (límite conocido, se guarda todo)."""
        other = {**DEBT, "commitment_date": "2026-12-15"}
        agent, client = make_debt(["a", "b", "c"], [DEBT, other, DEBT])

        results = [agent.handle_turn() for _ in range(3)]

        assert [r.action_status for r in results] == [
            ActionStatus.SENT,
            ActionStatus.SENT,
            ActionStatus.DUPLICATE,
        ]
        assert len(client.requests) == 2


class TestFailuresAndNotRequired:
    def test_failed_send_is_not_marked_and_next_turn_is_sent(self, make_debt):
        """PC-5 y AMB-1: un FAILED (503) no se marca; el turno siguiente se envía."""
        agent, client = make_debt(["a", "b"], [DEBT, DEBT], http_results=[503, 200])

        first = agent.handle_turn()
        second = agent.handle_turn()

        assert first.action_status is ActionStatus.FAILED
        assert first.reply == EMERGENCY_REPLY
        assert second.action_status is ActionStatus.SENT
        assert len(client.requests) == 2

    def test_turn_without_enough_data_marks_nothing(self, make_debt):
        """PC-5: un turno NOT_REQUIRED no marca nada; con datos completos luego sí se envía."""
        agent, client = make_debt(["a", "b"], [EMPTY_DEBT, DEBT])

        first = agent.handle_turn()
        second = agent.handle_turn()

        assert first.action_status is ActionStatus.NOT_REQUIRED
        assert second.action_status is ActionStatus.SENT
        assert len(client.requests) == 1

    def test_not_required_turn_leaves_the_registry_empty(self, make_debt):
        """PC-5 y PC-9: tras un NOT_REQUIRED el registro inyectado sigue vacío."""
        registry = SentActionRegistry()
        agent, _ = make_debt(["a"], [EMPTY_DEBT], registry=registry)

        agent.handle_turn()

        assert registry.was_sent(fingerprint(ActionName.REGISTER_COMMITMENT, EMPTY_DEBT)) is False


class TestInjectedRegistry:
    def test_injected_registry_can_be_inspected_after_a_send(self, make_debt):
        """PC-9: el registro inyectado se puede inspeccionar tras enviar."""
        registry = SentActionRegistry()
        agent, _ = make_debt(["a"], [DEBT], registry=registry)

        agent.handle_turn()

        assert registry.was_sent(fingerprint(ActionName.REGISTER_COMMITMENT, DEBT)) is True

    def test_registry_with_the_fingerprint_already_marked_prevents_sending(self, make_debt):
        """PC-9: con la huella ya marcada, el agente no envía y devuelve DUPLICATE."""
        registry = SentActionRegistry()
        registry.mark_sent(fingerprint(ActionName.REGISTER_COMMITMENT, DEBT))
        agent, client = make_debt(["Anotado."], [DEBT], registry=registry)

        result = agent.handle_turn()

        assert result.action_status is ActionStatus.DUPLICATE
        assert result.reply == "Anotado."
        assert client.requests == []

    def test_assistance_accepts_an_injected_registry(self, make_assistance):
        """PC-9: el agente de asistencia también acepta un registro ya marcado."""
        registry = SentActionRegistry()
        registry.mark_sent(fingerprint(ActionName.REGISTER_REQUEST, ADDRESS))
        agent, client = make_assistance(["Anotado."], [ADDRESS], registry=registry)

        result = agent.handle_turn()

        assert result.action_status is ActionStatus.DUPLICATE
        assert client.requests == []

    def test_debt_agent_accepts_registry_and_today_together(self, make_deps):
        """PC-9: DebtAgent acepta `registry` y `today` a la vez (aquí la fecha ya es pasada)."""
        conversation, parser, sender, client = make_deps(["a"], [DEBT])
        agent = DebtAgent(
            conversation,
            parser,
            sender,
            registry=SentActionRegistry(),
            today=lambda: date(2026, 12, 2),
        )

        result = agent.handle_turn()

        assert result.action_status is ActionStatus.NOT_REQUIRED
        assert client.requests == []

    def test_two_agents_do_not_share_the_registry_by_default(self, make_debt):
        """PC-5 y PC-9: dos conversaciones distintas no comparten registro por defecto."""
        first_agent, first_client = make_debt(["a"], [DEBT])
        second_agent, second_client = make_debt(["a"], [DEBT])

        first = first_agent.handle_turn()
        second = second_agent.handle_turn()

        assert first.action_status is ActionStatus.SENT
        assert second.action_status is ActionStatus.SENT
        assert len(first_client.requests) == 1
        assert len(second_client.requests) == 1
