"""Amt-Lotse command line: explain a German official letter in simple words.

Usage:
    uv run amt-lotse data/eval/mahnung_01.txt
    uv run amt-lotse data/eval/mahnung_01.txt --lang fr
    uv run amt-lotse data/eval/mahnung_01.txt --lang ar --speak     (read aloud)
    uv run amt-lotse photo_of_letter.jpg --lang ar --speak          (photo / scan / PDF)
    uv run amt-lotse seite1.jpg seite2.jpg anlage.pdf                (several pages = one letter, in this order)
    uv run amt-lotse data/eval/mahnung_01.txt --reply installments   (draft a German reply)
    uv run amt-lotse data/eval/mahnung_01.txt --ask "What if I don't pay?"   (question, answered from the letter)
    uv run amt-lotse data/eval/mahnung_01.txt --ask-voice question.wav       (spoken question)
"""

import argparse
import os
import re
import sys
from datetime import date
from pathlib import Path

from amt_lotse.extract import (
    MODEL,
    LetterInfo,
    chat,
    extract_letter_info,
    normalize_reference,
    options_for,
    parse_german_amount,
    parse_german_date,
)

LANGUAGES = {"en": "English", "fr": "French", "ar": "Arabic", "de": "simple German (A2 level)"}

# Extraction works well with 3B, but writing in other languages needs a bigger model.
# Override with: $env:AMT_LOTSE_EXPLAIN_MODEL="qwen2.5:3b"
EXPLAIN_MODEL = os.environ.get("AMT_LOTSE_EXPLAIN_MODEL", "qwen2.5:7b")

ARABIC_SCRIPT = re.compile(r"[\u0600-\u06FF]")
# Qwen sometimes leaks characters from other scripts (Korean, Chinese, Thai, Hindi, ...).
# Allowed: Latin (incl. German umlauts and French accents), Arabic, digits, punctuation, € and spaces.
FOREIGN_SCRIPT = re.compile(
    r"[^\u0000-\u024F\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF\u2000-\u206F\u20AC\s]"
)


def safe(parse, text):
    if not text:
        return None
    try:
        return parse(text)
    except (ValueError, ArithmeticError):
        return None


def days_left_text(deadline: date) -> str:
    days = (deadline - date.today()).days
    if days < 0:
        return f"⚠ {-days} days OVERDUE"
    if days == 0:
        return "⚠ TODAY"
    return f"in {days} days"


def ask_explanation(letter: str, info: LetterInfo, language: str) -> str:
    response = chat(
        model=EXPLAIN_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    f"You explain German official letters to international students. "
                    f"You ALWAYS answer in {language}, never in German (unless asked for German). "
                    "Write 3 to 4 short, simple sentences: who sent it, what it is about, "
                    "and exactly what the reader has to do. "
                    "If the letter says what happens if the reader does not act, explain that too. "
                    "If the letter does not say it, do not write anything about consequences: "
                    "never claim that nothing will happen. "
                    "Only use facts from the letter. Never add details that are not in the letter. "
                    "Write names of people, cities and companies exactly as in the letter, in Latin letters. "
                    "Keep German official terms (e.g. Krankenkasse, Bürgergeld, Mahnung) "
                    "and add a short explanation in brackets."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Letter:\n\n{letter}\n\n"
                    f"Facts (trust these): deadline={info.deadline_text}, "
                    f"amount={info.amount_text if info.recipient_must_pay else None}, "
                    f"money_direction={info.money_direction}.\n\n"
                    f"Now explain this letter in {language}. Answer only in {language}."
                ),
            },
        ],
        options=options_for(letter),
    )
    return response["message"]["content"].strip()


def is_in_language(text: str, lang_code: str) -> bool:
    """Cheap check that the model really answered in the requested language."""
    if FOREIGN_SCRIPT.search(text):
        return False
    if lang_code == "ar":
        # count letters only: digits, dates and "€" are the same in every language
        # (a short answer like "ادفع 56,13 € قبل 04.12.2026." is clearly Arabic)
        letters = [c for c in text if c.isalpha()]
        return len(ARABIC_SCRIPT.findall(text)) > len(letters) * 0.3
    if lang_code in ("en", "fr"):
        german_markers = len(re.findall(r"\b(der|die|das|und|ist|nicht|wird|Sie)\b", text))
        return german_markers < 3
    return True


def explain(letter: str, info: LetterInfo, lang_code: str) -> str:
    """Second LLM call: a short, friendly explanation. Retries once if the language is wrong."""
    language = LANGUAGES[lang_code]
    text = ask_explanation(letter, info, language)
    if not is_in_language(text, lang_code):
        text = ask_explanation(letter, info, language)
    if not is_in_language(text, lang_code):
        text += f"\n\n(⚠ The model did not answer in {language}. Try a bigger model.)"
    return text


def main() -> None:
    parser = argparse.ArgumentParser(prog="amt-lotse", description="Explain a German official letter.")
    parser.add_argument("letter", type=Path, nargs="+",
                        help="the letter: .txt, .pdf or a photo (.jpg/.png); several files = pages of one letter")
    parser.add_argument("--lang", choices=LANGUAGES, default="en", help="language of the explanation")
    parser.add_argument("--speak", action="store_true",
                        help="read the summary aloud (for blind and older people) and save it as .wav")
    parser.add_argument("--normal-speed", action="store_true", help="speak at normal speed (default: slower)")
    parser.add_argument("--no-play", action="store_true", help="only save the .wav file, do not play it")
    parser.add_argument("--reply", choices=["more-time", "installments", "already-paid", "reschedule", "question"],
                        help="also draft a reply letter in formal German")
    parser.add_argument("--note", help="your own information for the reply, in any language "
                                       "(e.g. 'I am sick until 10 December')")
    parser.add_argument("--ask", metavar="QUESTION",
                        help="a question about the letter, in your language; answered only from the letter")
    parser.add_argument("--ask-voice", metavar="AUDIO", type=Path,
                        help="the same, as a recording (.wav/.mp3/.m4a); turned into text offline")
    args = parser.parse_args()

    for f in args.letter:
        if not f.exists():
            sys.exit(f"File not found: {f}")
    first = args.letter[0]          # names of saved files (audio, reply, OCR text) come from the first page
    from amt_lotse.ocr import load_letters

    loaded = load_letters(args.letter)
    letter = loaded.text

    if loaded.ocr_pages:
        # Save what the vision model read, so a helper can compare it with the paper letter.
        ocr_path = first.with_suffix(".ocr.txt")
        ocr_path.write_text(letter, encoding="utf-8")
        print(f"Text read from the {'scan' if loaded.source != 'ocr' else 'photo'}: {ocr_path}\n")

    if loaded.looks_bad:
        if loaded.bad_pages:
            names = ", ".join(args.letter[i - 1].name for i in loaded.bad_pages if i <= len(args.letter))
            reason = f"unreadable: {names}"
        else:
            reason = "the text was cut off" if loaded.truncated else "too little text was found"
        print(f"⚠ Could not read the whole letter ({reason}). "
              "Take the photo again: good light, whole page, phone straight above it.")
        if args.speak:
            from amt_lotse.speak import TEXT, speak
            speak(TEXT[args.lang]["bad_photo"], args.lang, first.stem,
                  slow=not args.normal_speed, play=not args.no_play)
        sys.exit(1)

    pages = f" ({loaded.pages} pages)" if loaded.pages > 1 else ""
    print(f"Reading {first.name}{pages} with {MODEL} (explanation: {EXPLAIN_MODEL}) ...\n", flush=True)
    if loaded.cut:
        print("⚠ This letter is very long: only the first pages were read.\n")
    info = extract_letter_info(letter)

    deadline = safe(parse_german_date, info.deadline_text) if info.recipient_has_deadline else None
    amount = safe(parse_german_amount, info.amount_text) if info.recipient_must_pay else None
    # Never tell someone "you pay nothing" if there IS a payment we just could not read.
    amount_unclear = info.recipient_must_pay and amount is None
    reference = normalize_reference(info.reference_number) if info.reference_number else None

    print("=" * 60)
    print(f"  From:       {info.sender}")
    print(f"  Subject:    {info.subject}")
    if deadline:
        print(f"  Deadline:   {deadline:%d.%m.%Y}  ({days_left_text(deadline)})")
    else:
        print("  Deadline:   none")
    if amount is not None:
        print(f"  You pay:    {amount:.2f} €".replace(".", ","))
    elif amount_unclear:
        print("  You pay:    ⚠ an amount, but it could not be read – check the letter")
    elif info.money_direction == "recipient_receives":
        print(f"  You get:    {info.amount_text} (no payment needed)")
    else:
        print("  You pay:    nothing")
    if reference:
        print(f"  Reference:  {reference}  (always quote this number)")
    print("=" * 60)

    print("\nWhat this means:\n", flush=True)
    explanation = explain(letter, info, args.lang)
    print(explanation)
    print("\n(Automatic summary – always double-check the original letter.)")

    question = args.ask
    if args.ask_voice:
        from amt_lotse.listen import transcribe

        print("\nListening to your question ...", flush=True)
        question = transcribe(str(args.ask_voice), args.lang)
        print(f"You asked: {question}")
    if question:
        from amt_lotse.ask import answer_question

        answer = answer_question(letter, info, question, args.lang)
        print(f"\nQuestion: {answer.question}\nAnswer:   {answer.text}")

    if args.reply:
        from amt_lotse.reply import build_reply

        print("\nWriting a reply draft ...", flush=True)
        draft = build_reply(letter, info, reference, args.reply, LANGUAGES[args.lang], args.note)
        reply_dir = Path(__file__).resolve().parents[2] / "replies"
        reply_dir.mkdir(exist_ok=True)
        reply_path = reply_dir / f"{first.stem}_{args.reply}.txt"
        reply_path.write_text(draft.german, encoding="utf-8")

        print("\n" + "-" * 60)
        print(draft.german)
        print("-" * 60)
        print(f"\n{draft.summary}")
        for warning in draft.warnings:
            print(f"⚠ {warning}")
        print(f"\nReply saved: {reply_path}")

    if args.speak:
        from amt_lotse.speak import SpokenFacts, build_script, speak

        facts = SpokenFacts(
            amount_unclear=amount_unclear,
            sender=info.sender,
            deadline=deadline,
            amount=amount,
            receives=(
                safe(parse_german_amount, info.amount_text)
                if info.money_direction == "recipient_receives"
                else None
            ),
            reference=reference,
        )
        script = build_script(facts, explanation.split("\n\n(⚠")[0], args.lang)
        print("\nCreating audio ...", flush=True)
        path = speak(script, args.lang, first.stem,
                     slow=not args.normal_speed, play=not args.no_play)
        print(f"Audio saved: {path}")


if __name__ == "__main__":
    main()
