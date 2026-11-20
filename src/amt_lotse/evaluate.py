import json
import time
from decimal import Decimal
from pathlib import Path

from amt_lotse.extract import (
    MODEL,
    LetterInfo,
    extract_letter_info,
    normalize_reference,
    parse_german_amount,
    parse_german_date,
)

EVAL_DIR = Path(__file__).resolve().parents[2] / "data" / "eval"
FIELDS = ["deadline", "amount_eur", "reference_number"]


def safe(parse, text: str | None):
    """Run a parser, but return None instead of crashing on bad model output."""
    if not text:
        return None
    try:
        return parse(text)
    except (ValueError, ArithmeticError):
        return None


def to_prediction(info: LetterInfo) -> dict:
    """Convert the LLM's raw strings into the same format as *.expected.json."""
    deadline = safe(parse_german_date, info.deadline_text) if info.recipient_has_deadline else None
    amount = safe(parse_german_amount, info.amount_text) if info.recipient_must_pay else None
    ref = normalize_reference(info.reference_number) if info.reference_number else None
    return {
        "deadline": deadline.isoformat() if deadline else None,
        "amount_eur": str(amount) if amount is not None else None,
        "reference_number": ref,
    }


def is_match(field: str, got, expected) -> bool:
    if got is None or expected is None:
        return got == expected
    if field == "amount_eur":
        return Decimal(got) == Decimal(expected)  # "1234.5" == "1234.50"
    return got == expected


def main() -> None:
    total_correct = total_fields = 0
    run_start = time.perf_counter()
    print(f"Model: {MODEL}")

    for expected_path in sorted(EVAL_DIR.glob("*.expected.json")):
        name = expected_path.name.removesuffix(".expected.json")
        letter = (EVAL_DIR / f"{name}.txt").read_text(encoding="utf-8")
        expected = json.loads(expected_path.read_text(encoding="utf-8"))

        print(f"\n=== {name}  (warte auf Modell...)", flush=True)
        start = time.perf_counter()
        try:
            info = extract_letter_info(letter)
            got = to_prediction(info)
        except Exception as e:
            print(f"  ✗ Extraktion fehlgeschlagen: {e}")
            total_fields += len(FIELDS)
            continue
        print(f"  ({time.perf_counter() - start:.1f}s)")

        for field in FIELDS:
            ok = is_match(field, got[field], expected[field])
            total_correct += ok
            total_fields += 1
            mark = "✓" if ok else "✗"
            print(f"  {mark} {field:17} got={got[field]!r:18} expected={expected[field]!r}")

        if any(not is_match(f, got[f], expected[f]) for f in FIELDS):
            # Show what the model really said, so we can see WHY a field failed.
            print(f"    raw: has_deadline={info.recipient_has_deadline} "
                  f"deadline_text={info.deadline_text!r}")
            print(f"         money_direction={info.money_direction} "
                  f"amount_text={info.amount_text!r}")

    if total_fields == 0:
        print("Keine *.expected.json in data/eval gefunden.")
        return
    print(f"\nScore: {total_correct}/{total_fields} Felder korrekt "
          f"({total_correct / total_fields:.0%}) in {time.perf_counter() - run_start:.0f}s")


if __name__ == "__main__":
    main()
