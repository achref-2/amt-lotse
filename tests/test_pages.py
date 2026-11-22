"""Several pages = one letter; an unreadable page is named; long letters keep page 1."""

from amt_lotse import ocr
from amt_lotse.extract import options_for


def _files(tmp_path, monkeypatch, pages: dict[str, str]):
    """Fake photos: the OCR 'reads' the text we put in the dict."""
    paths = []
    for name in pages:
        p = tmp_path / name
        p.write_bytes(name.encode())
        paths.append(p)
    monkeypatch.setattr(ocr, "ocr_image", lambda b: (pages[b.decode()], False))
    return paths


def test_pages_are_joined_in_order(tmp_path, monkeypatch):
    paths = _files(tmp_path, monkeypatch, {"1.jpg": "Erste Seite " + "a" * 200, "2.jpg": "Zweite Seite " + "b" * 200})
    letter = ocr.load_letters(paths)
    assert letter.pages == 2 and not letter.looks_bad
    assert letter.text.index("Erste Seite") < letter.text.index("Zweite Seite")
    assert "--- Seite 2 ---" in letter.text


def test_unreadable_page_is_named(tmp_path, monkeypatch):
    paths = _files(tmp_path, monkeypatch, {"1.jpg": "Erste Seite " + "a" * 200, "2.jpg": "???", "3.jpg": "c" * 200})
    letter = ocr.load_letters(paths)
    assert letter.looks_bad and letter.bad_pages == [2]


def test_text_file_plus_photo(tmp_path, monkeypatch):
    (tmp_path / "brief.txt").write_text("Der Brief " + "a" * 200, encoding="utf-8")
    photo = _files(tmp_path, monkeypatch, {"anlage.jpg": "Rechtsbehelfsbelehrung " + "b" * 200})
    letter = ocr.load_letters([tmp_path / "brief.txt", *photo])
    assert letter.pages == 2 and letter.ocr_pages == 1 and not letter.looks_bad


def test_very_long_letter_is_cut_at_the_end(tmp_path):
    first = tmp_path / "1.txt"
    first.write_text("Frist 04.12.2026 " + "a" * 1000, encoding="utf-8")
    rest = tmp_path / "2.txt"
    rest.write_text("z" * 60_000, encoding="utf-8")
    letter = ocr.load_letters([first, rest])
    assert letter.cut and len(letter.text) == ocr.MAX_CHARS and "Frist 04.12.2026" in letter.text


def test_context_grows_with_the_letter():
    assert options_for("x" * 1000)["num_ctx"] == 4096           # short letters: unchanged
    assert options_for("x" * 20_000)["num_ctx"] > 4096           # 3-4 pages: more room, so page 1 isn't dropped
    assert options_for("x" * 200_000)["num_ctx"] == 16384        # capped
    assert options_for("x")["temperature"] == 0
