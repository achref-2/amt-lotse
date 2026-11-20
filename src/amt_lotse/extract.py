import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
import ollama
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LETTER_PATH = PROJECT_ROOT / "data" / "samples" / "example.txt"

DATE_PATTERN = re.compile(r"\d{1,2}\.\d{1,2}\.\d{4}")


class LetterInfo(BaseModel):
    sender: str
    subject: str
    letter_type: str
    required_action: str
    deadline_text: str | None = Field(
        description="Deadline exactly as written in the letter, e.g. '15.12.2026'"
    )
    amount_text: str | None = Field(
        description="Amount exactly as written in the letter, e.g. '55,08 €'"
    )
    reference_number: str | None


def read_letter() -> str:
    return LETTER_PATH.read_text(encoding="utf-8")


def parse_german_date(text: str) -> date:
    """Find a German date (DD.MM.YYYY) anywhere in the text, e.g. 'bis zum 15.12.2026'."""
    match = DATE_PATTERN.search(text)
    if match is None:
        raise ValueError(f"No date found in: {text!r}")
    return datetime.strptime(match.group(), "%d.%m.%Y").date()


def parse_german_amount(text: str) -> Decimal:
    """Convert a German amount like '1.234,56 €' to Decimal('1234.56')."""
    cleaned = text.replace("€", "").replace(".", "").replace(",", ".").strip()
    return Decimal(cleaned)


def extract_letter_info(letter: str) -> LetterInfo:
    response = ollama.chat(
        model="qwen2.5:7b",
        messages=[
            {
                "role": "system",
                "content": (
                    "You extract information from German official letters. "
                    "Only use facts stated in the letter. If something is missing, use null."
                ),
            },
            {"role": "user", "content": f"Extract the information from this letter:\n\n{letter}"},
        ],
        format=LetterInfo.model_json_schema(),
        options={"temperature": 0},
    )
    return LetterInfo.model_validate_json(response["message"]["content"])


if __name__ == "__main__":
    letter = read_letter()
    info = extract_letter_info(letter)

    deadline = parse_german_date(info.deadline_text) if info.deadline_text else None
    amount = parse_german_amount(info.amount_text) if info.amount_text else None

    print(info)
    print("Deadline:", deadline, type(deadline))
    print("Amount:  ", amount, type(amount))