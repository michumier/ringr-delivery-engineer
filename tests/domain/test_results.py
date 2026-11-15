"""`TurnResult` y `SendResult`: DTO inmutables con valores por defecto (AMB-5)."""

import dataclasses

import pytest

from ringr_agents.domain.enums import ActionStatus, TurnError
from ringr_agents.domain.results import SendResult, TurnResult


class TestTurnResult:
    def test_optional_fields_default_to_empty(self):
        """AMB-5: sin avisos, errores ni envío por defecto."""
        result = TurnResult(reply="hola", data={}, action_status=ActionStatus.NOT_REQUIRED)

        assert result.warnings == ()
        assert result.errors == ()
        assert result.send_result is None

    def test_keeps_the_given_values(self):
        """AMB-5: el resultado guarda respuesta, datos, estado, avisos, errores y envío."""
        send = SendResult(ok=False, attempts=1, status_code=503, idempotency_key="k")

        result = TurnResult(
            reply="r",
            data={"request": None},
            action_status=ActionStatus.FAILED,
            warnings=("aviso",),
            errors=(TurnError.SEND_FAILED,),
            send_result=send,
        )

        assert result.reply == "r"
        assert result.data == {"request": None}
        assert result.action_status is ActionStatus.FAILED
        assert result.warnings == ("aviso",)
        assert result.errors == (TurnError.SEND_FAILED,)
        assert result.send_result is send

    def test_is_immutable(self):
        """AMB-5: un resultado ya devuelto no se puede alterar."""
        result = TurnResult(reply="r", data={}, action_status=ActionStatus.SENT)

        with pytest.raises(dataclasses.FrozenInstanceError):
            result.reply = "otra"  # type: ignore[misc]
