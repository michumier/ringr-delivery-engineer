"""Modelos simulados: guion en orden, copia, excepciones y guion agotado (AMB-6, PC-8.3)."""

import pytest

from ringr_agents.infrastructure.models import (
    ConversationModel,
    ParserModel,
    ScriptExhaustedError,
)


class TestConversationModel:
    def test_returns_the_script_in_order(self):
        """AMB-6: una respuesta del guion por llamada, en orden."""
        model = ConversationModel(["uno", "dos", "tres"])

        answers = [model.answer_user(), model.answer_user(), model.answer_user()]

        assert answers == ["uno", "dos", "tres"]

    def test_raises_script_exhausted_after_the_last_item(self):
        """AMB-6: al acabarse el guion se lanza `ScriptExhaustedError` (no se repite)."""
        model = ConversationModel(["uno"])
        model.answer_user()

        with pytest.raises(ScriptExhaustedError):
            model.answer_user()
        with pytest.raises(ScriptExhaustedError):
            model.answer_user()

    def test_empty_script_is_exhausted_from_the_start(self):
        """AMB-6: un guion vacío falla en la primera llamada."""
        with pytest.raises(ScriptExhaustedError):
            ConversationModel([]).answer_user()

    def test_exception_in_script_is_raised_and_consumes_the_turn(self):
        """AMB-6 y AMB-11: una excepción del guion se lanza y cuenta como turno."""
        boom = RuntimeError("fallo")
        model = ConversationModel(["uno", boom, "tres"])
        model.answer_user()

        with pytest.raises(RuntimeError) as info:
            model.answer_user()

        assert info.value is boom
        assert model.answer_user() == "tres"

    def test_script_is_copied_at_construction(self):
        """AMB-6: modificar la lista original después no cambia el guion."""
        script = ["uno", "dos"]
        model = ConversationModel(script)
        script.append("tres")
        script[0] = "cambiado"

        assert [model.answer_user(), model.answer_user()] == ["uno", "dos"]
        with pytest.raises(ScriptExhaustedError):
            model.answer_user()

    def test_accepts_a_tuple_as_script(self):
        """AMB-6: vale cualquier secuencia."""
        assert ConversationModel(("a",)).answer_user() == "a"


class TestParserModel:
    def test_returns_the_script_in_order(self):
        """AMB-6: un dict del guion por llamada, en orden."""
        model = ParserModel([{"request": "a"}, {"request": "b"}])

        results = [model.parse_data(), model.parse_data()]

        assert results == [{"request": "a"}, {"request": "b"}]

    def test_raises_script_exhausted_after_the_last_item(self):
        """AMB-6: al acabarse el guion se lanza `ScriptExhaustedError`."""
        model = ParserModel([{"a": 1}])
        model.parse_data()

        with pytest.raises(ScriptExhaustedError):
            model.parse_data()

    def test_empty_script_is_exhausted_from_the_start(self):
        """AMB-6: un guion vacío falla en la primera llamada."""
        with pytest.raises(ScriptExhaustedError):
            ParserModel([]).parse_data()

    def test_exception_in_script_is_raised_and_consumes_the_turn(self):
        """AMB-6 y AMB-11: una excepción del guion se lanza y cuenta como turno."""
        boom = ValueError("parser roto")
        model = ParserModel([boom, {"a": 1}])

        with pytest.raises(ValueError) as info:
            model.parse_data()

        assert info.value is boom
        assert model.parse_data() == {"a": 1}

    def test_returns_a_copy_so_the_script_cannot_be_altered(self):
        """AMB-6: modificar el dict devuelto no altera el guion."""
        item = {"request": "a", "nested": {"k": [1]}}
        model = ParserModel([item, item])
        first = model.parse_data()
        first["request"] = "alterado"
        first["nested"]["k"].append(2)

        second = model.parse_data()

        assert second == {"request": "a", "nested": {"k": [1]}}
        assert first is not item

    def test_script_is_copied_at_construction(self):
        """AMB-6: modificar la lista original después no cambia el guion."""
        script = [{"a": 1}]
        model = ParserModel(script)
        script.append({"a": 2})

        model.parse_data()

        with pytest.raises(ScriptExhaustedError):
            model.parse_data()

    def test_script_exhausted_error_is_not_a_common_error_type(self):
        """PC-8.3: no hereda de un error «normal» que el turno pudiera capturar por accidente."""
        assert not issubclass(ScriptExhaustedError, (ValueError, RuntimeError, OSError))
