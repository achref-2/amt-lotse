"""The web page builds, every language switch fills every label, and nothing is sent to Gradio's servers."""

import os

from amt_lotse import app
from amt_lotse.cli import LANGUAGES


def test_page_builds_and_language_switch_matches_the_labels():
    ui = app.build_ui()
    switch = next(dep for dep in ui.fns.values() if dep.fn is app.switch_language)
    for lang in LANGUAGES:
        assert len(app.switch_language(lang)) == len(switch.outputs), lang


def test_no_usage_statistics():
    assert os.environ.get("GRADIO_ANALYTICS_ENABLED") == "False"
    assert app.build_ui().analytics_enabled is False


def test_phone_app_icon_exists():
    assert app.ICON.exists()
