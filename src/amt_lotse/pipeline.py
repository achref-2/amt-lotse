"""The full Amt-Lotse pipeline as plain functions, shared by the web UI.

letter file -> text (OCR if needed) -> checked extraction -> summary card
            -> explanation -> spoken audio -> optional reply draft
"""

import tempfile
import uuid
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
from amt_lotse.speak import say_date

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


TODO = {
    "en": {"pay_now": "Pay <b>{amount}</b>.", "pay": "Pay <b>{amount}</b> by <b>{date}</b>.", "date": "Important date: <b>{date}</b>. Read below what to do.",
           "receive": "You will receive <b>{amount}</b>. You do not have to pay anything.",
           "nothing": "No deadline and nothing to pay in this letter.",
           "unclear": "There is an amount to pay, but it could not be read. Please check the letter with someone.",
           "overdue": "The deadline has passed!", "days": "{n} days left", "one_day": "1 day left", "today": "Today!"},
    "fr": {"pay_now": "Payez <b>{amount}</b>.", "pay": "Payez <b>{amount}</b> avant le <b>{date}</b>.", "date": "Date importante : <b>{date}</b>. Lisez ci-dessous ce qu'il faut faire.",
           "receive": "Vous allez recevoir <b>{amount}</b>. Vous n'avez rien à payer.",
           "nothing": "Pas de date limite et rien à payer dans cette lettre.",
           "unclear": "Il y a un montant à payer, mais il n'a pas pu être lu. Vérifiez la lettre avec quelqu'un.",
           "overdue": "La date limite est dépassée !", "days": "encore {n} jours", "one_day": "encore 1 jour", "today": "Aujourd'hui !"},
    "de": {"pay_now": "Zahlen Sie <b>{amount}</b>.", "pay": "Zahlen Sie <b>{amount}</b> bis <b>{date}</b>.", "date": "Wichtiges Datum: <b>{date}</b>. Was zu tun ist, steht unten.",
           "receive": "Sie bekommen <b>{amount}</b>. Sie müssen nichts bezahlen.",
           "nothing": "In diesem Brief gibt es keine Frist und nichts zu bezahlen.",
           "unclear": "Es gibt einen Betrag zu bezahlen, aber er war nicht lesbar. Bitte prüfen Sie den Brief mit jemandem.",
           "overdue": "Die Frist ist vorbei!", "days": "noch {n} Tage", "one_day": "noch 1 Tag", "today": "Heute!"},
    "ar": {"pay_now": "ادفع <b>{amount}</b>.", "pay": "ادفع <b>{amount}</b> قبل <b>{date}</b>.", "date": "تاريخ مهم: <b>{date}</b>. اقرأ في الأسفل ما يجب عليك فعله.",
           "receive": "ستحصل على <b>{amount}</b>. لا يجب عليك دفع أي شيء.",
           "nothing": "لا يوجد موعد نهائي ولا شيء للدفع في هذه الرسالة.",
           "unclear": "يوجد مبلغ للدفع لكن لم تمكن قراءته. من فضلك راجع الرسالة مع شخص ما.",
           "overdue": "لقد انتهى الموعد النهائي!", "days": "بقي {n} يوما", "one_day": "بقي يوم واحد", "today": "اليوم!"},
}


def todo_box(a: Analysis, lang: str) -> str:
    """The one sentence that matters most, built only from checked facts. HTML, red when urgent."""
    t = TODO[lang]
    if a.amount is not None and a.deadline:
        text = t["pay"].format(amount=_euro(a.amount), date=say_date(a.deadline, lang))
    elif a.amount_unclear:
        text = t["unclear"]
    elif a.receives is not None:
        text = t["receive"].format(amount=_euro(a.receives))
    elif a.deadline:
        text = t["date"].format(date=say_date(a.deadline, lang))
    elif a.amount is not None:
        text = t["pay_now"].format(amount=_euro(a.amount))
    else:
        text = t["nothing"]

    urgent, when = False, ""
    if a.deadline:
        days = (a.deadline - date.today()).days
        urgent = days <= 7
        when = t["overdue"] if days < 0 else t["today"] if days == 0 else t["one_day"] if days == 1 else t["days"].format(n=days)
        when = f'<div class="when">{when}</div>'
    css = "todo urgent" if urgent or a.amount_unclear else "todo"
    # dir="auto": the browser picks right-to-left for Arabic, so "." and "€" land on the right side
    return f'<div class="{css}" role="status" dir="auto">{when}<div class="what" dir="auto">{text}</div></div>'


def _ics_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def calendar_file(a: Analysis, lang: str) -> str | None:
    """An .ics file for the deadline, with reminders 3 days and 1 day before. Opens in any calendar app."""
    if not a.deadline:
        return None
    title = f"{a.info.sender}: " + (f"{_euro(a.amount)} " if a.amount is not None else "") + CARD[lang]["deadline"]
    details = f"{CARD[lang]['ref']}: {a.reference}" if a.reference else ""
    day, next_day = a.deadline.strftime("%Y%m%d"), date.fromordinal(a.deadline.toordinal() + 1).strftime("%Y%m%d")
    alarms = "".join(
        f"BEGIN:VALARM\r\nTRIGGER:-P{n}D\r\nACTION:DISPLAY\r\nDESCRIPTION:{_ics_escape(title)}\r\nEND:VALARM\r\n"
        for n in (3, 1)
    )
    ics = (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Amt-Lotse//EN\r\nBEGIN:VEVENT\r\n"
        f"UID:{uuid.uuid4()}@amt-lotse\r\nDTSTAMP:{date.today():%Y%m%d}T000000Z\r\n"
        f"DTSTART;VALUE=DATE:{day}\r\nDTEND;VALUE=DATE:{next_day}\r\n"
        f"SUMMARY:{_ics_escape(title)}\r\nDESCRIPTION:{_ics_escape(details)}\r\n"
        f"{alarms}END:VEVENT\r\nEND:VCALENDAR\r\n"
    )
    path = Path(tempfile.mkdtemp(prefix="amt_lotse_cal_")) / "Frist.ics"
    path.write_text(ics, encoding="utf-8", newline="")  # keep the \r\n that the .ics format needs
    return str(path)


def summary_card(a: Analysis, lang: str) -> str:
    """Markdown card with the checked facts, in the user's language."""
    t = CARD[lang]
    lines = [f"**{t['from']}:** {a.info.sender}"]

    if a.deadline:
        days = (a.deadline - date.today()).days
        when = t["today"] if days == 0 else (t["overdue"].format(n=-days) if days < 0 else t["days"].format(n=days))
        lines.append(f"**{t['deadline']}:** {say_date(a.deadline, lang)} ({when})")
    else:
        lines.append(f"**{t['deadline']}:** {t['none']}")

    if a.amount is not None:
        lines.append(f"**{t['pay']}:** {_euro(a.amount)}")
    elif a.amount_unclear:
        lines.append(f"**{t['pay']}:** {t['unclear']}")
    elif a.receives is not None:
        lines.append(f"**{t['get']}:** {_euro(a.receives)}")
    else:
        lines.append(t["nothing"])

    if a.reference:
        # spaced so it is easy to read aloud and copy, e.g. "RE-2026-08812"
        lines.append(f"**{t['ref']}:** <span class=\"ref\">{a.reference}</span> ({t['ref_hint']})")
    return "\n\n".join(lines)
