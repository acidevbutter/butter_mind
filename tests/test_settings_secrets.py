import pytest
from pydantic import ValidationError

from app.settings.config import Settings


def test_development_allows_default_password() -> None:
    settings = Settings(_env_file=None, environment="development")
    assert settings.database_password == "butter_mind"


@pytest.mark.parametrize("environment", ["staging", "preprod", "production"])
def test_non_dev_rejects_default_database_password(environment: str) -> None:
    with pytest.raises(ValidationError, match="DATABASE_PASSWORD"):
        Settings(_env_file=None, environment=environment, maritaca_api_key="key")


def test_non_dev_rejects_empty_maritaca_api_key() -> None:
    with pytest.raises(ValidationError, match="MARITACA_API_KEY"):
        Settings(
            _env_file=None,
            environment="staging",
            database_password="real-password",
            maritaca_api_key="",
        )


def test_non_dev_valid_config_passes() -> None:
    settings = Settings(
        _env_file=None,
        environment="production",
        database_password="real-password",
        maritaca_api_key="key",
    )
    assert settings.database_password == "real-password"
