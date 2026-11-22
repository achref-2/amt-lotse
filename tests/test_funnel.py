"""Online from anywhere with Tailscale Funnel: the app on this PC gets a public HTTPS address,
the status page on GitHub Pages says whether the AI is on. The public address must never work without a
real password, and the one page without a password (/amt-status) must say nothing but "AI on or off"."""

import importlib.util
import sys
from pathlib import Path

import gradio as gr
import pytest
from fastapi.testclient import TestClient

from amt_lotse import app

ROOT = Path(__file__).resolve().parents[1]


def test_funnel_refuses_a_weak_password(monkeypatch):
    monkeypatch.setenv("AMT_LOTSE_PASSWORD", "short")
    monkeypatch.setattr(sys, "argv", ["amt-lotse-ui", "--funnel"])
    with pytest.raises(SystemExit):
        app.main()


def test_funnel_starts_locally_with_password_and_status_route(monkeypatch):
    seen = {}

    class FakeUI:
        def launch(self, **kwargs):
            seen.update(kwargs)

        def block_thread(self):
            seen["blocked"] = True

    monkeypatch.setenv("AMT_LOTSE_PASSWORD", "a-long-secret-1234")
    monkeypatch.setenv("AMT_LOTSE_FUNNEL", "0")    # main() switches it on; monkeypatch removes it again afterwards
    monkeypatch.setattr(app, "start_funnel", lambda port: (True, ""))
    monkeypatch.setattr(app, "tailscale_url", lambda port: "https://my-pc.example.ts.net")
    monkeypatch.setattr(app, "build_ui", lambda: FakeUI())
    monkeypatch.setattr(app, "add_status_route", lambda ui: seen.setdefault("status_route", True))
    monkeypatch.setattr(sys, "argv", ["amt-lotse-ui", "--funnel"])
    app.main()
    assert seen["server_name"] == "127.0.0.1"           # only Tailscale passes traffic on; no open port
    assert seen["auth"] == ("amt", "a-long-secret-1234")
    assert seen["status_route"] and seen["blocked"]


def test_status_route_is_public_but_says_only_on_or_off(monkeypatch):
    monkeypatch.setattr(app, "ai_online", lambda: True)
    with gr.Blocks() as ui:
        gr.Markdown("letter")
    ui.launch(server_name="127.0.0.1", auth=("amt", "a-long-secret-1234"), prevent_thread_lock=True)
    try:
        app.add_status_route(ui)
        client = TestClient(ui.app, base_url="http://127.0.0.1:7860")   # as on the PC, behind Tailscale
        ok = client.get("/amt-status", headers={"Origin": "https://achref-2.github.io"})
        assert ok.json() == {"app": True, "ai": True}
        assert ok.headers["access-control-allow-origin"] == "https://achref-2.github.io"
        other = client.get("/amt-status", headers={"Origin": "https://evil.example"})
        assert "access-control-allow-origin" not in other.headers   # other websites can't read it
        assert client.get("/config").status_code == 401             # everything else still needs the password
    finally:
        ui.close()


def test_status_page_has_every_language_and_the_app_address():
    spec = importlib.util.spec_from_file_location("build_status_page", ROOT / "scripts" / "build_status_page.py")
    page = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(page)
    html = page.build("https://my-pc.example.ts.net/")
    assert '"https://my-pc.example.ts.net"' in html
    for _name, code in app.LANG_CHOICES:
        assert f'data-lang="{code}"' in html
    assert "AI on this computer" not in html            # on the public page it is not the visitor's computer
    with pytest.raises(SystemExit):
        page.build("http://insecure.example")
