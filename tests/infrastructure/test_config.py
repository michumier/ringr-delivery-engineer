"""Configuración: valores por defecto, variables de entorno y valores inválidos (PC-10, PASO3)."""

import pytest

from ringr_agents.infrastructure.config import ConfigError, Settings


class TestSettingsDefaults:
    def test_uses_the_token_of_the_statement_and_default_retries(self):
        """PC-10, RF-12: sin variables, token del enunciado, 3 intentos y 0.2 s."""
        settings = Settings.from_env({})

        assert settings.api_token == "ringr_test_token_9f3a2c1d"
        assert settings.max_attempts == 3
        assert settings.base_delay == 0.2

    def test_reads_os_environ_when_no_env_is_given(self, monkeypatch):
        """PC-10: sin parámetro `env` lee el entorno real del proceso."""
        monkeypatch.setenv("RINGR_API_TOKEN", "desde_entorno")
        monkeypatch.delenv("RINGR_MAX_ATTEMPTS", raising=False)
        monkeypatch.delenv("RINGR_RETRY_BASE_DELAY", raising=False)

        settings = Settings.from_env()

        assert settings.api_token == "desde_entorno"
        assert settings.max_attempts == 3

    def test_empty_values_fall_back_to_defaults(self):
        """PC-10: una variable vacía cuenta como ausente."""
        env = {"RINGR_API_TOKEN": "", "RINGR_MAX_ATTEMPTS": " ", "RINGR_RETRY_BASE_DELAY": ""}

        settings = Settings.from_env(env)

        assert settings == Settings()


class TestSettingsFromVariables:
    def test_reads_all_variables(self):
        """PC-10: las tres variables sustituyen a los valores por defecto."""
        env = {
            "RINGR_API_TOKEN": "otro_token",
            "RINGR_MAX_ATTEMPTS": "5",
            "RINGR_RETRY_BASE_DELAY": "0.5",
        }

        settings = Settings.from_env(env)

        assert settings == Settings(api_token="otro_token", max_attempts=5, base_delay=0.5)

    def test_accepts_zero_delay(self):
        """PASO3: un retardo de 0 es válido (útil en tests)."""
        settings = Settings.from_env({"RINGR_RETRY_BASE_DELAY": "0"})

        assert settings.base_delay == 0.0


class TestSettingsInvalid:
    @pytest.mark.parametrize(
        ("name", "value"),
        [
            ("RINGR_MAX_ATTEMPTS", "abc"),
            ("RINGR_MAX_ATTEMPTS", "2.5"),
            ("RINGR_MAX_ATTEMPTS", "0"),
            ("RINGR_MAX_ATTEMPTS", "-1"),
            ("RINGR_RETRY_BASE_DELAY", "abc"),
            ("RINGR_RETRY_BASE_DELAY", "-0.1"),
            ("RINGR_RETRY_BASE_DELAY", "nan"),
            ("RINGR_RETRY_BASE_DELAY", "inf"),
        ],
    )
    def test_raises_config_error_for_invalid_values(self, name, value):
        """PC-10: un valor inválido lanza ConfigError, no un error genérico."""
        with pytest.raises(ConfigError):
            Settings.from_env({name: value})

    def test_config_error_names_the_variable(self):
        """PC-10: el mensaje indica qué variable falla."""
        with pytest.raises(ConfigError, match="RINGR_MAX_ATTEMPTS"):
            Settings.from_env({"RINGR_MAX_ATTEMPTS": "abc"})


class TestSettingsToken:
    def test_a_token_of_only_spaces_counts_as_missing(self):
        """PC-10: un token en blanco usa el valor por defecto, igual que las otras variables."""
        settings = Settings.from_env({"RINGR_API_TOKEN": "   "})

        assert settings.api_token == "ringr_test_token_9f3a2c1d"

    def test_surrounding_spaces_are_removed_from_the_token(self):
        """PC-10: los espacios alrededor del token se quitan."""
        settings = Settings.from_env({"RINGR_API_TOKEN": " otro_token\n"})

        assert settings.api_token == "otro_token"

    def test_repr_does_not_show_the_token(self):
        """PC-10: si se imprime la configuración no sale el token."""
        assert "ringr_test_token_9f3a2c1d" not in repr(Settings())
