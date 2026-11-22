"""Turkish, Ukrainian, Russian and Farsi: dates, plurals, right-to-left and 'is this really the right language?'."""

from datetime import date
from decimal import Decimal

import pytest

from amt_lotse.cli import LANGUAGES, RTL_LANGUAGES, is_in_language
from amt_lotse.evaluate_text import dates_in
from amt_lotse.speak import plural, say_amount, say_date

D = date(2026, 12, 4)   # a Friday


@pytest.mark.parametrize("lang, expected", [
    ("tr", "4 Aralık 2026 Cuma"),
    ("ru", "4 декабря 2026 года (пятница)"),      # month in the genitive, as inside a date
    ("uk", "4 грудня 2026 року (пʼятниця)"),
    ("fa", "جمعه 4 دسامبر 2026"),
])
def test_dates(lang, expected):
    assert say_date(D, lang) == expected


@pytest.mark.parametrize("lang", ["tr", "uk", "ru", "fa"])
def test_spoken_dates_are_found_again_by_the_invented_date_check(lang):
    assert dates_in(f"… {say_date(D, lang)} …") == {D}


@pytest.mark.parametrize("n, form", [(1, "цент"), (2, "цента"), (4, "цента"), (5, "центов"), (11, "центов"),
                                     (12, "центов"), (21, "цент"), (22, "цента"), (13, "центов")])
def test_russian_plural(n, form):
    assert plural(n, ("цент", "цента", "центов")) == form


def test_amounts():
    assert say_amount(Decimal("56.13"), "ru") == "56 евро 13 центов"
    assert say_amount(Decimal("21.21"), "uk") == "21 євро 21 цент"
    assert say_amount(Decimal("93.00"), "fa") == "93 یورو"
    assert say_amount(Decimal("56.13"), "tr") == "56 avro 13 sent"


def test_right_to_left():
    assert RTL_LANGUAGES == {"ar", "fa"} and RTL_LANGUAGES <= set(LANGUAGES)


@pytest.mark.parametrize("lang, text, ok", [
    ("ru", "Вам нужно заплатить 56,13 € компании Muster Mobilfunk GmbH до 04.12.2026.", True),
    ("uk", "Вам потрібно сплатити 56,13 € компанії Muster Mobilfunk GmbH до 04.12.2026.", True),
    ("uk", "Вам нужно заплатить 56,13 € до 04.12.2026, это важно, иначе будет Inkasso.", False),   # Russian
    ("ru", "Вам потрібно сплатити 56,13 € до 04.12.2026, це важливо, інакше буде Inkasso.", False),  # Ukrainian
    ("fa", "شما باید تا 04.12.2026 مبلغ 56,13 € را به Muster Mobilfunk GmbH پرداخت کنید.", True),
    ("fa", "يجب عليك دفع 56,13 € إلى شركة Muster Mobilfunk GmbH قبل 04.12.2026 وإلا سيتم إرسال الدين.", False),  # Arabic
    ("ar", "يجب عليك دفع 56,13 € إلى شركة Muster Mobilfunk GmbH قبل 04.12.2026.", True),
    ("tr", "Muster Mobilfunk GmbH'ye 04.12.2026 tarihine kadar 56,13 € ödemeniz gerekiyor.", True),
    ("tr", "Sie müssen die Rechnung bezahlen, und die Frist ist nicht verlängert.", False),         # German
    ("en", "You have to pay. Вам нужно заплатить.", False),                                       # Cyrillic leak
    ("ru", "Вам нужно заплатить 请 56,13 €.", False),                                              # Chinese leak
])
def test_right_language(lang, text, ok):
    assert is_in_language(text, lang) is ok


@pytest.mark.parametrize("text", [
    "Ödemezseniz hiçbir şey olmaz.",
    "Если вы не заплатите, ничего не будет.",
    "Якщо ви не заплатите, нічого не станеться.",
    "اگر پرداخت نکنید هیچ اتفاقی نمی‌افتد.",
])
def test_false_reassurance_is_caught_in_every_new_language(text):
    from amt_lotse.evaluate_text import FALSE_REASSURANCE

    assert FALSE_REASSURANCE.search(text)
