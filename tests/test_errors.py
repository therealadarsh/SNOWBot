"""Tests for snowbot.errors."""

from snowbot.errors import ConfigError, SnowbotError, ValidationError


def test_snowbot_error_str() -> None:
    err = SnowbotError(message="boom", code="test")
    assert str(err) == "boom"
    assert err.code == "test"


def test_config_error_defaults() -> None:
    err = ConfigError("bad config")
    assert err.code == "config_error"
    assert err.details is None


def test_validation_error_with_details() -> None:
    err = ValidationError("nope", details={"field": "id"})
    assert err.details == {"field": "id"}
