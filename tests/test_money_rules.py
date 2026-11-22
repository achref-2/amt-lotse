"""Who pays? The small model gets this wrong; the letter's own wording decides (extract.py safety nets)."""

from decimal import Decimal

from amt_lotse.extract import amount_is_credit, extract_letter_info, find_payment_request
from conftest import eval_letter, model_info


def test_model_says_no_payment_but_letter_asks_to_pay(fake_model):
    letter = eval_letter("mahnung_01")  # "Bitte überweisen Sie den Gesamtbetrag von 56,13 € ..."
    fake_model(model_info(money_direction="no_payment", amount_text=None))
    info = extract_letter_info(letter)
    assert info.money_direction == "recipient_pays"
    assert info.amount_text == "56,13 €"


def test_payment_request_takes_the_total_not_a_single_line_item(fake_model):
    letter = eval_letter("mahnung_01")  # lists 49,90 € + 5,00 € + 1,23 € = 56,13 €
    fake_model(model_info(money_direction="recipient_pays", amount_text="49,90 €"))
    assert extract_letter_info(letter).amount_text == "56,13 €"


def test_credit_is_money_you_get_not_a_bill(fake_model):
    letter = (
        "Stadtwerke Musterstadt\n\nJahresabrechnung 2026\n\n"
        "Ihr Guthaben beträgt\n64,30 €.\n\nWir überweisen den Betrag auf Ihr Konto.\n"
    )
    fake_model(model_info(money_direction="recipient_pays", amount_text="64,30 €"))
    info = extract_letter_info(letter)
    assert info.money_direction == "recipient_receives"
    assert not info.recipient_must_pay


def test_refund_next_to_a_pay_word_is_still_a_refund():
    letter = "Wir erstatten Ihnen 120,00 €.\nSie müssen nichts zahlen."
    assert amount_is_credit(letter, "120,00 €")


def test_model_says_pay_but_letter_has_no_euro_amount(fake_model):
    letter = "Jobcenter Musterstadt\n\nBitte kommen Sie am 08.12.2026 um 10:30 Uhr in Zimmer 214."
    fake_model(model_info(money_direction="recipient_pays", amount_text="10,30 €"))
    info = extract_letter_info(letter)
    assert info.money_direction == "no_payment"
    assert info.amount_text is None


def test_price_per_unit_is_not_a_bill(fake_model):
    letter = "Ab dem 01.01.2027 beträgt der Arbeitspreis 0,32 € pro kWh.\nDer Grundpreis beträgt 12,00 € monatlich."
    fake_model(model_info(money_direction="recipient_pays", amount_text="0,32 € pro kWh"))
    info = extract_letter_info(letter)
    assert info.money_direction == "no_payment"
    assert info.amount_text is None


def test_amount_named_on_the_line_before_the_request():
    letter = "Für 2025 ergibt sich eine Nachzahlung von 312,00 €.\nBitte überweisen Sie den Betrag bis zum 23.12.2026."
    assert find_payment_request(letter) == "312,00 €"


def test_no_request_no_amount():
    assert find_payment_request("Wir informieren Sie über die neuen Öffnungszeiten.") is None


def test_every_labelled_amount_is_in_its_letter():
    """Data check: the hand labels in data/eval must match the letters they belong to."""
    import json

    from conftest import EVAL_DIR

    for expected_file in EVAL_DIR.glob("*.expected.json"):
        expected = json.loads(expected_file.read_text(encoding="utf-8"))
        letter = (EVAL_DIR / expected_file.name.replace(".expected.json", ".txt")).read_text(encoding="utf-8")
        if expected["amount_eur"]:
            german = f"{Decimal(expected['amount_eur']):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            assert german in letter, expected_file.name
        if expected["reference_number"]:
            assert expected["reference_number"] in letter, expected_file.name
