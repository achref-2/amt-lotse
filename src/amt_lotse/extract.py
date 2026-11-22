import os
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal

import ollama
from pydantic import BaseModel, Field

MODEL = os.environ.get("AMT_LOTSE_MODEL", "qwen2.5:3b")
TIMEOUT_SECONDS = 180

PROJECT_ROOT = Path(__file__).resolve().parents[2]  # extract.py -> amt_lotse -> src -> amt-lotse
LETTER_PATH = PROJECT_ROOT / "data" / "eval" / "example.txt"

DATE_PATTERN = re.compile(r"\d{1,2}\.\d{1,2}\.\d{4}")
# Matches a leading label like "Kundennummer:", "Steuernummer", "Aktenzeichen:", "Nr."
REF_LABEL = re.compile(r"^\s*[\w\s-]*?(nummer|nr\.?|zeichen)\s*[:.]?\s*", re.IGNORECASE)

# Words that mean the recipient GETS money. Used as a safety net after the LLM.
CREDIT_WORDS = re.compile(
    r"guthaben|erstatt|rückzahlung|zurückzahl|gutschrift|gutgeschrieben|zu ihren gunsten",
    re.IGNORECASE,
)

# A clear request to pay: "Bitte überweisen Sie ...", "zahlen Sie ...", "... ist zu zahlen".
PAY_REQUEST = re.compile(
    r"\b(überweisen|zahlen|bezahlen|begleichen|entrichten)\s+sie\b"
    r"|\bzu\s+(zahlen|bezahlen|überweisen|entrichten)\b",
    re.IGNORECASE,
)
# A price per unit is information, not a bill: "0,32 € pro kWh", "18,36 € monatlich", "12 €/Stunde".
RATE_PATTERN = re.compile(
    r"\b(pro|je)\s+\w+|/\s*(kwh|monat|jahr|stunde|tag|liter|m²|m2|qm)\b|\b(monatlich|jährlich|stündlich)\b",
    re.IGNORECASE,
)
AMOUNT_PATTERN = re.compile(r"\d{1,3}(?:\.\d{3})*,\d{2}\s*(?:€|EUR|Euro)?")

client = ollama.Client(timeout=TIMEOUT_SECONDS)

# Ollama's default context is about 4000 tokens. When a prompt is longer, Ollama silently drops the BEGINNING,
# and page 1 is where the deadline and the amount are. So every call asks for a context that fits the letter.
MIN_CTX, MAX_CTX = 4096, 16384


def options_for(*texts: str) -> dict:
    """temperature 0 + a context window big enough for these texts (German: ~3 characters per token)."""
    needed = sum(len(t) for t in texts) // 3 + 2048      # + room for instructions and the answer
    num_ctx = min(MAX_CTX, max(MIN_CTX, -(-needed // 1024) * 1024))
    return {"temperature": 0, "num_ctx": num_ctx}


class LetterInfo(BaseModel):
    # Field order matters: the model fills them top to bottom.
    # Measured on data/eval with qwen2.5:3b:
    #   - deadline: the yes/no question BEFORE the value works best
    #   - amount:   the value BEFORE the yes/no question works best
    sender: str
    subject: str
    letter_type: str
    required_action: str
    recipient_has_deadline: bool = Field(
        description=(
            "True only if the recipient must DO something by a specific calendar date "
            "(pay, submit documents, reply, attend an appointment). "
            "False if the letter only contains information dates (start of a new price, "
            "validity or billing periods, end of a Bewilligungszeitraum, letter date) "
            "or only a relative period like 'innerhalb von vier Wochen'."
        )
    )
    deadline_text: str | None = Field(
        description=(
            "The date by which the recipient must act or attend an appointment, "
            "exactly as written, e.g. 'bis zum 15.12.2026' or 'am 08.12.2026'. "
            "Never a period, never a date when something changes or ends. "
            "null if recipient_has_deadline is false."
        )
    )
    amount_text: str | None = Field(
        description=(
            "The total amount the recipient must PAY, exactly as written in the letter, e.g. '55,08 €'. "
            "If there are several amounts (e.g. invoice + fees), use the total. "
            "Use null if the recipient does not have to pay anything "
            "(e.g. credits/Guthaben, refunds, prices for information only)."
        )
    )
    money_direction: Literal["recipient_pays", "recipient_receives", "no_payment"] = Field(
        description=(
            "Who gets the money? "
            "'recipient_pays': the recipient must pay or transfer money (Rechnung, Mahnung, Nachzahlung, Gebühr). "
            "'recipient_receives': the recipient GETS money (Guthaben, Erstattung, Rückzahlung). "
            "'no_payment': no money changes hands (information, appointments, documents)."
        )
    )
    reference_number: str | None = Field(
        description="Only the reference number itself, without its label, e.g. '987 654 321'"
    )


def _must_pay(info: "LetterInfo") -> bool:
    return info.money_direction == "recipient_pays"


LetterInfo.recipient_must_pay = property(_must_pay)  # keeps evaluate.py unchanged


def amount_is_credit(letter: str, amount_text: str) -> bool:
    """True if the letter mentions this amount right next to a credit word.

    Looks at the line with the amount plus the line before it,
    e.g. 'Ihr Guthaben beträgt\n64,30 €.' -> True.
    """
    number = re.search(r"\d[\d.]*,\d{2}", amount_text)
    if number is None:
        return False
    lines = letter.splitlines()
    for i, line in enumerate(lines):
        if number.group() in line:
            context = " ".join(lines[max(i - 1, 0) : i + 1])
            if CREDIT_WORDS.search(context):
                return True
    return False


def find_payment_request(letter: str) -> str | None:
    """Return the amount from a sentence that asks the reader to pay, e.g. '312,00 €'.

    Looks at the line with the request and the previous non-empty line (sentences often
    wrap, and the amount is often named just before "Bitte überweisen Sie den Betrag ...").
    The amount on the request line itself wins.
    """
    lines = [line for line in letter.splitlines() if line.strip()]
    for i, line in enumerate(lines):
        if PAY_REQUEST.search(line):
            for candidate in (line, lines[i - 1] if i > 0 else ""):
                amounts = AMOUNT_PATTERN.findall(candidate)
                if amounts:
                    return amounts[-1].strip()
    return None


def normalize_reference(text: str) -> str:
    """Strip a label from a reference number: 'Kundennummer: 7788990' -> '7788990'."""
    return REF_LABEL.sub("", text).strip()


def read_letter(path: Path = LETTER_PATH) -> str:
    return path.read_text(encoding="utf-8")


def parse_german_date(text: str) -> date:
    """Find a German date (DD.MM.YYYY) anywhere in the text, e.g. 'bis zum 15.12.2026'."""
    match = DATE_PATTERN.search(text)
    if match is None:
        raise ValueError(f"No date found in: {text!r}")
    return datetime.strptime(match.group(), "%d.%m.%Y").date()


def parse_german_amount(text: str) -> Decimal:
    """Convert a German amount like '1.234,56 €' to Decimal('1234.56').

    Works even if the € sign is missing or garbled (e.g. '312,00 ?' from a bad PDF/OCR).
    """
    match = re.search(r"\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2}|\d+", text)
    if match is None:
        raise ValueError(f"No amount found in: {text!r}")
    return Decimal(match.group().replace(".", "").replace(",", "."))


def extract_letter_info(letter: str) -> LetterInfo:
    response = client.chat(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You extract information from German official letters. "
                    "Only use facts stated in the letter. If something is missing, use null. "
                    "deadline_text is only a date by which the recipient must act. "
                    "amount_text is only an amount the recipient has to pay."
                ),
            },
            {"role": "user", "content": f"Extract the information from this letter:\n\n{letter}"},
        ],
        format=LetterInfo.model_json_schema(),
        options=options_for(letter),
    )
    info = LetterInfo.model_validate_json(response["message"]["content"])

    # Safety nets: the small model is unreliable on WHO pays. The letter's own wording decides.
    # 1) Amount next to "Guthaben"/"Erstattung" -> the recipient gets money.
    if info.amount_text and amount_is_credit(letter, info.amount_text):
        info.money_direction = "recipient_receives"
        return info
    # 2) A clear request to pay with an amount -> the recipient pays that amount.
    requested = find_payment_request(letter)
    if requested and not amount_is_credit(letter, requested):
        info.money_direction = "recipient_pays"
        info.amount_text = requested
        return info
    # 3) The model says "pays", but the letter contains no euro amount at all -> nothing to pay.
    if info.money_direction == "recipient_pays" and not AMOUNT_PATTERN.search(letter):
        info.money_direction = "no_payment"
        info.amount_text = None
        return info
    # 4) No request to pay, and the model's "amount" is a rate (e.g. "0,32 € pro kWh") -> no bill.
    if info.money_direction == "recipient_pays" and info.amount_text and RATE_PATTERN.search(info.amount_text):
        info.money_direction = "no_payment"
        info.amount_text = None
    return info


if __name__ == "__main__":
    print(f"Model: {MODEL}  |  Letter: {LETTER_PATH.relative_to(PROJECT_ROOT)}")
    info = extract_letter_info(read_letter())

    deadline = (
        parse_german_date(info.deadline_text)
        if info.deadline_text and info.recipient_has_deadline
        else None
    )
    amount = (
        parse_german_amount(info.amount_text)
        if info.amount_text and info.recipient_must_pay
        else None
    )
    reference = normalize_reference(info.reference_number) if info.reference_number else None

    print(info)
    print("Deadline:", deadline, type(deadline))
    print("Amount:  ", amount, type(amount))
    print("Ref:     ", reference)
