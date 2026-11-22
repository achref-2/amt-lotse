"""What the user sees and hears first: the to-do sentence, the facts card, the audio script, the calendar file."""

from datetime import date, timedelta
from decimal import Decimal

from amt_lotse.extract import LetterInfo
from amt_lotse.pipeline import Analysis, calendar_file, summary_card, todo_box
from amt_lotse.speak import SpokenFacts, build_script, say_amount, say_date, say_reference
from conftest import model_info


def analysis(**fields) -> Analysis:
    a = Analysis(text="Brief", ocr_used=False, looks_bad=False, truncated=False,
                 info=LetterInfo(**model_info(sender="Muster Mobilfunk GmbH")))
    for k, v in fields.items():
        setattr(a, k, v)
    return a


def test_pay_by_date_is_one_sentence():
    a = analysis(amount=Decimal("56.13"), deadline=date(2030, 12, 4))
    html = todo_box(a, "en")
    assert "Pay <b>56,13 €</b> by <b>Wednesday, 4 December 2030</b>." in html
    assert 'class="todo"' in html                       # far away: not urgent


def test_seven_days_or_less_is_urgent():
    a = analysis(amount=Decimal("10.00"), deadline=date.today() + timedelta(days=3))
    html = todo_box(a, "de")
    assert 'class="todo urgent"' in html and "noch 3 Tage" in html


def test_overdue_says_so():
    html = todo_box(analysis(deadline=date.today() - timedelta(days=1)), "en")
    assert "The deadline has passed!" in html


def test_unreadable_amount_never_says_nothing_to_pay():
    html = todo_box(analysis(amount_unclear=True), "en")
    assert "could not be read" in html and "urgent" in html
    assert "nothing to pay" not in html


def test_credit_says_you_receive():
    assert "You will receive <b>64,30 €</b>" in todo_box(analysis(receives=Decimal("64.30")), "en")


def test_nothing_to_do():
    assert "No deadline and nothing to pay" in todo_box(analysis(), "en")


def test_arabic_box_is_right_to_left_aware():
    assert 'dir="auto"' in todo_box(analysis(amount=Decimal("5.00")), "ar")


def test_card_shows_reference_and_amount():
    card = summary_card(analysis(amount=Decimal("1234.56"), reference="RE-2026-08812"), "en")
    assert "1.234,56 €" in card and "RE-2026-08812" in card


def test_calendar_file_has_two_reminders():
    path = calendar_file(analysis(deadline=date(2030, 12, 4), amount=Decimal("56.13"), reference="K-1"), "en")
    ics = open(path, encoding="utf-8").read()
    assert "DTSTART;VALUE=DATE:20301204" in ics
    assert ics.count("BEGIN:VALARM") == 2 and "TRIGGER:-P3D" in ics and "TRIGGER:-P1D" in ics


def test_no_deadline_no_calendar_file():
    assert calendar_file(analysis(), "en") is None


def test_spoken_numbers():
    assert say_amount(Decimal("56.13"), "de") == "56 Euro und 13 Cent"
    assert "Cent" not in say_amount(Decimal("93.00"), "de")         # round amounts: no "0 cents"
    assert say_reference("KV-445566") == "K V 4 4 5 5 6 6"
    assert say_date(date(2026, 12, 4), "de") == "Freitag, 4. Dezember 2026"


def test_script_says_the_key_point_twice():
    facts = SpokenFacts(sender="Muster Mobilfunk GmbH", deadline=date.today() + timedelta(days=10),
                        amount=Decimal("56.13"), receives=None, reference="RE-1")
    script = build_script(facts, "Explanation.", "en")
    assert script.index("Explanation.") < script.rindex("56")       # repeated after the explanation
    assert "10" in script                                           # days left
