"""Función `normalize`: claves que faltan, que sobran y avisos por valores inválidos."""

import logging
from datetime import date

import pytest

from ringr_agents.domain.fields import AmountField, DateField, Normalized, TextField, normalize

LOGGER_NAME = "ringr_agents.domain.fields.normalize"


@pytest.fixture
def fields():
    return {
        "commitment_date": DateField(today=lambda: date(2026, 11, 13)),
        "committed_amount": AmountField(),
    }


def test_valid_data_is_cleaned_without_warnings(fields):
    """AMB-2 y AMB-3: datos válidos salen limpios y sin avisos."""
    raw = {"commitment_date": " 2026-12-01 ", "committed_amount": "150,5"}

    result = normalize(raw, fields)

    assert result == Normalized(
        data={"commitment_date": "2026-12-01", "committed_amount": 150.5}, warnings=()
    )


def test_missing_keys_count_as_none_without_warnings(fields):
    """AMB-2: las claves que faltan cuentan como `None`."""
    result = normalize({"committed_amount": 50}, fields)

    assert result.data == {"commitment_date": None, "committed_amount": 50.0}
    assert result.warnings == ()


def test_empty_dict_gives_all_none(fields):
    """AMB-2: un dict vacío da todo `None`, sin avisos."""
    result = normalize({}, fields)

    assert result.data == {"commitment_date": None, "committed_amount": None}
    assert result.warnings == ()


def test_extra_keys_are_ignored(fields):
    """AMB-2 y AMB-7: las claves que sobran no aparecen en el resultado."""
    raw = {"commitment_date": "2026-12-01", "committed_amount": 10, "request": "x", "foo": 1}

    result = normalize(raw, fields)

    assert set(result.data) == {"commitment_date", "committed_amount"}
    assert result.warnings == ()


def test_invalid_value_becomes_none_with_a_warning(fields):
    """AMB-2: un valor inválido pasa a `None` con aviso y el resto sigue."""
    raw = {"commitment_date": "2026-11-12", "committed_amount": 150}

    result = normalize(raw, fields)

    assert result.data == {"commitment_date": None, "committed_amount": 150.0}
    assert len(result.warnings) == 1
    assert "commitment_date" in result.warnings[0]
    assert "pasada" in result.warnings[0]


def test_several_invalid_values_give_one_warning_each(fields):
    """AMB-2: no se para en el primer campo inválido."""
    raw = {"commitment_date": "01/12/2026", "committed_amount": -5}

    result = normalize(raw, fields)

    assert result.data == {"commitment_date": None, "committed_amount": None}
    assert len(result.warnings) == 2
    assert "commitment_date" in result.warnings[0]
    assert "committed_amount" in result.warnings[1]


def test_warnings_are_also_logged(fields, caplog):
    """AMB-2 y AMB-10: el aviso queda también en el log (nivel WARNING)."""
    raw = {"commitment_date": "2026-13-45", "committed_amount": True}

    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        result = normalize(raw, fields)

    logged = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert logged == list(result.warnings)


def test_no_log_when_everything_is_valid(fields, caplog):
    """AMB-10: sin datos descartados no se escribe nada en el log."""
    with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
        normalize({"commitment_date": "2026-12-01", "committed_amount": 1}, fields)

    assert caplog.records == []


def test_empty_text_field_gives_none_without_warning(caplog):
    """AMB-3: un texto vacío es `None`, no un valor inválido."""
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        result = normalize({"request": "   "}, {"request": TextField()})

    assert result.data == {"request": None}
    assert result.warnings == ()
    assert caplog.records == []


def test_normalize_does_not_modify_the_input(fields):
    """AMB-2: el dict de entrada queda intacto."""
    raw = {"commitment_date": " 2026-12-01 ", "committed_amount": "150", "extra": 1}
    before = dict(raw)

    normalize(raw, fields)

    assert raw == before


def test_normalized_is_immutable(fields):
    """AMB-2: el resultado es una dataclass congelada."""
    result = normalize({}, fields)

    with pytest.raises(AttributeError):
        result.warnings = ("x",)


def test_agent_declares_its_own_fields_with_plain_string_keys():
    """CA-13 y ENUM-2: las claves pueden ser textos normales, sin tocar `enums.py`."""
    result = normalize({"nuevo": "  hola "}, {"nuevo": TextField()})

    assert result.data == {"nuevo": "hola"}
