"""Always-online version: the app runs on a server, the AI on the owner's PC.
When the PC is off, the page must say so clearly, and the online mode must never start without a real password."""

import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import ollama
import pytest

from amt_lotse import app, extract, landing


@pytest.fixture
def fake_ollama():
    """A tiny local server that answers /api/version like Ollama and remembers the Host header it got."""
    seen = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen["host"] = self.headers["Host"]
            body = b'{"version": "0.40.17"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}", seen
    server.shutdown()


def test_ai_online_and_the_request_is_addressed_to_localhost(fake_ollama, monkeypatch):
    """Ollama on the PC refuses other host names; through Tailscale the request must still say 'localhost'."""
    url, seen = fake_ollama
    monkeypatch.setattr(extract, "client", ollama.Client(host=url, headers={"Host": "localhost"}))
    assert extract.ai_online() is True
    assert seen["host"] == "localhost"


def test_ai_offline_when_nothing_answers(monkeypatch):
    monkeypatch.setattr(extract, "client", ollama.Client(host="http://127.0.0.1:9"))   # nothing listens there
    assert extract.ai_online(timeout=1) is False


def test_proxy_settings_only_in_the_online_version(monkeypatch):
    monkeypatch.setattr(extract, "OLLAMA_PROXY", "socks5://localhost:1055")
    options = extract.client_options()
    assert options["proxy"] == "socks5://localhost:1055" and options["headers"] == {"Host": "localhost"}
    monkeypatch.setattr(extract, "OLLAMA_PROXY", None)
    assert "proxy" not in extract.client_options()


def test_server_off_message_in_the_users_language(monkeypatch):
    monkeypatch.setenv("AMT_LOTSE_CLOUD", "1")
    monkeypatch.setattr(app, "ai_online", lambda: False)
    for lang in app.UI:
        assert landing.TEXT[lang]["ai_off_h"] in app._error(ConnectionError("refused"), app.UI[lang]), lang
        assert 'class="ai-off"' in app.ai_status(lang)
    monkeypatch.setattr(app, "ai_online", lambda: True)
    assert 'class="ai-on"' in app.ai_status("en")


def test_on_this_computer_nothing_changes(monkeypatch):
    monkeypatch.delenv("AMT_LOTSE_CLOUD", raising=False)
    assert app.ai_status("en") == ""
    assert "Ollama" in app._error(ConnectionError("refused"), app.UI["en"])
    assert "AI on this computer" in landing.hero_html("en")


def test_online_version_does_not_claim_the_ai_is_on_this_computer():
    assert "AI on this computer" not in landing.hero_html("en", cloud=True)
    assert "private computer" in landing.info_html("en", cloud=True)


def test_online_version_needs_a_real_password(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["amt-lotse-ui", "--cloud"])
    for weak in ["", "short"]:
        monkeypatch.setenv("AMT_LOTSE_PASSWORD", weak)
        with pytest.raises(SystemExit):
            app.main()


def test_online_version_starts_with_password_for_everyone(monkeypatch):
    seen = {}

    class FakeUI:
        def launch(self, **kwargs):
            seen.update(kwargs)

    monkeypatch.setenv("AMT_LOTSE_PASSWORD", "a-long-secret-1234")
    monkeypatch.setenv("AMT_LOTSE_CLOUD", "0")     # main() switches it on; monkeypatch removes it again afterwards
    monkeypatch.setattr(app, "ai_online", lambda: False)
    monkeypatch.setattr(app, "build_ui", lambda: FakeUI())
    monkeypatch.setattr(sys, "argv", ["amt-lotse-ui", "--cloud"])
    app.main()
    assert seen["server_name"] == "0.0.0.0"
    assert seen["auth"] == ("amt", "a-long-secret-1234")
