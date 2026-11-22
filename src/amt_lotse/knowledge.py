"""RAG: checked background knowledge about German official terms, added to the prompt when a letter uses them.

Why: the models sometimes get the MEANING of official terms wrong, for example
  - "Einspruch within one month after Bekanntgabe"  ->  "within one month of the letter's date" (wrong start)
  - an Einspruch against a tax decision                ->  forgetting that the tax must still be paid
  - "Inkassounternehmen" (private debt collector)      ->  "enforcement agency" (sounds like the state)
Each entry in knowledge/*.md explains one term correctly, with sources. Entries contain no amounts,
percentages or dates: those change over time, and the letter itself says what applies.

An entry has two parts: the MEANING of the term, and lines starting with "Tip:" (what someone can do).
Explanations only get the meaning: in the first evaluation with RAG the model turned tips into statements
about the letter ("failure to respond may result in a reminder letter"). Answers to questions get both,
because "what if I can't send the documents in time?" is exactly what a tip answers.

Retrieval is keyword-based on purpose: official letters use fixed legal words, so matching those words
finds the right entry reliably, needs no extra model, and is easy to test and to explain.
"""

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

KNOWLEDGE_DIR = Path(__file__).resolve().parent / "knowledge"
MAX_ENTRIES = 3          # more background makes small models drift away from the letter


@dataclass(frozen=True)
class Entry:
    id: str
    title: str
    triggers: tuple[str, ...]
    meaning: str
    tips: tuple[str, ...]
    sources: tuple[str, ...]

    @property
    def text(self) -> str:
        return "\n".join([self.meaning, *(f"Tip: {t}" for t in self.tips)])


def _parse(path: Path) -> Entry:
    head, text = path.read_text(encoding="utf-8").split("\n---\n", 1)
    fields = dict(line.split(": ", 1) for line in head.splitlines() if ": " in line)
    lines = text.strip().splitlines()
    return Entry(
        id=path.stem,
        title=fields["title"].strip(),
        triggers=tuple(t.strip() for t in fields["triggers"].split(",") if t.strip()),
        meaning="\n".join(ln for ln in lines if not ln.startswith("Tip:")).strip(),
        tips=tuple(ln.removeprefix("Tip:").strip() for ln in lines if ln.startswith("Tip:")),
        sources=tuple(fields.get("sources", "").split()),
    )


@lru_cache(maxsize=1)
def entries() -> tuple[Entry, ...]:
    return tuple(_parse(p) for p in sorted(KNOWLEDGE_DIR.glob("*.md")))


def _hits(trigger: str, letter: str) -> int:
    # word start, any ending: "Inkasso" also finds "Inkassounternehmen", "Einspruch" finds "Einspruchsfrist"
    return len(re.findall(r"(?<![\wäöüß])" + re.escape(trigger), letter, re.IGNORECASE))


def retrieve(letter: str, k: int = MAX_ENTRIES) -> list[Entry]:
    """The entries whose terms appear in the letter, best first. Longer (more specific) terms count more."""
    scored = []
    for entry in entries():
        score = sum(min(_hits(t, letter), 3) * len(t) for t in entry.triggers)
        if score:
            scored.append((-score, entry.id, entry))
    return [e for _, _, e in sorted(scored)[:k]]


def enabled() -> bool:
    """AMT_LOTSE_RAG=0 switches the background off (used to measure what RAG changes)."""
    return os.environ.get("AMT_LOTSE_RAG", "1") != "0"


def background(letter: str, tips: bool = False) -> str:
    """The prompt block, or "" when nothing matches or RAG is switched off.
    tips=False for explanations (meaning only), tips=True for answers to questions."""
    if not enabled():
        return ""
    found = retrieve(letter)
    if not found:
        return ""
    notes = "\n\n".join(f"[{e.title}]\n{e.text if tips else e.meaning}" for e in found)
    return (
        "Background notes (checked facts about German official terms in this letter). "
        "Use them to explain these terms CORRECTLY. They are general knowledge, not part of the letter: "
        "never take dates, amounts or deadlines from them, never present them as something the letter says, "
        "and do not add consequences the letter does not state.\n\n"
        + notes
    )
