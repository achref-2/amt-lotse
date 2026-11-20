"""The full Amt-Lotse pipeline as plain functions, shared by the web UI.

letter file -> text (OCR if needed) -> checked extraction -> summary card
            -> explanation -> spoken audio -> optional reply draft
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from amt_lotse.extract import (
    LetterInfo,
    extract_letter_info,
    normalize_reference,
    parse_german_amount,
    parse_german_date,
)
from amt_lotse.ocr import load_letter

# Labels for the summary card, in the user's language.
CARD = {
    "en": {"from": "From", "deadline": "Deadline", "none": "no fixed deadline", "days": "in {n} days",
           "today": "TODAY", "overdue": "{n} days overdue", "pay": "You pay", "get": "You get",
           "nothing": "nothing to pay", "unclear": "an amount, but it could not be read – check the letter",
           "ref": "Reference number", "ref_hint": "always give this number"},
    "fr": {"from": "Expéditeur", "deadline": "Date limite", "none": "pas de date limite", "days": "dans {n} jours",
           "today": "AUJOURD'HUI", "overdue": "dépassée depuis {n} jours", "pay": "Vous payez", "get": "Vous recevez",
           "nothing": "rien à payer", "unclear": "un montant, mais il n'a pas pu être lu – vérifiez la lettre",
           "ref": "Numéro de référence", "ref_hint": "indiquez toujours ce numéro"},
    "de": {"from": "Absender", "deadline": "Frist", "none": "keine feste Frist", "days": "in {n} Tagen",
           "today": "HEUTE", "overdue": "seit {n} Tagen vorbei", "pay": "Sie zahlen", "get": "Sie bekommen",
           "nothing": "nichts zu zahlen", "unclear": "ein Betrag, aber er war nicht lesbar – Brief prüfen",
           "ref": "Nummer", "ref_hint": "immer angeben"},
    "ar": {"from": "المرسل", "deadline": "آخر موعد", "none": "لا يوجد موعد محدد", "days": "بعد {n} يوما",
           "today": "اليوم", "overdue": "انتهى منذ {n} يوما", "pay": "عليك دفع", "get": "ستحصل على",
           "nothing": "لا شيء للدفع", "unclear": "يوجد مبلغ لكن لم تمكن قراءته – راجع الرسالة",
           "ref": "الرقم المرجعي", "ref_hint": "اذكره دائما"},
}


def _safe(parse, text):
    if not text:
        return None
    try:
        return parse(text)
    except (ValueError, ArithmeticError):
        return None


@dataclass
class Analysis:
    text: str
    ocr_used: bool
    looks_bad: bool
    truncated: bool
    info: LetterInfo | None = None
    deadline: date | None = None
    amount: Decimal | None = None
    amount_unclear: bool = False
    receives: Decimal | None = None
    reference: str | None = None


def analyze(path: Path, on_step=None) -> Analysis:
    """on_step is called after the letter was read, before the facts are extracted (for progress bars)."""
    loaded = load_letter(path)
    result = Analysis(loaded.text, loaded.ocr_pages > 0, loaded.looks_bad, loaded.truncated)
    if loaded.looks_bad:
        return result

    if on_step:
        on_step()
    info = extract_letter_info(loaded.text)
    result.info = info
    result.deadline = _safe(parse_german_date, info.deadline_text) if info.recipient_has_deadline else None
    result.amount = _safe(parse_german_amount, info.amount_text) if info.recipient_must_pay else None
    result.amount_unclear = info.recipient_must_pay and result.amount is None
    if info.money_direction == "recipient_receives":
        result.receives = _safe(parse_german_amount, info.amount_text)
    result.reference = normalize_reference(info.reference_number) if info.reference_number else None
    return result


def _euro(value: Decimal) -> str:
    return f"{value:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def summary_card(a: Analysis, lang: str) -> str:
    """Markdown card with the checked facts, in the user's language."""
    t = CARD[lang]
    lines = [f"**{t['from']}:** {a.info.sender}"]

    if a.deadline:
        days = (a.deadline - date.today()).days
        when = t["today"] if days == 0 else (t["overdue"].format(n=-days) if days < 0 else t["days"].format(n=days))
        icon = "⚠️" if days <= 7 else "📅"
        lines.append(f"{icon} **{t['deadline']}:** {a.deadline:%d.%m.%Y} ({when})")
    else:
        lines.append(f"📅 **{t['deadline']}:** {t['none']}")

    if a.amount is not None:
        lines.append(f"💶 **{t['pay']}:** {_euro(a.amount)}")
    elif a.amount_unclear:
        lines.append(f"⚠️ **{t['pay']}:** {t['unclear']}")
    elif a.receives is not None:
        lines.append(f"💶 **{t['get']}:** {_euro(a.receives)}")
    else:
        lines.append(f"💶 {t['nothing']}")

    if a.reference:
        lines.append(f"🔢 **{t['ref']}:** `{a.reference}` ({t['ref_hint']})")
    return "\n\n".join(lines)
