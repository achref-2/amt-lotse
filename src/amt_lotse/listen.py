"""Voice input: turns a short recording into text, offline, with faster-whisper.

The model runs on this computer (CPU is enough). It is downloaded once, the first time it is used
(about 0.5 GB for "small"). Change it with:  $env:AMT_LOTSE_WHISPER_MODEL="base"   (smaller, faster)
"""

import os
from functools import lru_cache

WHISPER_MODEL = os.environ.get("AMT_LOTSE_WHISPER_MODEL", "small")

# Amt-Lotse language code -> Whisper language code. A hint makes short questions much more accurate.
WHISPER_LANG = {"en": "en", "fr": "fr", "ar": "ar", "de": "de", "tr": "tr", "uk": "uk", "ru": "ru", "fa": "fa"}


@lru_cache(maxsize=1)
def _model():
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise RuntimeError("Voice input needs faster-whisper. Install it with:  uv add faster-whisper") from e
    print(f"Loading speech recognition '{WHISPER_MODEL}' (downloaded once, the first time) ...", flush=True)
    return WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")


def transcribe(audio_path: str, lang: str | None = None) -> str:
    """Speech -> text. `lang` is a hint; people may still speak another language, Whisper copes with that."""
    segments, _info = _model().transcribe(
        audio_path,
        language=WHISPER_LANG.get(lang or "", None),
        vad_filter=True,          # cut silence and background noise before recognising
        beam_size=5,
        condition_on_previous_text=False,
    )
    return " ".join(s.text.strip() for s in segments).strip()
