import os
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import ollama
from pydantic import BaseModel, Field

MODEL = os.environ.get("AMT_LOTSE_MODEL", "qwen2.5:7b")
TIMEOUT_SECONDS = 180

PROJECT_ROOT = Path(__file__).resolve().parents[2]  # extract.py -> amt_lotse -> src -> amt-lotse
LETTER_PATH = PROJECT_ROOT / "data" / "eval" / "example.txt"

DATE_PATTERN = re.compile(r"\d{1,2}\.\d{1,2}\.\d{4}")
# Matches a leading label like "Kundennummer:", "Steuernummer", "Aktenzeichen:", "Nr."
REF_LABEL = re.compile(r"^\s*[\w\s-]*?(nummer|nr\.?|zeichen)\s*[:.]?\s*", re.IGNORECASE)

client = ollama.Client(timeout=TIMEOUT_SECONDS)


class LetterInfo(BaseModel):
    sender: str
    subject: str
    letter_type: str
    required_action: str
    deadline_text: str | None = Field(
        description="Deadline for the recipient's action, exactly as written in the letter, e.g. '15.12.2026'"
    )
    amount_text: str | None = Field(
        description=(
            "Amount the recipient must PAY, exactly as written in the letter, e.g. '55,08 €'. "
            "Use null if the recipient does not have to pay anything "
            "(e.g. credits/Guthaben, refunds, prices for information only)."
        )
    )
    recipient_must_pay: bool = Field(
        description=(
            "True only if the recipient has to pay money. "
            "False for credits (Guthaben), refunds, price information or letters without a payment."
        )
    )
    reference_number: str | None = Field(
        description="Only the reference number itself, without its label, e.g. '987 654 321'"
    )


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
    """Convert a German amount like '1.234,56 €' to Decimal('1234.56')."""
    cleaned = text.replace("€", "").replace("EUR", "").replace(".", "").replace(",", ".").strip()
    return Decimal(cleaned)


def extract_letter_info(letter: str) -> LetterInfo:
    response = client.chat(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You extract information from German official letters. "
                    "Only use facts stated in the letter. If something is missing, use null. "
                    "amount_text is only an amount the recipient has to pay."
                ),
            },
            {"role": "user", "content": f"Extract the information from this letter:\n\n{letter}"},
        ],
        format=LetterInfo.model_json_schema(),
        options={"temperature": 0},
    )
    return LetterInfo.model_validate_json(response["message"]["content"])


if __name__ == "__main__":
    print(f"Model: {MODEL}  |  Letter: {LETTER_PATH.relative_to(PROJECT_ROOT)}")
    info = extract_letter_info(read_letter())

    deadline = parse_german_date(info.deadline_text) if info.deadline_text else None
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
