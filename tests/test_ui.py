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


def test_public_link_always_needs_a_password(monkeypatch):
    """--share must never start without a password: the link alone would let anyone in."""
    import sys

    seen = {}

    class FakeUI:
        def launch(self, **kwargs):
            seen.update(kwargs)
            return None, "http://127.0.0.1:7860", "https://abc.gradio.live"

        def block_thread(self):
            pass

    monkeypatch.delenv("AMT_LOTSE_PASSWORD", raising=False)     # a fresh random password
    monkeypatch.setattr(app, "build_ui", lambda: FakeUI())
    monkeypatch.setattr(sys, "argv", ["amt-lotse-ui", "--share"])
    app.main()
    assert seen["share"] is True
    assert seen["auth"][0] == "amt" and len(seen["auth"][1]) >= 8
    assert seen["server_name"] == "127.0.0.1"          # the computer itself stays closed to the local network
