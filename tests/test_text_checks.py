"""The rule-based text evaluation: finds dates and amounts in any of the four languages."""

from datetime import date
from decimal import Decimal

from amt_lotse.evaluate_text import amounts_in, check_explanation, dates_in


def test_dates_in_every_language():
    assert dates_in("by 4 December 2026") == {date(2026, 12, 4)}
    assert dates_in("bis 4. Dezember 2026") == {date(2026, 12, 4)}
    assert dates_in("avant le 4 décembre 2026") == {date(2026, 12, 4)}
    assert dates_in("December 4, 2026 and 2027-01-10") == {date(2026, 12, 4), date(2027, 1, 10)}
    assert dates_in("Frist: 04.12.2026") == {date(2026, 12, 4)}


def test_a_date_is_not_an_amount():
    assert amounts_in("bis 04.12.2026 zahlen Sie 1.234,56 €") == {Decimal("1234.56")}


def test_false_reassurance_is_flagged():
    letter = "Bitte zahlen Sie 56,13 € bis zum 04.12.2026."
    expected = {"deadline": "2026-12-04", "amount_eur": "56.13", "reference_number": None}
    good = check_explanation("Pay 56,13 € by 4 December 2026.", letter, expected, "en")
    bad = check_explanation("Pay 56,13 € by 4 December 2026. Nothing will happen if you don't.", letter, expected, "en")
    assert all(good["checks"].values())
    assert not bad["checks"]["no_false_reassurance"]


def test_invented_date_is_flagged():
    letter = "Bitte zahlen Sie 56,13 € bis zum 04.12.2026."
    expected = {"deadline": "2026-12-04", "amount_eur": "56.13", "reference_number": None}
    result = check_explanation("Pay 56,13 € by 10 January 2027.", letter, expected, "en")
    assert not result["checks"]["no_invented_dates"] and not result["checks"]["mentions_deadline"]
