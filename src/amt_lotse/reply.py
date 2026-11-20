"""Draft a reply letter in formal German, plus a short explanation in the user's language.

The frame of the letter (addresses, reference number, dates, subject, greeting, closing)
is built by code from the checked extraction. The LLM only writes the short body.
Anything the tool cannot know (your name, a new date, an amount you can pay) stays
as a [placeholder] that you fill in yourself before sending.
"""

import re
from dataclasses import dataclass
from datetime import date

from amt_lotse.extract import DATE_PATTERN, LetterInfo, client

INTENTS = {
    "more-time": {
        "subject": "Bitte um Fristverlängerung",
        "task": "Politely ask for more time (a later deadline). Ask for a new deadline [neues Datum].",
        "label": "Ask for more time",
    },
    "installments": {
        "subject": "Antrag auf Ratenzahlung",
        "task": (
            "Politely ask to pay the amount in monthly installments of [Betrag] euros, "
            "starting on [Datum]. Say that paying everything at once is currently not possible."
        ),
        "label": "Ask to pay in installments",
    },
    "already-paid": {
        "subject": "Zahlung bereits erfolgt",
        "task": (
            "Say that the amount was already paid on [Datum der Zahlung] by bank transfer, "
            "and ask them to check their records. Mention that a proof of payment is attached."
        ),
        "label": "Say you already paid",
    },
    "reschedule": {
        "subject": "Bitte um einen neuen Termin",
        "task": (
            "Say that the reader cannot attend the appointment because of [Grund], "
            "and politely ask for a new appointment."
        ),
        "label": "Ask for a new appointment",
    },
    "question": {
        "subject": "Rückfrage zu Ihrem Schreiben",
        "task": "Say that the letter is not fully clear and politely ask them to explain [Ihre Frage].",
        "label": "Ask a question about the letter",
    },
}

GREETING_OR_CLOSING = re.compile(
    r"^\s*(sehr geehrte|mit freundlichen grüßen|freundliche grüße|hochachtungsvoll|viele grüße)",
    re.IGNORECASE,
)
PLACEHOLDER = re.compile(r"\[[^\]]+\]")
AMOUNT_OR_DATE = re.compile(r"\d{1,2}\.\d{1,2}\.\d{2,4}|\d+(?:\.\d{3})*,\d{2}")


@dataclass
class ReplyDraft:
    german: str      # the full letter, ready to copy, with [placeholders]
    summary: str     # what the letter says, in the user's language
    warnings: list[str]


def letter_date(letter: str) -> str | None:
    """The date the letter was written, e.g. 'Musterstadt, 20.11.2026' -> '20.11.2026'."""
    match = re.search(r",\s*(" + DATE_PATTERN.pattern + r")", letter)
    return match.group(1) if match else None


def _write_body(letter: str, info: LetterInfo, intent: str, note: str | None) -> str:
    note_text = f"\nThe reader adds this personal information (use it, translate it to German): {note}" if note else ""
    response = client.chat(
        model=_explain_model(),
        messages=[
            {
                "role": "system",
                "content": (
                    "You write the body of a short, polite, formal German reply letter (Sie-Form) "
                    "to a German authority or company. Write 3 to 5 sentences. "
                    "Do NOT write a greeting, a closing, addresses, a date or a subject line. "
                    "Do NOT invent facts: no new dates, amounts, reasons or names. "
                    "Everything that is unknown stays as a placeholder in square brackets, "
                    "exactly as given in the task, e.g. [Datum] or [Grund]. "
                    "Output only the German body text."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Original letter:\n\n{letter}\n\n"
                    f"Task: {INTENTS[intent]['task']}"
                    f"{note_text}\n\n"
                    "Write the German body now."
                ),
            },
        ],
        options={"temperature": 0},
    )
    return _clean_body(response["message"]["content"])


def _clean_body(text: str) -> str:
    """Remove greetings/closings the model added anyway (the frame adds its own)."""
    text = re.sub(r"\s*(mit freundlichen grüßen|freundliche grüße|hochachtungsvoll)[\s,.!]*$", "",
                  text.strip(), flags=re.IGNORECASE)
    lines = [line for line in text.splitlines() if not GREETING_OR_CLOSING.match(line)]
    return "\n".join(lines).strip()


def _summarize(german: str, language: str) -> str:
    response = client.chat(
        model=_explain_model(),
        messages=[
            {
                "role": "system",
                "content": (
                    f"Explain in {language}, in 2 simple sentences, what this German reply letter asks for. "
                    "Do not list the placeholders, they are shown separately. "
                    f"Answer only in {language}."
                ),
            },
            {"role": "user", "content": german},
        ],
        options={"temperature": 0},
    )
    return response["message"]["content"].strip()


def _explain_model() -> str:
    from amt_lotse.cli import EXPLAIN_MODEL  # same model as the explanation
    return EXPLAIN_MODEL


def _invented_numbers(body: str, letter: str, note: str | None) -> list[str]:
    """Dates/amounts in the body that appear neither in the original letter nor in the user's note."""
    allowed = letter + " " + (note or "")
    return [x for x in AMOUNT_OR_DATE.findall(body) if x not in allowed]


def build_reply(letter: str, info: LetterInfo, reference: str | None, intent: str,
                language: str, note: str | None = None) -> ReplyDraft:
    warnings = []

    body = _write_body(letter, info, intent, note)
    invented = _invented_numbers(body, letter, note)
    if invented:  # try once more, then warn
        body = _write_body(letter, info, intent, note)
        invented = _invented_numbers(body, letter, note)
        if invented:
            warnings.append(f"The draft contains numbers that are not in the letter: {', '.join(invented)}. Check them.")

    sent_on = letter_date(letter)
    ref_line = f"Ihr Zeichen / Nummer: {reference}" if reference else "Ihr Zeichen: [Nummer aus dem Brief]"
    letter_ref = f"Ihr Schreiben vom {sent_on}" if sent_on else "Ihr Schreiben vom [Datum des Briefes]"

    german = "\n".join([
        "[Ihr Vorname Nachname]",
        "[Ihre Straße und Hausnummer]",
        "[PLZ Ort]",
        "",
        info.sender,
        "[Adresse aus dem Briefkopf]",
        "",
        f"[Ort], {date.today():%d.%m.%Y}",
        "",
        ref_line,
        letter_ref,
        "",
        INTENTS[intent]["subject"],
        "",
        "Sehr geehrte Damen und Herren,",
        "",
        body,
        "",
        "Mit freundlichen Grüßen",
        "",
        "[Unterschrift]",
        "[Ihr Vorname Nachname]",
    ])

    summary = _summarize(german, language)
    # The list of what is still missing comes from code, not from the model.
    missing = list(dict.fromkeys(PLACEHOLDER.findall(german)))
    if missing:
        warnings.append("Fill in before sending: " + ", ".join(missing))
    return ReplyDraft(german, summary, warnings)
