"""Logging, tested for the one case that actually broke.

`logging.basicConfig` is a no-op when the root logger already has a handler,
and the Lambda runtime installs one before our code imports. The result is a
function that runs correctly and logs nothing: CloudWatch shows START, END and
REPORT, and every `log.info` is dropped. Nothing errors, so nothing points at
the cause.

The test that matters is therefore the second one - it fails against a plain
`basicConfig` and passes against `configure_logging`. The others exist so that
fixing the Lambda case does not break running locally.
"""

from __future__ import annotations

import io
import logging
import sys

import pytest

from src.logging_setup import configure_logging


@pytest.fixture(autouse=True)
def pristine_root_logger():
    """Give every test the root logger back the way it found it.

    Logging is process-global state, so a test that reconfigures it would
    otherwise decide the outcome of whichever test runs next.
    """
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    yield
    root.handlers[:] = handlers
    root.setLevel(level)


def test_it_configures_a_bare_interpreter():
    """Running locally: no handler yet, so a handler has to be installed."""
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.WARNING)

    configure_logging()

    assert root.level == logging.INFO
    assert root.handlers, "nothing would be printed at all"


def test_it_raises_the_level_when_a_handler_already_exists(monkeypatch):
    """The Lambda case, and the reason this module exists.

    `basicConfig` returns early here without setting the level, so INFO
    records are discarded by the root logger before any handler sees them.
    """
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(logging.StreamHandler(sys.stdout))
    root.setLevel(logging.WARNING)  # the Lambda runtime's default

    configure_logging()

    assert root.level == logging.INFO


def test_log_level_is_honoured(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "warning")  # lower case on purpose
    logging.getLogger().setLevel(logging.INFO)

    configure_logging()

    assert logging.getLogger().level == logging.WARNING


def test_an_info_record_survives_the_lambda_setup():
    """End to end: the record reaches a handler, not just the right level.

    Captured through our own handler rather than pytest's `caplog`, because
    this test has to clear the root handlers to stand in for Lambda - which
    would remove caplog's handler along with them.
    """
    stream = io.StringIO()
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(logging.StreamHandler(stream))
    root.setLevel(logging.WARNING)

    configure_logging()
    logging.getLogger("src.data.ingest").info("wrote s3://bucket/key")

    assert "wrote s3://bucket/key" in stream.getvalue()


def test_yfinance_is_kept_quiet():
    """It logs every download at INFO and buries everything else."""
    configure_logging()
    assert logging.getLogger("yfinance").level == logging.WARNING
