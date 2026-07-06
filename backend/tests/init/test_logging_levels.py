import logging
import os
import pytest
from app.init.logging_config import apply_runtime_levels


@pytest.fixture(autouse=True)
def _restore_levels(monkeypatch):
    """Save and restore root + app logger levels after each test.

    apply_runtime_levels mutates global logging state; without this fixture
    the level changes would leak into subsequent tests. Also clear the
    MEDIATRANX_LOG_LEVEL env var to prevent dev-machine residue from
    affecting production/staging test cases.
    """
    root_lvl = logging.getLogger().level
    app_lvl = logging.getLogger("app").level
    # Ensure env var is clean before test runs
    monkeypatch.delenv("MEDIATRANX_LOG_LEVEL", raising=False)
    yield
    logging.getLogger().setLevel(root_lvl)
    logging.getLogger("app").setLevel(app_lvl)
    # Clean up after test
    os.environ.pop("MEDIATRANX_LOG_LEVEL", None)


def test_production_keeps_app_info_but_root_warning():
    apply_runtime_levels("production")

    # Our app diagnostics survive (app.init.system_info inherits from "app")
    assert logging.getLogger("app").isEnabledFor(logging.INFO)
    assert logging.getLogger("app.init.system_info").isEnabledFor(logging.INFO)

    # Root stays WARNING → third-party INFO is suppressed
    assert logging.getLogger().level == logging.WARNING

    # A logger with no explicit level inherits root's WARNING → INFO suppressed
    fresh_third_party = logging.getLogger("some.thirdparty.logger")
    assert not fresh_third_party.isEnabledFor(logging.INFO)


def test_dev_is_debug_everywhere():
    apply_runtime_levels("dev")

    assert logging.getLogger().level == logging.DEBUG
    assert logging.getLogger("app").isEnabledFor(logging.DEBUG)
    assert logging.getLogger("app.init.system_info").isEnabledFor(logging.DEBUG)


def test_unknown_mode_treated_as_production():
    """Any mode value that is not 'dev' should behave like production."""
    apply_runtime_levels("staging")

    assert logging.getLogger().level == logging.WARNING
    assert logging.getLogger("app").isEnabledFor(logging.INFO)
    assert not logging.getLogger("app").isEnabledFor(logging.DEBUG)


def test_env_override_forces_debug_in_production(monkeypatch):
    monkeypatch.setenv("MEDIATRANX_LOG_LEVEL", "debug")
    apply_runtime_levels("production")
    assert logging.getLogger().level == logging.DEBUG
    assert logging.getLogger("app").level == logging.DEBUG


def test_env_override_invalid_value_ignored(monkeypatch):
    monkeypatch.setenv("MEDIATRANX_LOG_LEVEL", "chatty")
    apply_runtime_levels("production")
    assert logging.getLogger().level == logging.WARNING   # 維持 mode 推導
    assert logging.getLogger("app").level == logging.INFO


def test_env_override_absent_keeps_mode_behavior(monkeypatch):
    monkeypatch.delenv("MEDIATRANX_LOG_LEVEL", raising=False)
    apply_runtime_levels("dev")
    assert logging.getLogger().level == logging.DEBUG
