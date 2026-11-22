"""Automatic checks for the free-text parts: explanation and reply draft.

Run:
    uv run python -m amt_lotse.evaluate_text                 # English, explanations + replies
    uv run python -m amt_lotse.evaluate_text --lang ar
    uv run python -m amt_lotse.evaluate_text --no-replies --limit 4

No human labels and no "LLM judge": every check is a rule that can be read and trusted.
It uses the same *.expected.json files as evaluate.py (deadline, amount, reference).
"""

import argparse
import json
import re
import time
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from amt_lotse.cli import LANGUAGES, explain, is_in_language
from amt_lotse.extract import DATE_PATTERN, extract_letter_info, normalize_reference
from amt_lotse.reply import _invented_numbers, build_reply
from amt_lotse.speak import MONTHS

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = PROJECT_ROOT / "data" / "eval"
RESULTS_DIR = PROJECT_ROOT / "eval_results"

# Phrases that tell the reader "don't worry" without the letter saying so.
FALSE_REASSURANCE = re.compile(
    r"nothing (will|would) happen|no consequences?|does not (specify|mention|say)|not specified|"
    r"no further action|keine (folgen|konsequenzen)|passiert nichts|"
    r"rien ne se passera|aucune conséquence|ne précise pas|"
    r"لن يحدث شيء|لا توجد عواقب|"
    r"hiçbir şey olmaz|hiçbir sonucu (yok|olmaz)|"
    r"ничего не (будет|произойд[её]т|случится)|никаких последствий|"
    r"нічого не (буде|станеться)|жодних наслідків|"
    r"هیچ اتفاقی نمی‌افتد|هیچ پیامدی ندارد",
    re.IGNORECASE,
)
AMOUNT_ANY = re.compile(r"\d{1,3}(?:[.,  ]\d{3})*[.,]\d{2}(?!\d)")
SENTENCE_END = re.compile(r"[.!?](?:\s|$)")


# ---------- helpers ----------

def to_decimal(text: str) -> Decimal | None:
    """'1.234,56' / '1,234.56' / '56,13' / '56.13' -> Decimal."""
    digits = re.sub(r"[  ]", "", text)
    last_sep = max(digits.rfind(","), digits.rfind("."))
    whole, cents = digits[:last_sep], digits[last_sep + 1:]
    try:
        return Decimal(re.sub(r"[.,]", "", whole) + "." + cents)
    except InvalidOperation:
        return None


def amounts_in(text: str) -> set[Decimal]:
    text = DATE_PATTERN.sub(" ", text)                  # "04.12.2026" is a date, not "04,12 €"
    text = re.sub(r"\d{4}-\d{2}-\d{2}", " ", text)
    return {d for d in (to_decimal(m) for m in AMOUNT_ANY.findall(text)) if d is not None}


def _month_patterns() -> list[tuple[re.Pattern, str]]:
    patterns = []
    for lang, names in MONTHS.items():
        alt = "|".join(re.escape(n) for n in names)
        # "4 December 2026", "4. Dezember 2026", "4 décembre 2026", "4 ديسمبر 2026"
        patterns.append((re.compile(rf"(\d{{1,2}})\.?\s+({alt})\s+(\d{{4}})", re.IGNORECASE), lang + ":dmy"))
        # "December 4, 2026"
        patterns.append((re.compile(rf"({alt})\s+(\d{{1,2}}),?\s+(\d{{4}})", re.IGNORECASE), lang + ":mdy"))
    return patterns


MONTH_PATTERNS = _month_patterns()


def dates_in(text: str) -> set[date]:
    found = set()
    for m in DATE_PATTERN.finditer(text):
        try:
            found.add(datetime.strptime(m.group(), "%d.%m.%Y").date())
        except ValueError:
            pass
    for m in re.finditer(r"\d{4}-\d{2}-\d{2}", text):
        found.add(date.fromisoformat(m.group()))
    for pattern, kind in MONTH_PATTERNS:
        lang, order = kind.split(":")
        names = [n.lower() for n in MONTHS[lang]]
        for m in pattern.finditer(text):
            if order == "dmy":
                day, month, year = m.group(1), m.group(2), m.group(3)
            else:
                month, day, year = m.group(1), m.group(2), m.group(3)
            try:
                found.add(date(int(year), names.index(month.lower()) + 1, int(day)))
            except ValueError:
                pass
    return found


def sentences(text: str) -> int:
    return max(1, len(SENTENCE_END.findall(text.strip())))


# ---------- checks ----------

def check_explanation(text: str, letter: str, expected: dict, lang: str) -> dict:
    exp_deadline = date.fromisoformat(expected["deadline"]) if expected["deadline"] else None
    exp_amount = Decimal(expected["amount_eur"]) if expected["amount_eur"] else None
    said_dates, said_amounts = dates_in(text), amounts_in(text)
    letter_dates, letter_amounts = dates_in(letter), amounts_in(letter)

    checks = {
        "right_language": is_in_language(text, lang),
        "no_invented_dates": said_dates <= letter_dates,
        "no_invented_amounts": said_amounts <= letter_amounts,
        "no_false_reassurance": not FALSE_REASSURANCE.search(text),
    }
    if exp_deadline:
        checks["mentions_deadline"] = exp_deadline in said_dates
    if exp_amount is not None:
        checks["mentions_amount"] = exp_amount in said_amounts
    details = {
        "invented_dates": sorted(str(d) for d in said_dates - letter_dates),
        "invented_amounts": sorted(str(a) for a in said_amounts - letter_amounts),
        "reassurance": (m.group() if (m := FALSE_REASSURANCE.search(text)) else None),
    }
    return {"checks": checks, "details": details}


def choose_intent(expected: dict) -> str:
    if expected["amount_eur"]:
        return "installments"
    if expected["deadline"]:
        return "more-time"
    return "question"


def check_reply(german: str, warnings: list[str], expected: dict, letter: str) -> dict:
    body = german.split("Sehr geehrte Damen und Herren,")[-1].split("Mit freundlichen Grüßen")[0].strip()
    checks = {
        "no_invented_numbers_left": not _invented_numbers(body, letter, None),
        # "wenn wir den Termin verschieben könnten" (you and I) is fine German.
        # It is only wrong if the writer NEVER speaks as one person.
        "first_person_singular": bool(re.search(r"\b(ich|mir|mich|mein\w*)\b", body, re.IGNORECASE)),
        "formal_sie": not re.search(r"\b(du|dich|dir|dein\w*)\b", body, re.IGNORECASE),
        "one_closing": german.count("Mit freundlichen Grüßen") == 1,
        "body_1_to_6_sentences": 1 <= sentences(body) <= 6,
    }
    if expected["reference_number"]:
        checks["includes_reference"] = expected["reference_number"] in german
    guardrail_used = any("were replaced" in w for w in warnings)
    return {"checks": checks, "guardrail_replaced_numbers": guardrail_used, "body": body}


# ---------- main ----------

def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate explanation and reply texts.")
    parser.add_argument("--lang", choices=LANGUAGES, default="en")
    parser.add_argument("--no-replies", action="store_true", help="only check explanations (faster)")
    parser.add_argument("--limit", type=int, help="only the first N letters")
    args = parser.parse_args()

    files = sorted(EVAL_DIR.glob("*.expected.json"))[: args.limit]
    totals: dict[str, list[bool]] = {}
    guardrail_count = 0
    report = []
    start = time.perf_counter()

    for expected_path in files:
        name = expected_path.name.removesuffix(".expected.json")
        letter = (EVAL_DIR / f"{name}.txt").read_text(encoding="utf-8")
        expected = json.loads(expected_path.read_text(encoding="utf-8"))
        print(f"\n=== {name}", flush=True)

        info = extract_letter_info(letter)
        explanation = explain(letter, info, args.lang).split("\n\n(⚠")[0]
        exp_result = check_explanation(explanation, letter, expected, args.lang)
        entry = {"letter": name, "explanation": explanation, **{"explanation_" + k: v for k, v in exp_result.items()}}

        for check, ok in exp_result["checks"].items():
            totals.setdefault("explanation." + check, []).append(ok)
            print(f"  {'✓' if ok else '✗'} explanation.{check}")
        for key, value in exp_result["details"].items():
            if value:
                print(f"      {key}: {value}")

        if not args.no_replies:
            intent = choose_intent(expected)
            reference = normalize_reference(info.reference_number) if info.reference_number else None
            draft = build_reply(letter, info, reference, intent, LANGUAGES[args.lang])
            rep_result = check_reply(draft.german, draft.warnings, expected, letter)
            guardrail_count += rep_result["guardrail_replaced_numbers"]
            entry.update({"reply_intent": intent, "reply": draft.german, "reply_checks": rep_result["checks"],
                          "reply_guardrail_replaced_numbers": rep_result["guardrail_replaced_numbers"]})
            for check, ok in rep_result["checks"].items():
                totals.setdefault("reply." + check, []).append(ok)
                print(f"  {'✓' if ok else '✗'} reply({intent}).{check}")
            if rep_result["guardrail_replaced_numbers"]:
                print("      (the model invented numbers; the guardrail replaced them)")
        report.append(entry)

    print("\n" + "=" * 60)
    print(f"Language: {LANGUAGES[args.lang]}   Letters: {len(files)}   Time: {time.perf_counter() - start:.0f}s\n")
    passed = total = 0
    for check, results in totals.items():
        ok = sum(results)
        passed, total = passed + ok, total + len(results)
        print(f"  {check:42} {ok:2}/{len(results):<2}")
    if not args.no_replies:
        print(f"\n  Replies where the model invented numbers (fixed by guardrail): {guardrail_count}/{len(files)}")
    print(f"\nScore: {passed}/{total} checks passed ({passed / max(total, 1):.0%})")

    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / f"text_eval_{args.lang}_{datetime.now():%Y%m%d_%H%M}.json"
    out.write_text(json.dumps({"lang": args.lang, "totals": {k: [sum(v), len(v)] for k, v in totals.items()},
                               "guardrail_replaced": guardrail_count, "letters": report},
                              ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"Full report: {out}")


if __name__ == "__main__":
    main()
