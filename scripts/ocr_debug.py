"""Diagnose OCR loops: shows, live, what the vision model writes before Ollama stops it.

    uv run python scripts/ocr_debug.py data/photos/jobcenter_01_photo.jpg
    uv run python scripts/ocr_debug.py my_photo.jpg --raw      (without grey/contrast preparation)
    uv run python scripts/ocr_debug.py my_photo.jpg --cpu      (without the graphics card: slow, but shows
                                                                 whether the GPU is the problem)

Nothing is saved, nothing leaves the computer.
"""

import argparse
import sys
from pathlib import Path

import ollama

from amt_lotse.extract import client
from amt_lotse.ocr import MAX_SIDE, NUM_CTX, OCR_MODEL, OCR_PROMPT, _shrink_png


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("photo", type=Path)
    parser.add_argument("--raw", action="store_true", help="send the photo without grey/contrast preparation")
    parser.add_argument("--cpu", action="store_true", help="run without the graphics card (num_gpu=0)")
    parser.add_argument("--model", default=OCR_MODEL)
    args = parser.parse_args()

    try:
        version = client._client.get("/api/version").json().get("version")
    except Exception:
        version = "?"
    print(f"Ollama {version} | model {args.model} | photo {args.photo.name} "
          f"({args.photo.stat().st_size // 1024} KB) | {'raw' if args.raw else f'prepared, max {MAX_SIDE}px'}"
          f"{' | CPU only' if args.cpu else ''}")

    image = args.photo.read_bytes() if args.raw else _shrink_png(args.photo.read_bytes())
    print("-" * 70)
    text = ""
    try:
        for chunk in client.chat(model=args.model, stream=True,
                                 messages=[{"role": "user", "content": OCR_PROMPT, "images": [image]}],
                                 options={"temperature": 0, "num_ctx": NUM_CTX,
                                          **({"num_gpu": 0} if args.cpu else {})}):
            piece = chunk["message"]["content"]
            text += piece
            print(piece, end="", flush=True)
            if chunk.get("done"):
                print(f"\n{'-' * 70}\nFINISHED normally ({chunk.get('done_reason')}), {len(text)} characters.")
    except ollama.ResponseError as e:
        print(f"\n{'-' * 70}\nSTOPPED by Ollama after {len(text)} characters: {e}")
        tail = text[-300:]
        print(f"Last part before the stop:\n{tail!r}")


if __name__ == "__main__":
    main()
