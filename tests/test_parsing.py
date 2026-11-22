"""Turning German text into dates, amounts and reference numbers."""

from datetime import date
from decimal import Decimal

import pytest

from amt_lotse.extract import normalize_reference, parse_german_amount, parse_german_date
from amt_lotse.reply import letter_date


@pytest.mark.parametrize("text, expected", [
    ("bis zum 15.12.2026", date(2026, 12, 15)),
    ("am 8.1.2027 um 10:30 Uhr", date(2027, 1, 8)),
    ("04.12.2026", date(2026, 12, 4)),
])
def test_german_dates(text, expected):
    assert parse_german_date(text) == expected


def test_no_date_is_an_error_not_a_guess():
    with pytest.raises(ValueError):
        parse_german_date("innerhalb von vier Wochen")


@pytest.mark.parametrize("text, expected", [
    ("56,13 €", Decimal("56.13")),
    ("1.234,56 EUR", Decimal("1234.56")),
    ("Gesamtbetrag 312,00 Euro", Decimal("312.00")),
])
def test_german_amounts(text, expected):
    assert parse_german_amount(text) == expected


@pytest.mark.parametrize("text, expected", [
    ("Kundennummer: 7788990", "7788990"),
    ("Rechnungsnummer RE-2026-08812", "RE-2026-08812"),
    ("Aktenzeichen: 32.1-AE-2026-0457", "32.1-AE-2026-0457"),
    ("201/5555/1234", "201/5555/1234"),
])
def test_reference_numbers_lose_their_label(text, expected):
    assert normalize_reference(text) == expected


def test_letter_date_is_the_date_after_the_place():
    assert letter_date("Musterstadt, 20.11.2026\n\nZahlen Sie bis 04.12.2026") == "20.11.2026"
