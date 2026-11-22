"""Voice input: recordings are decoded by Amt-Lotse itself (faster-whisper 1.2.1 + PyAV 19 broke that)."""

import math
import struct
import wave

import pytest

from amt_lotse import listen


def _wav(path, seconds, rate=44100, channels=2, freq=440):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = b"".join(
            struct.pack("<h", int(8000 * math.sin(2 * math.pi * freq * i / rate))) * channels
            for i in range(int(seconds * rate))
        )
        w.writeframes(frames)
    return path


def test_browser_recording_becomes_16khz_mono(tmp_path):
    audio = listen.load_audio(str(_wav(tmp_path / "rec.wav", 2)))
    assert audio.dtype.name == "float32" and audio.ndim == 1
    assert abs(audio.size - 2 * listen.SAMPLE_RATE) < 400        # 2 seconds at 16 kHz
    assert 0.1 < abs(audio).max() <= 1.0                          # scaled to -1..1, not silent


def test_too_short_recording_is_empty_text_not_an_error(tmp_path, monkeypatch):
    monkeypatch.setattr(listen, "_model", lambda: pytest.fail("the model must not run for an empty recording"))
    assert listen.transcribe(str(_wav(tmp_path / "click.wav", 0.1))) == ""


def test_whisper_gets_the_decoded_samples(tmp_path, monkeypatch):
    seen = {}

    class FakeWhisper:
        def transcribe(self, audio, **kwargs):
            seen["audio"], seen["language"] = audio, kwargs["language"]
            return iter([type("S", (), {"text": " Was passiert, "})(), type("S", (), {"text": "wenn ich nicht zahle?"})()]), None

    monkeypatch.setattr(listen, "_model", lambda: FakeWhisper())
    text = listen.transcribe(str(_wav(tmp_path / "q.wav", 1)), "de")
    assert text == "Was passiert, wenn ich nicht zahle?"
    assert seen["language"] == "de" and not isinstance(seen["audio"], str)    # samples, not a file path
