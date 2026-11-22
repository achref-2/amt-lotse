"""Did the model really answer in the user's language?"""

from amt_lotse.cli import is_in_language


def test_english_ok():
    assert is_in_language("You have to pay 56,13 € to Muster Mobilfunk GmbH by 4 December 2026.", "en")


def test_german_answer_when_english_was_asked():
    assert not is_in_language("Sie müssen die Rechnung bezahlen, das ist die Mahnung und der Betrag ist hoch.", "en")


def test_leaked_chinese_characters_are_caught():
    assert not is_in_language("You have to pay 56,13 € 请 by Friday.", "en")


def test_arabic_with_german_names_and_numbers():
    assert is_in_language("هذه رسالة من Muster Mobilfunk GmbH. ادفع 56,13 € قبل 04.12.2026.", "ar")


def test_english_text_is_not_arabic():
    assert not is_in_language("Pay the bill to Muster Mobilfunk GmbH.", "ar")
