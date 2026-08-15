from __future__ import annotations

import dataclasses

import pytest

from ragtorch.core.config import RAGConfig
from ragtorch.core.errors import ConfigurationError


def test_default_config():
    cfg = RAGConfig()
    assert cfg.debug is False
    assert cfg.tracing is False
    assert cfg.profiling is False


def test_config_is_frozen():
    cfg = RAGConfig()
    with pytest.raises(dataclasses.FrozenInstanceError):
        cfg.debug = True


def test_with_overrides_returns_new_instance():
    cfg = RAGConfig()
    cfg2 = cfg.with_overrides(debug=True)
    assert cfg2.debug is True
    assert cfg.debug is False
    assert cfg is not cfg2


def test_with_overrides_unknown_field_raises():
    cfg = RAGConfig()
    with pytest.raises(ConfigurationError, match="Unknown configuration field"):
        cfg.with_overrides(not_a_field=True)
