"""Reply drafts: people may SEND these, so numbers the model invents must never stay in them."""

from amt_lotse.extract import LetterInfo
from amt_lotse.reply import _clean_body, _invented_numbers, _replace_invented, build_reply
from conftest import eval_letter, model_info

LETTER = eval_letter("mahnung_01")


def test_dates_and_amounts_from_the_letter_are_allowed():
    body = "Ich kann den Betrag von 56,13 € leider nicht bis zum 04.12.2026 zahlen."
    assert _invented_numbers(body, LETTER, None) == []


def test_invented_amount_date_and_count_are_found():
    body = "Ich zahle in drei Monatsraten von 20,00 € ab dem 01.01.2027."
    assert set(_invented_numbers(body, LETTER, None)) == {"20,00", "01.01.2027", "drei"}


def test_numbers_from_the_users_own_note_are_allowed():
    body = "Ich bin bis zum 10.12.2026 krank."
    assert _invented_numbers(body, LETTER, "krank bis 10.12.2026") == []


def test_invented_numbers_become_placeholders():
    body = "Ich zahle in drei Raten von 20,00 € ab dem 01.01.2027."
    fixed = _replace_invented(body, ["drei", "20,00", "01.01.2027"])
    assert fixed == "Ich zahle in [Anzahl] Raten von [Betrag] € ab dem [Datum]."


def test_greetings_and_copied_signature_are_removed():
    body = "Sehr geehrte Damen und Herren,\nich bitte um Ratenzahlung.\nMit freundlichen Grüßen\nIhre Muster Mobilfunk GmbH"
    assert _clean_body(body, "Muster Mobilfunk GmbH") == "ich bitte um Ratenzahlung."


def test_model_invents_twice_then_code_replaces(fake_model):
    info = LetterInfo(**model_info(sender="Muster Mobilfunk GmbH", money_direction="recipient_pays",
                                   amount_text="56,13 €"))
    invented = "Ich möchte in drei Raten zu je 18,71 € zahlen."
    fake_model(invented, invented, "Sie bitten um Ratenzahlung.")   # body, retry body, summary
    draft = build_reply(LETTER, info, "RE-2026-08812", "installments", "English")
    assert "18,71" not in draft.german and "drei" not in draft.german
    assert "[Betrag]" in draft.german and "[Anzahl]" in draft.german
    assert any("were replaced" in w for w in draft.warnings)
    assert draft.german.count("Mit freundlichen Grüßen") == 1
    assert "Ihr Zeichen / Nummer: RE-2026-08812" in draft.german
    assert "Ihr Schreiben vom 20.11.2026" in draft.german


def test_clean_answer_is_used_as_it_is(fake_model):
    info = LetterInfo(**model_info(sender="Muster Mobilfunk GmbH"))
    calls = fake_model("Ich bitte um eine Ratenzahlung für den Betrag von 56,13 €.", "Summary.")
    draft = build_reply(LETTER, info, None, "installments", "English")
    assert len(calls) == 2                       # no retry needed
    assert "56,13 €" in draft.german
    assert "Ihr Zeichen: [Nummer aus dem Brief]" in draft.german
