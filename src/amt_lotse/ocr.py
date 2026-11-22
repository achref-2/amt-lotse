"""Turn any letter file into text: .txt, .pdf (digital or scanned) or a photo.

- .txt          -> read directly
- .pdf          -> use the PDF's own text; only scanned pages go through OCR
- .jpg/.png/... -> OCR with a local vision model (Qwen2.5-VL via Ollama)
- several files  -> one letter: page photos, a letter plus its attachments (Anlagen), in the given order

Everything stays on this machine.
"""

import io
import os
from dataclasses import dataclass
from pathlib import Path

from amt_lotse.extract import client

OCR_MODEL = os.environ.get("AMT_LOTSE_OCR_MODEL", "qwen2.5vl:3b")

IMAGE_TYPES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
MAX_SIDE = 1600        # px; ~2500 image tokens, fits the context with room for the text
NUM_CTX = 8192         # context window for OCR (image tokens + the transcribed text)
MIN_CHARS = 150        # less text than this = probably a bad photo
PDF_TEXT_MIN = 50      # a PDF page with less text than this is treated as a scan
MAX_CHARS = 40_000     # ~15 pages; beyond this the end is cut (better than the models losing page 1)

OCR_PROMPT = (
    "This is a photo or scan of a German letter. "
    "Transcribe ALL text exactly as written, line by line, from top to bottom. "
    "Keep every number, date, amount, IBAN and reference number exactly. "
    "Keep German umlauts (ä, ö, ü, ß). "
    "Do not translate, do not summarize, do not explain, do not add anything. "
    "Output only the text of the letter."
)


@dataclass
class LetterText:
    text: str
    source: str            # "text", "pdf", "pdf+ocr" or "ocr"
    ocr_pages: int = 0
    truncated: bool = False
    pages: int = 1
    bad_pages: list[int] | None = None   # 1-based numbers of the FILES (photos/scans) that could not be read
    cut: bool = False                    # very long letter: the end was left out

    @property
    def looks_bad(self) -> bool:
        if self.bad_pages:
            return True
        return self.ocr_pages > 0 and (self.truncated or len(self.text.strip()) < MIN_CHARS)


def _shrink_png(image_bytes: bytes) -> bytes:
    """Fix rotation, convert to grayscale, boost contrast and limit the size.

    The size limit matters: every pixel costs model context. Too big an image
    fills the context window and the transcription stops halfway.
    (No automatic cropping: it is too easy to cut off text, which is worse.)
    """
    from PIL import Image, ImageOps

    with Image.open(io.BytesIO(image_bytes)) as img:
        img = ImageOps.autocontrast(ImageOps.exif_transpose(img).convert("L"), cutoff=1)
        img.thumbnail((MAX_SIDE, MAX_SIDE))
        out = io.BytesIO()
        img.save(out, format="PNG")
        return out.getvalue()


def ocr_image(image_bytes: bytes) -> tuple[str, bool]:
    """Returns (text, truncated). truncated=True means the model stopped before the end."""
    response = client.chat(
        model=OCR_MODEL,
        messages=[{"role": "user", "content": OCR_PROMPT, "images": [_shrink_png(image_bytes)]}],
        options={"temperature": 0, "num_ctx": NUM_CTX},
    )
    truncated = response.get("done_reason") == "length"
    return response["message"]["content"].strip(), truncated


def _read_pdf(path: Path) -> LetterText:
    import pymupdf

    pages, ocr_pages, truncated = [], 0, False
    with pymupdf.open(path) as doc:
        for page in doc:
            text = page.get_text().strip()
            if len(text) >= PDF_TEXT_MIN:
                pages.append(text)
            else:
                print(f"  page {page.number + 1}: scanned, running OCR ...", flush=True)
                png = page.get_pixmap(dpi=200).tobytes("png")
                text, cut = ocr_image(png)
                pages.append(text)
                ocr_pages += 1
                truncated = truncated or cut
    text = "\n\n".join(pages)
    return LetterText(text[:MAX_CHARS], "pdf+ocr" if ocr_pages else "pdf", ocr_pages, truncated,
                      pages=len(pages), cut=len(text) > MAX_CHARS)


def load_letters(paths: list[Path]) -> LetterText:
    """Several files = one letter, in this order. Each file is checked on its own, so the user
    can be told exactly which page to photograph again."""
    if len(paths) == 1:
        return load_letter(paths[0])
    parts, bad, ocr_pages, page_no, truncated = [], [], 0, 0, False
    for number, path in enumerate(paths, 1):
        part = load_letter(path)
        if part.looks_bad:
            bad.append(number)
        start = page_no + 1
        page_no += part.pages
        label = f"Seite {start}" if part.pages == 1 else f"Seiten {start}–{page_no}"
        parts.append(f"--- {label} ---\n{part.text.strip()}")
        ocr_pages += part.ocr_pages
        truncated = truncated or part.truncated
    text = "\n\n".join(parts)
    cut = len(text) > MAX_CHARS
    source = "ocr" if ocr_pages == page_no else ("text" if not ocr_pages else "pdf+ocr")
    return LetterText(text[:MAX_CHARS], source, ocr_pages, truncated, page_no, bad or None, cut)


def load_letter(path: Path) -> LetterText:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _read_pdf(path)
    if suffix in IMAGE_TYPES:
        print(f"Reading the photo with {OCR_MODEL} ...", flush=True)
        text, cut = ocr_image(path.read_bytes())
        return LetterText(text, "ocr", ocr_pages=1, truncated=cut)
    return LetterText(path.read_text(encoding="utf-8"), "text")
