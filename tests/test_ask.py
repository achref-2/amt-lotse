"""Questions about a letter: answered only from the letter, never with invented dates or amounts."""

from amt_lotse.ask import NOT_SAID, answer_question
from amt_lotse.extract import LetterInfo
from conftest import eval_letter, model_info

LETTER = eval_letter("mahnung_01")
INFO = LetterInfo(**model_info(sender="Muster Mobilfunk GmbH", money_direction="recipient_pays",
                               amount_text="56,13 €", recipient_has_deadline=True, deadline_text="04.12.2026"))


def test_good_answer_is_kept(fake_model):
    fake_model("If you don't pay 56,13 € by 04.12.2026, the debt goes to a debt collection agency (Inkasso).")
    a = answer_question(LETTER, INFO, "What happens if I don't pay?", "en")
    assert a.from_letter and "Inkasso" in a.text


def test_letter_does_not_say_it(fake_model):
    fake_model("NOT_IN_LETTER")
    a = answer_question(LETTER, INFO, "Can I pay in cash?", "en")
    assert not a.from_letter and a.text == NOT_SAID["en"]


def test_invented_amount_twice_gives_the_safe_answer(fake_model):
    fake_model("You must pay 80,00 €.", "You must pay 99,00 €.")
    assert answer_question(LETTER, INFO, "How much?", "en").text == NOT_SAID["en"]


def test_invented_date_is_retried(fake_model):
    calls = fake_model("Pay by 10.01.2027.", "Pay 56,13 € by 4 December 2026.")
    a = answer_question(LETTER, INFO, "When?", "en")
    assert a.from_letter and a.text == "Pay 56,13 € by 4 December 2026." and len(calls) == 2


def test_short_arabic_answer_with_numbers_counts_as_arabic(fake_model):
    fake_model("ادفع 56,13 € قبل 04.12.2026.")
    assert answer_question(LETTER, INFO, "كم؟", "ar").from_letter


def test_answer_in_the_wrong_language_is_retried(fake_model):
    fake_model("Sie müssen die Rechnung bezahlen, und die Frist ist der 04.12.2026, das ist wichtig.",
               "You must pay 56,13 €.")
    assert answer_question(LETTER, INFO, "What must I do?", "en").text == "You must pay 56,13 €."
