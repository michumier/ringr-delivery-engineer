"""Vocabulario del dominio: los enumerados coinciden con los nombres que impone el enunciado."""

import pytest

from ringr_agents.domain.enums import ActionName, ActionStatus, FieldName, TurnError


def test_field_names_match_the_names_imposed_by_the_statement():
    """Los valores de `FieldName` son los nombres del enunciado (ENUM-1)."""
    names = {member.name: member.value for member in FieldName}

    assert names == {
        "COMMITMENT_DATE": "commitment_date",
        "COMMITTED_AMOUNT": "committed_amount",
        "REQUEST": "request",
    }


@pytest.mark.parametrize(
    ("member", "text"),
    [
        (FieldName.REQUEST, "request"),
        (FieldName.COMMITMENT_DATE, "commitment_date"),
        (ActionStatus.NOT_REQUIRED, "not_required"),
        (ActionStatus.SENT, "sent"),
        (TurnError.PARSER_FAILED, "parser_failed"),
        (ActionName.REGISTER_REQUEST, "register_request"),
    ],
)
def test_str_enums_compare_equal_to_plain_strings(member, text):
    """Los `StrEnum` son a la vez cadenas: sirven de clave y de cabecera (ENUM-1, ENUM-2)."""
    assert member == text
    assert {text: 1}[member] == 1
    assert str(member) == text
