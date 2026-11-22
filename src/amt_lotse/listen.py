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


SAMPLE_RATE = 16_000   # what Whisper expects


def load_audio(audio_path: str):
    """Any recording (.wav from the browser, .mp3, .m4a, .webm ...) -> 16 kHz mono float32 samples.

    We decode it ourselves instead of letting faster-whisper do it: faster-whisper 1.2.1 passes
    `metadata_errors=` to av.open(), which PyAV 19 no longer accepts ("unexpected keyword argument").
    This works with old and new PyAV versions."""
    import av
    import numpy as np

    resampler = av.audio.resampler.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
    chunks = []
    with av.open(audio_path, mode="r") as container:
        for frame in container.decode(audio=0):
            frame.pts = None
            chunks.extend(f.to_ndarray() for f in resampler.resample(frame))
        chunks.extend(f.to_ndarray() for f in resampler.resample(None))   # flush the last samples
    if not chunks:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(chunks, axis=1).reshape(-1).astype(np.float32) / 32768.0


def transcribe(audio_path: str, lang: str | None = None) -> str:
    """Speech -> text. `lang` is a hint; people may still speak another language, Whisper copes with that."""
    audio = load_audio(audio_path)
    if audio.size < SAMPLE_RATE // 4:        # under a quarter second: nothing was said
        return ""
    segments, _info = _model().transcribe(
        audio,
        language=WHISPER_LANG.get(lang or "", None),
        vad_filter=True,          # cut silence and background noise before recognising
        beam_size=5,
        condition_on_previous_text=False,
    )
    return " ".join(s.text.strip() for s in segments).strip()
