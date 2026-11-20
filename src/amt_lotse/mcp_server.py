"""Amt-Lotse as an MCP server: AI assistants (Claude Desktop, IDEs, local agents) can use it as tools.

Start (stdio, the way MCP clients launch it):
    uv run amt-lotse-mcp

Privacy
- Everything heavy runs locally: OCR, fact extraction, the code checks and the explanation (Ollama).
- By default the tools return RESULTS (facts, explanation, reply draft), not the full letter text.
  `read_letter_text` returns the whole text and is a separate, explicit tool.
- If the assistant you connect is a cloud model, whatever a tool returns is sent to that cloud model.

Security
- Only files inside the allowed folders can be read (default: the project's data/ folder and
  Documents/Briefe). Change with AMT_LOTSE_LETTER_DIRS (folders separated by ';' on Windows, ':' elsewhere).
"""

import contextlib
import os
import re
import sys
from pathlib import Path
from typing import Literal

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError  # message is shown to the assistant
from mcp.types import ToolAnnotations

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LETTER_TYPES = {".txt", ".pdf", ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
Language = Literal["en", "fr", "ar", "de"]
Intent = Literal["more-time", "installments", "already-paid", "reschedule", "question"]

server = MCPServer(
    "amt-lotse",
    title="Amt-Lotse",
    description="Explains German official letters (Behördenbriefe) locally: deadline, amount, what to do, reply drafts.",
    instructions=(
        "Use these tools when the user has a German official letter (from Jobcenter, Finanzamt, Krankenkasse, "
        "Ausländerbehörde, landlord, Beitragsservice, ...) as a file. Start with list_letters if you do not know "
        "the path. get_letter_facts returns code-checked facts (deadline, amount, reference number) and one "
        "'what_to_do' sentence: prefer these facts over your own reading of the letter. explain_letter adds a "
        "plain-language explanation in en/fr/ar/de. draft_reply writes a formal German reply with [placeholders] "
        "the user must fill in; never fill placeholders with invented values. Remind the user that this is not "
        "legal advice and that the original letter must be checked."
    ),
    version="0.1.0",
)

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
WRITES_FILE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)


# ---------------------------------------------------------------- helpers
def allowed_dirs() -> list[Path]:
    configured = os.environ.get("AMT_LOTSE_LETTER_DIRS")
    if configured:
        dirs = [Path(p).expanduser() for p in configured.split(os.pathsep) if p.strip()]
    else:
        dirs = [PROJECT_ROOT / "data", Path.home() / "Documents" / "Briefe"]
    return [d.resolve() for d in dirs if d.exists()]


def resolve_letter(path: str) -> Path:
    """Only letters inside the allowed folders. Blocks ../ tricks and links pointing elsewhere."""
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    p = p.resolve()
    if not any(p.is_relative_to(d) for d in allowed_dirs()):
        folders = ", ".join(str(d) for d in allowed_dirs()) or "(none exist)"
        raise ToolError(f"Not allowed: {path}. Letters must be inside: {folders}. "
                         "Set AMT_LOTSE_LETTER_DIRS to allow another folder.")
    if not p.is_file():
        raise ToolError(f"File not found: {p}")
    if p.suffix.lower() not in LETTER_TYPES:
        raise ToolError(f"Unsupported file type {p.suffix}. Use: {', '.join(sorted(LETTER_TYPES))}")
    return p


@contextlib.contextmanager
def quiet_stdout():
    """stdio MCP uses stdout for the protocol: progress prints from the pipeline must go to stderr."""
    with contextlib.redirect_stdout(sys.stderr):
        yield


_cache: dict[tuple[str, float], object] = {}


def analyze_cached(p: Path):
    """The models are slow: analyse each file version only once per server run."""
    from amt_lotse.pipeline import analyze

    key = (str(p), p.stat().st_mtime)
    if key not in _cache:
        with quiet_stdout():
            _cache[key] = analyze(p)
    return _cache[key]


def _plain(html: str) -> str:
    text = re.sub(r"</div>", " ", html)          # block ends -> space
    text = re.sub(r"<[^>]+>", "", text)           # inline tags like <b> -> nothing
    return re.sub(r"\s+", " ", text).strip()


def _facts(p: Path, language: str) -> dict:
    from datetime import date

    from amt_lotse.pipeline import todo_box

    a = analyze_cached(p)
    if a.looks_bad:
        return {"file": str(p), "readable": False,
                "problem": "The letter could not be read well (bad photo or text cut off). Ask the user for a "
                           "new photo: good light, whole page, phone held straight above it."}
    days_left = (a.deadline - date.today()).days if a.deadline else None
    return {
        "file": str(p),
        "readable": True,
        "sender": a.info.sender,
        "subject": a.info.subject,
        "what_to_do": _plain(todo_box(a, language)),
        "deadline": a.deadline.isoformat() if a.deadline else None,
        "days_left": days_left,
        "amount_to_pay_eur": str(a.amount) if a.amount is not None else None,
        "amount_to_receive_eur": str(a.receives) if a.receives is not None else None,
        "amount_unclear": a.amount_unclear,
        "reference_number": a.reference,
        "read_with_ocr": a.ocr_used,
        "note": "Deadline, amounts and reference number are checked by rules, not only by the language model.",
    }


# ---------------------------------------------------------------- tools
@server.tool(annotations=READ_ONLY)
def list_letters() -> dict:
    """List letter files (text, PDF, photos) in the allowed folders."""
    letters = []
    for d in allowed_dirs():
        for f in sorted(d.rglob("*")):
            if f.is_file() and f.suffix.lower() in LETTER_TYPES and not f.name.endswith(".ocr.txt"):
                letters.append({"path": str(f), "name": f.name, "folder": str(f.parent)})
    return {"allowed_folders": [str(d) for d in allowed_dirs()], "letters": letters[:200]}


@server.tool(annotations=READ_ONLY)
def get_letter_facts(path: str, language: Language = "en") -> dict:
    """Code-checked key facts of a German official letter: sender, deadline, days left, amount to pay or
    receive, reference number, and one 'what_to_do' sentence in the chosen language. Runs fully locally."""
    return _facts(resolve_letter(path), language)


@server.tool(annotations=READ_ONLY)
def explain_letter(path: str, language: Language = "en") -> dict:
    """Facts plus a short plain-language explanation of the letter (en, fr, ar or de), written by a local model."""
    from amt_lotse.cli import explain

    p = resolve_letter(path)
    facts = _facts(p, language)
    if not facts["readable"]:
        return facts
    with quiet_stdout():
        explanation = explain(analyze_cached(p).text, analyze_cached(p).info, language).split("\n\n(⚠")[0]
    return {**facts, "explanation": explanation,
            "disclaimer": "Automatic summary, not legal advice. Check the original letter."}


@server.tool(annotations=READ_ONLY)
def draft_reply(path: str, intent: Intent, note: str | None = None, language: Language = "en") -> dict:
    """Draft a formal German reply letter. intent: more-time, installments, already-paid, reschedule, question.
    note: the user's own facts in any language (e.g. 'I am sick until 10 December'). Unknown details stay as
    [placeholders] that the user must fill in; numbers not found in the letter or note are replaced by placeholders."""
    from amt_lotse.cli import LANGUAGES
    from amt_lotse.reply import build_reply

    p = resolve_letter(path)
    a = analyze_cached(p)
    if a.looks_bad:
        return _facts(p, language)
    with quiet_stdout():
        draft = build_reply(a.text, a.info, a.reference, intent, LANGUAGES[language], note)
    return {"reply_german": draft.german, "summary": draft.summary, "warnings": draft.warnings}


@server.tool(annotations=WRITES_FILE)
def create_calendar_reminder(path: str, language: Language = "en") -> dict:
    """Create an .ics calendar file for the letter's deadline, with reminders 3 days and 1 day before.
    Returns the file path; the user can open it to add the event to any calendar app."""
    from amt_lotse.pipeline import calendar_file

    p = resolve_letter(path)
    a = analyze_cached(p)
    ics = None if a.looks_bad else calendar_file(a, language)
    if not ics:
        return {"created": False, "reason": "This letter has no deadline (or could not be read)."}
    return {"created": True, "file": ics, "deadline": a.deadline.isoformat()}


@server.tool(annotations=READ_ONLY)
def read_letter_text(path: str) -> dict:
    """Return the FULL text of the letter (OCR for photos/scans). Only use this if the user asks about details
    the other tools do not cover: the whole letter, including personal data, is then shared with the assistant."""
    p = resolve_letter(path)
    a = analyze_cached(p)
    return {"text": a.text, "read_with_ocr": a.ocr_used, "readable": not a.looks_bad}


def main() -> None:
    server.run("stdio")


if __name__ == "__main__":
    main()
