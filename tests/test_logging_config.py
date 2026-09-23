import io
import sys
from collections.abc import Iterator

import pytest
import structlog
import structlog.stdlib
import structlog.testing

from la_rp_peace.logging_config import configure_logging, get_logger


@pytest.fixture(autouse=True)
def isolate_logging_configuration() -> Iterator[None]:
    was_configured = structlog.is_configured()
    original_config = structlog.get_config()
    structlog.reset_defaults()
    try:
        yield
    finally:
        structlog.reset_defaults()
        if was_configured:
            structlog.configure(**original_config)


def test_configure_logging_is_idempotent() -> None:
    configure_logging()
    original_config = structlog.get_config()

    configure_logging()

    assert structlog.is_configured()
    assert structlog.get_config() == original_config
    assert isinstance(structlog.get_config()["processors"][-1], structlog.dev.ConsoleRenderer)


def test_get_logger_emits_bound_field() -> None:
    configure_logging()

    with structlog.testing.capture_logs() as events:
        logger = get_logger("x")
        assert isinstance(logger, structlog.stdlib.BoundLogger)
        logger.bind(entity_id="item-1").info("item_processed")

    assert events == [
        {
            "logger": "x",
            "entity_id": "item-1",
            "event": "item_processed",
            "log_level": "info",
        }
    ]


@pytest.mark.parametrize("already_configured", [False, True])
def test_invalid_level_raises_clear_error(already_configured: bool) -> None:
    if already_configured:
        configure_logging()

    with pytest.raises(ValueError, match="Invalid log level 'INVALID'; expected one of:"):
        configure_logging("INVALID")

    assert structlog.is_configured() is already_configured


@pytest.mark.parametrize("method", ["exception", "warn"])
def test_non_level_method_names_do_not_raise(method: str) -> None:
    configure_logging("DEBUG")
    logger = get_logger("x")

    getattr(logger, method)("event_emitted")


def test_cyrillic_values_do_not_crash_on_a_legacy_code_page(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", stream)

    configure_logging()
    get_logger("x").info("document_parsed", filename="Положение.docx")
    stream.flush()

    assert "Положение.docx" in raw.getvalue().decode("utf-8")
