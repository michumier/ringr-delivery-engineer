"""Estrategias de limpieza de campos: `TextField`, `DateField` y `AmountField`."""

import math
from datetime import date

import pytest

from ringr_agents.domain.fields import AmountField, DateField, InvalidFieldError, TextField

TODAY = date(2026, 11, 13)


@pytest.fixture
def date_field():
    return DateField(today=lambda: TODAY)


class TestTextField:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("Cambiar dirección", "Cambiar dirección"),
            ("  Cambiar dirección  ", "Cambiar dirección"),
            ("\n\tHola\n", "Hola"),
            ("", None),
            ("   ", None),
            (None, None),
        ],
    )
    def test_text_is_trimmed_and_empty_becomes_none(self, raw, expected):
        """AMB-3: se quitan espacios y el texto vacío pasa a `None`."""
        assert TextField().normalize(raw) == expected

    @pytest.mark.parametrize("raw", [123, 1.5, True, ["a"], {"a": 1}])
    def test_non_text_is_invalid(self, raw):
        """AMB-2: un valor que no es texto es inválido."""
        with pytest.raises(InvalidFieldError):
            TextField().normalize(raw)


class TestDateField:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("2026-12-01", "2026-12-01"),
            (" 2026-12-01 ", "2026-12-01"),
            ("2028-02-29", "2028-02-29"),
        ],
    )
    def test_valid_iso_date_is_returned_trimmed(self, date_field, raw, expected):
        """AMB-3: la fecha ISO válida se acepta, sin espacios."""
        assert date_field.normalize(raw) == expected

    def test_yesterday_is_rejected(self, date_field):
        """AMB-3: se rechazan las fechas pasadas."""
        with pytest.raises(InvalidFieldError, match="pasada"):
            date_field.normalize("2026-11-12")

    def test_today_is_accepted(self, date_field):
        """AMB-3: la fecha de hoy sí vale (borde)."""
        assert date_field.normalize("2026-11-13") == "2026-11-13"

    def test_tomorrow_is_accepted(self, date_field):
        """AMB-3: mañana es futuro y vale."""
        assert date_field.normalize("2026-11-14") == "2026-11-14"

    @pytest.mark.parametrize(
        "raw",
        [
            "01/12/2026",
            "20261201",
            "2026-13-45",
            "2027-02-29",
            "2026-W49-2",
            "2026-1-5",
            "mañana",
        ],
    )
    def test_malformed_or_impossible_dates_are_invalid(self, date_field, raw):
        """AMB-2 y AMB-3: formato distinto de AAAA-MM-DD o fecha inexistente se descarta."""
        with pytest.raises(InvalidFieldError):
            date_field.normalize(raw)

    @pytest.mark.parametrize("raw", ["", "   ", None])
    def test_empty_date_becomes_none(self, date_field, raw):
        """AMB-3: vacío pasa a `None`."""
        assert date_field.normalize(raw) is None

    @pytest.mark.parametrize("raw", [20261201, 1.5, True, date(2026, 12, 1)])
    def test_non_text_date_is_invalid(self, date_field, raw):
        """AMB-2: una fecha que no llega como texto es inválida."""
        with pytest.raises(InvalidFieldError):
            date_field.normalize(raw)

    def test_today_is_injected_and_changes_the_boundary(self):
        """PC-4: `today` inyectado decide el borde, sin depender del reloj."""
        field = DateField(today=lambda: date(2030, 1, 1))

        assert field.normalize("2030-01-01") == "2030-01-01"
        with pytest.raises(InvalidFieldError):
            field.normalize("2029-12-31")

    def test_default_today_is_the_system_date(self):
        """PC-4: sin inyección se usa la fecha real: hoy vale y ayer falla."""
        field = DateField()
        today = date.today()
        yesterday = date.fromordinal(today.toordinal() - 1)

        assert field.normalize(today.isoformat()) == today.isoformat()
        with pytest.raises(InvalidFieldError):
            field.normalize(yesterday.isoformat())


class TestAmountField:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (150, 150.0),
            (150.5, 150.5),
            ("150", 150.0),
            ("  150  ", 150.0),
            ("150,5", 150.5),
            ("150.5", 150.5),
            ("150,50", 150.5),
            ("150.50", 150.5),
            ("+150", 150.0),
            ("0,5", 0.5),
            (0.005, 0.01),
        ],
    )
    def test_valid_amounts_are_converted_to_float(self, raw, expected):
        """AMB-3: importe en texto a decimal; coma o punto decimal, uno solo."""
        result = AmountField().normalize(raw)

        assert result == expected
        assert isinstance(result, float)

    @pytest.mark.parametrize(("raw", "expected"), [(2.675, 2.68), ("2,67", 2.67), (1.005, 1.01)])
    def test_amount_is_rounded_half_up_to_cents(self, raw, expected):
        """AMB-3 y PC-11: redondeo a céntimos con ROUND_HALF_UP (2.675 da 2.68)."""
        assert AmountField().normalize(raw) == expected

    def test_amount_with_many_decimals_is_rounded(self):
        """AMB-3: un float con muchos decimales se redondea a 2."""
        assert AmountField().normalize(10.123456) == 10.12

    @pytest.mark.parametrize("raw", ["1.500,50", "1,500", "1.500", "1,500.50", "2.675", "1,2,3"])
    def test_ambiguous_amounts_are_invalid(self, raw):
        """AMB-3: lo ambiguo no se adivina, se descarta."""
        with pytest.raises(InvalidFieldError):
            AmountField().normalize(raw)

    @pytest.mark.parametrize("raw", ["abc", "150€", "1e3", "--5", "150,", ",5"])
    def test_malformed_amount_text_is_invalid(self, raw):
        """AMB-2: texto que no es un importe se descarta."""
        with pytest.raises(InvalidFieldError):
            AmountField().normalize(raw)

    @pytest.mark.parametrize("raw", [0, 0.0, "0", "0,00", -50, -0.5, "-50", "-50,5", 0.004])
    def test_zero_negative_or_rounding_to_zero_is_invalid(self, raw):
        """AMB-2 y AMB-3: el importe debe ser mayor que 0 (también tras redondear)."""
        with pytest.raises(InvalidFieldError, match="mayor que 0"):
            AmountField().normalize(raw)

    @pytest.mark.parametrize("raw", [True, False])
    def test_bool_is_not_an_amount(self, raw):
        """AMB-2: `True` no vale 1 euro."""
        with pytest.raises(InvalidFieldError, match="booleano"):
            AmountField().normalize(raw)

    @pytest.mark.parametrize("raw", [math.nan, math.inf, -math.inf])
    def test_nan_and_infinity_are_invalid(self, raw):
        """AMB-2: NaN e infinito no son importes."""
        with pytest.raises(InvalidFieldError, match="finito"):
            AmountField().normalize(raw)

    @pytest.mark.parametrize("raw", ["", "   ", None])
    def test_empty_amount_becomes_none(self, raw):
        """AMB-3: vacío pasa a `None`."""
        assert AmountField().normalize(raw) is None

    @pytest.mark.parametrize("raw", [[150], {"a": 1}, (1,), b"150"])
    def test_unsupported_types_are_invalid(self, raw):
        """AMB-2: tipos que no son número ni texto se descartan."""
        with pytest.raises(InvalidFieldError, match="tipo"):
            AmountField().normalize(raw)
