from __future__ import annotations

import logging

from ragtorch.core.context import ExecutionContext
from ragtorch.core.logging import get_logger, is_sensitive_key, log_event, redact


def test_get_logger_default_name():
    log = get_logger()
    assert log.name == "ragtorch"


def test_get_logger_namespaces_under_ragtorch():
    log = get_logger("retriever")
    assert log.name == "ragtorch.retriever"


def test_get_logger_leaves_already_namespaced_name():
    log = get_logger("ragtorch.retriever")
    assert log.name == "ragtorch.retriever"


def test_log_event_attaches_run_id_from_context(caplog):
    log = get_logger("test_logging")
    ctx = ExecutionContext()
    with caplog.at_level(logging.INFO, logger=log.name):
        log_event(log, logging.INFO, "module started", context=ctx, module="retriever")
    record = caplog.records[0]
    assert record.ragtorch_run_id == ctx.run_id
    assert record.ragtorch_module == "retriever"


def test_log_event_without_context_has_no_run_id_field(caplog):
    log = get_logger("test_logging_no_ctx")
    with caplog.at_level(logging.INFO, logger=log.name):
        log_event(log, logging.INFO, "no context here")
    record = caplog.records[0]
    assert not hasattr(record, "ragtorch_run_id")


def test_redact_hides_value_by_default():
    out = redact("super secret prompt text")
    assert "super secret" not in out
    assert "str" in out


def test_redact_reports_length_when_available():
    out = redact("abcde")
    assert "len=5" in out


def test_redact_handles_non_sized_values():
    out = redact(12345)
    assert "int" in out
    assert "12345" not in out


def test_redact_allow_true_returns_real_value():
    assert redact("visible", allow=True) == "visible"


def test_is_sensitive_key_detects_common_secret_names():
    assert is_sensitive_key("api_key")
    assert is_sensitive_key("Authorization")
    assert is_sensitive_key("password")
    assert is_sensitive_key("access_token")


def test_is_sensitive_key_false_for_ordinary_field():
    assert not is_sensitive_key("module_name")
    assert not is_sensitive_key("latency_ms")
