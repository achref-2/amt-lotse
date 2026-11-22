"""When a model gets stuck repeating itself, Ollama aborts with 'token repeat limit reached' (HTTP 500).
One retry with a repetition penalty usually breaks the loop; if not, the user gets a clear message."""

import ollama
import pytest

from amt_lotse import ocr
from amt_lotse.extract import ModelLoopError, extract_letter_info
from conftest import eval_letter, model_info


def loop():
    return ollama.ResponseError("prediction aborted, token repeat limit reached", 500)


def test_retry_with_repetition_penalty_after_a_loop(fake_model):
    calls = fake_model(loop(), model_info(sender="Muster Mobilfunk GmbH"))
    info = extract_letter_info(eval_letter("mahnung_01"))
    assert info.sender == "Muster Mobilfunk GmbH"
    assert len(calls) == 2
    retry = calls[1]["options"]
    assert retry["repeat_penalty"] > 1 and retry["temperature"] > 0
    assert retry["num_ctx"] == calls[0]["options"]["num_ctx"]        # the context size is kept


def test_loop_twice_is_a_clear_error(fake_model):
    fake_model(loop(), loop())
    with pytest.raises(ModelLoopError):
        extract_letter_info(eval_letter("mahnung_01"))


def test_other_errors_are_not_retried(fake_model):
    calls = fake_model(ollama.ResponseError("model 'qwen2.5:3b' not found", 404))
    with pytest.raises(ollama.ResponseError):
        extract_letter_info(eval_letter("mahnung_01"))
    assert len(calls) == 1


def _photo(tmp_path, monkeypatch):
    from PIL import Image

    monkeypatch.setattr(ocr, "_shrink_png", lambda b: b)
    photo = tmp_path / "brief.png"
    Image.new("RGB", (100, 200), "white").save(photo)
    return photo


def test_ocr_loop_then_the_photo_is_read_in_two_halves(fake_model, tmp_path, monkeypatch):
    photo = _photo(tmp_path, monkeypatch)
    top = "Finanzamt Musterstadt\nSteuerbescheid 2025\n" + "Zeile oben\n" * 10 + "Gemeinsame Zeile"
    bottom = "Gemeinsame Zeile\nBitte zahlen Sie 312,00 € bis zum 23.12.2026.\n" + "Zeile unten\n" * 10
    calls = fake_model(loop(), loop(), top, bottom)
    letter = ocr.load_letter(photo)
    assert not letter.looks_bad
    assert letter.text.count("Gemeinsame Zeile") == 1                 # the overlap is kept once
    assert letter.text.index("Steuerbescheid") < letter.text.index("312,00 €")
    assert len(calls) == 4


def test_ocr_still_stuck_in_halves_means_take_the_photo_again(fake_model, tmp_path, monkeypatch):
    photo = _photo(tmp_path, monkeypatch)
    fake_model(loop(), loop(), loop(), loop())
    assert ocr.load_letter(photo).looks_bad          # -> "take the photo again", no crash


def test_halves_overlap_and_cover_the_page():
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (100, 200), "white").save(buf, format="PNG")
    top, bottom = (Image.open(io.BytesIO(b)) for b in ocr._halves(buf.getvalue()))
    assert top.size[1] + bottom.size[1] > 200                         # they overlap
    assert top.size[0] == bottom.size[0] == 100


def test_user_sees_stuck_message_not_is_ollama_running():
    from amt_lotse.app import UI, _error

    for lang, t in UI.items():
        assert _error(ModelLoopError("x"), t) == t["stuck"], lang
    assert "Ollama" in _error(ConnectionError("refused"), UI["en"])
