"""Control de duplicados: `fingerprint` y `SentActionRegistry` (AMB-1, PC-5, RF-17)."""

from ringr_agents.domain.dedup import SentActionRegistry, fingerprint

ACTION = "register_commitment"
DATA = {"commitment_date": "2026-12-01", "committed_amount": 150.0}


class TestFingerprint:
    def test_same_action_and_same_data_give_the_same_fingerprint(self):
        """AMB-1 y RF-17: la misma acción con los mismos datos es la misma huella."""
        first = fingerprint(ACTION, DATA)

        second = fingerprint(ACTION, dict(DATA))

        assert first == second

    def test_key_order_does_not_change_the_fingerprint(self):
        """PC-5: el orden de las claves del diccionario no cambia la huella."""
        reversed_data = {"committed_amount": 150.0, "commitment_date": "2026-12-01"}

        assert fingerprint(ACTION, DATA) == fingerprint(ACTION, reversed_data)

    def test_different_data_give_a_different_fingerprint(self):
        """CA-8: otro valor (una corrección) es otra huella."""
        corrected = {**DATA, "commitment_date": "2026-12-15"}

        assert fingerprint(ACTION, DATA) != fingerprint(ACTION, corrected)

    def test_different_action_gives_a_different_fingerprint(self):
        """PC-5: los mismos datos con otra acción son otra huella."""
        assert fingerprint(ACTION, DATA) != fingerprint("register_request", DATA)

    def test_a_none_field_differs_from_a_value(self):
        """PC-5: un campo a None no es igual a un campo con valor."""
        with_none = {**DATA, "committed_amount": None}

        assert fingerprint(ACTION, with_none) != fingerprint(ACTION, DATA)

    def test_fingerprint_is_hashable(self):
        """PC-5: la huella se puede guardar en un `set` o usar como clave."""
        fp = fingerprint(ACTION, DATA)

        assert fp in {fp}
        assert {fp: 1}[fingerprint(ACTION, DATA)] == 1


class TestSentActionRegistry:
    def test_empty_registry_has_sent_nothing(self):
        """PC-5: un registro nuevo no tiene nada enviado."""
        registry = SentActionRegistry()

        assert registry.was_sent(fingerprint(ACTION, DATA)) is False

    def test_marked_fingerprint_was_sent(self):
        """RF-17: tras `mark_sent`, `was_sent` es verdadero para esa huella."""
        registry = SentActionRegistry()
        fp = fingerprint(ACTION, DATA)

        registry.mark_sent(fp)

        assert registry.was_sent(fp) is True
        assert registry.was_sent(fingerprint(ACTION, dict(DATA))) is True

    def test_other_fingerprints_are_not_affected_by_a_mark(self):
        """PC-5.2: marcar una huella no marca las demás."""
        registry = SentActionRegistry()
        registry.mark_sent(fingerprint(ACTION, DATA))

        other = fingerprint(ACTION, {**DATA, "committed_amount": 200.0})

        assert registry.was_sent(other) is False

    def test_marking_twice_is_harmless(self):
        """PC-5: marcar dos veces la misma huella no falla ni cambia el resultado."""
        registry = SentActionRegistry()
        fp = fingerprint(ACTION, DATA)

        registry.mark_sent(fp)
        registry.mark_sent(fp)

        assert registry.was_sent(fp) is True

    def test_two_registries_are_independent(self):
        """PC-5 y PC-9: cada registro (cada conversación) tiene su propia memoria."""
        first, second = SentActionRegistry(), SentActionRegistry()
        fp = fingerprint(ACTION, DATA)

        first.mark_sent(fp)

        assert first.was_sent(fp) is True
        assert second.was_sent(fp) is False
