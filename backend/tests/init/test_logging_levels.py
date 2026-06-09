import logging
import pytest
from app.init.logging_config import apply_runtime_levels


@pytest.fixture(autouse=True)
def _restore_levels():
    """Save and restore root + app logger levels after each test.

    apply_runtime_levels mutates global logging state; without this fixture
    the level changes would leak into subsequent tests.
    """
    root_lvl = logging.getLogger().level
    app_lvl = logging.getLogger("app").level
    yield
    logging.getLogger().setLevel(root_lvl)
    logging.getLogger("app").setLevel(app_lvl)


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
