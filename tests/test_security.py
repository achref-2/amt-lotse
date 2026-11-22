"""The MCP server may only read letters inside the allowed folders."""

import pytest

from amt_lotse import mcp_server


@pytest.fixture
def allowed(tmp_path, monkeypatch):
    letters = tmp_path / "Briefe"
    letters.mkdir()
    (letters / "brief.txt").write_text("Test", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("geheim", encoding="utf-8")
    monkeypatch.setenv("AMT_LOTSE_LETTER_DIRS", str(letters))
    return letters


def test_letter_inside_is_allowed(allowed):
    assert mcp_server.resolve_letter(str(allowed / "brief.txt")) == (allowed / "brief.txt").resolve()


def test_dot_dot_trick_is_blocked(allowed):
    with pytest.raises(Exception, match="Not allowed"):
        mcp_server.resolve_letter(str(allowed / ".." / "secret.txt"))


def test_absolute_path_outside_is_blocked(allowed):
    with pytest.raises(Exception, match="Not allowed"):
        mcp_server.resolve_letter(str(allowed.parent / "secret.txt"))


def test_link_pointing_outside_is_blocked(allowed):
    link = allowed / "link.txt"
    try:
        link.symlink_to(allowed.parent / "secret.txt")
    except OSError:
        pytest.skip("symlinks not allowed on this system")
    with pytest.raises(Exception, match="Not allowed"):
        mcp_server.resolve_letter(str(link))
