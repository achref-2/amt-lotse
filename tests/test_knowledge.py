"""RAG: the knowledge base is well-formed, finds the right entries, reaches the prompts, and the meaning
checks catch the real errors the model made before RAG (20 Nov 2026 eval run)."""

import json

import pytest

from amt_lotse import knowledge
from amt_lotse.cli import explain
from amt_lotse.evaluate_text import amounts_in, check_meaning, dates_in
from amt_lotse.extract import LetterInfo
from conftest import EVAL_DIR, eval_letter, model_info


@pytest.mark.parametrize("entry", knowledge.entries(), ids=lambda e: e.id)
def test_entries_are_well_formed(entry):
    assert entry.title and entry.triggers and len(entry.text) > 100
    assert entry.sources and all(s.startswith("https://") for s in entry.sources)
    # no amounts, dates or percentages: they go out of date, and the letter says what applies
    assert not amounts_in(entry.text) and not dates_in(entry.text) and "%" not in entry.text


@pytest.mark.parametrize("letter, must_have, must_not_have", [
    ("finanzamt_02", {"einspruch", "bekanntgabe"}, {"widerspruch"}),   # tax office: Einspruch, not Widerspruch
    ("mahnung_01", {"inkasso", "mahnung"}, {"vollstreckung"}),
    ("finanzamt_01", {"unterlagen"}, {"einspruch"}),                    # a request for documents is no decision
    ("jobcenter_01", {"jobcenter-termin"}, set()),
    ("vermieter_01", {"betriebskosten", "guthaben"}, set()),
    ("info_01", set(), {"mahnung", "inkasso"}),
])
def test_retrieval_finds_the_right_entries(letter, must_have, must_not_have):
    found = {e.id for e in knowledge.retrieve(eval_letter(letter))}
    assert must_have <= found and not (must_not_have & found)
    assert len(found) <= knowledge.MAX_ENTRIES


def test_rag_can_be_switched_off(monkeypatch):
    assert knowledge.background(eval_letter("mahnung_01"))
    monkeypatch.setenv("AMT_LOTSE_RAG", "0")
    assert knowledge.background(eval_letter("mahnung_01")) == ""


def test_background_reaches_the_explanation_prompt(fake_model):
    calls = fake_model("The company may hand the debt to a debt collection company (Inkasso).")
    explain(eval_letter("mahnung_01"), LetterInfo(**model_info()), "en")
    prompt = calls[0]["messages"][1]["content"]
    assert "debt collection company" in prompt and 'never as "enforcement agency"' in prompt


def test_background_reaches_the_question_prompt(fake_model):
    from amt_lotse.ask import answer_question

    calls = fake_model("In general, an Einspruch does not stop the payment.")
    answer_question(eval_letter("finanzamt_02"), LetterInfo(**model_info()), "Do I have to pay if I object?", "en")
    assert "does NOT stop the payment" in calls[0]["messages"][1]["content"]


# The model's real explanations from the eval run BEFORE RAG, and what the meaning checks say about them.
BEFORE_RAG = {
    "finanzamt_02": ("It informs him that he needs to pay a tax amount of 312.00 € by December 23, 2026. If he disagrees "
                     "with the amount, he can file an objection within one month of the letter's date.",
                     {"meaning.payment_still_due": False, "meaning.deadline_from_letter_date": False}),
    "mahnung_01": ("If the payment is not received by the deadline, the company will hand over the debt to an "
                   "enforcement agency, which may result in additional costs.",
                   {"meaning.debt_collection_company": False, "meaning.called_enforcement": False}),
    "finanzamt_01": ("He must submit these documents by January 10, 2027. Failure to do so may result in further "
                     "correspondence or delays in processing his tax declaration.",
                     {"meaning.invented_consequence": False}),
    # found in the FIRST run with RAG (22 Nov): background advice turned into a wrong consequence
    "vermieter_02": ("Herr Beispiel needs to pay a remaining amount of 143.27 euros by December 15, 2026. If he does not "
                     "pay, the monthly advance payment will increase to 112 euros starting January 1, 2027.",
                     {"meaning.increase_linked_to_not_paying": False, "meaning.advance_payment_increases": True}),
    "beitragsservice_02": ("He must respond within four weeks of receiving the letter using the attached form. "
                           "Failure to respond may result in further reminders.",
                           {"meaning.invented_consequence": False}),
}
GOOD = {
    "finanzamt_02": "Pay 312,00 € by 23 December 2026. You can object (Einspruch) within one month after you received "
                    "the decision, but the tax must still be paid even if you object.",
    "mahnung_01": "If you do not pay by 4 December 2026, the company hands the debt to a debt collection company "
                  "(Inkasso), which costs you more.",
    "finanzamt_01": "The tax office needs your enrolment certificate and proof of travel costs by 10 January 2027.",
    "vermieter_02": "Please pay the remaining 143,27 € by 15 December 2026. From 1 January 2027 your monthly advance "
                    "payment goes up from 100 € to 112 €.",
    "beitragsservice_02": "Within four weeks after receiving the letter, tell the Beitragsservice whether a flatmate "
                          "already pays the fee for your apartment, using the attached form.",
}


@pytest.mark.parametrize("letter", BEFORE_RAG)
def test_meaning_checks_catch_the_real_errors(letter):
    rules = json.loads((EVAL_DIR / f"{letter}.meaning.json").read_text(encoding="utf-8"))
    text, expected = BEFORE_RAG[letter]
    assert check_meaning(text, rules) == expected
    assert all(check_meaning(GOOD[letter], rules).values())


def test_background_may_only_explain_terms(fake_model):
    """The first RAG run turned background advice into consequences; the prompt now forbids that."""
    calls = fake_model("Explanation.")
    explain(eval_letter("vermieter_02"), LetterInfo(**model_info()), "en")
    system = calls[0]["messages"][0]["content"]
    assert "ONLY to explain what a German term" in system and "Always keep the consequences" in system


def test_second_rag_run_vermieter_is_correct_and_not_flagged():
    """22 Nov, second RAG run: correct (the increase is its own sentence) - the first check version flagged it."""
    rules = json.loads((EVAL_DIR / "vermieter_02.meaning.json").read_text(encoding="utf-8"))
    text = ("Herr Beispiel needs to pay a remaining amount of 143.27 € by December 15, 2026. If he does not pay, no "
            "further consequences are mentioned in the letter. The monthly advance payment will increase to 112.00 € "
            "starting January 1, 2027.")
    assert all(check_meaning(text, rules).values())


def test_explanations_get_the_meaning_only_questions_also_get_tips(fake_model):
    """Tips leaked into explanations as if the letter said them; now only answers to questions see them."""
    from amt_lotse.ask import answer_question

    letter = eval_letter("finanzamt_01")
    assert "more time" not in knowledge.background(letter)
    assert "more time" in knowledge.background(letter, tips=True)
    calls = fake_model("Explanation.", "In general, you can ask in writing for more time before the deadline.")
    explain(letter, LetterInfo(**model_info()), "en")
    answer_question(letter, LetterInfo(**model_info()), "What if I cannot send them in time?", "en")
    assert "more time" not in calls[0]["messages"][1]["content"]
    assert "more time" in calls[1]["messages"][1]["content"]


@pytest.mark.parametrize("entry", knowledge.entries(), ids=lambda e: e.id)
def test_meaning_part_gives_no_advice(entry):
    """Advice belongs in 'Tip:' lines, so explanations cannot present it as part of the letter."""
    import re

    assert not re.search(r"\b(should|can get free help|helps for free|ask about)\b", entry.meaning, re.IGNORECASE), entry.id


def test_prompt_forbids_saying_that_no_consequences_are_mentioned(fake_model):
    """Run of 22 Nov: 'If he does not comply, the letter does not specify any consequences.' - readers hear
    'nothing will happen', so the evaluation counts it as false reassurance and the prompt forbids it."""
    calls = fake_model("Explanation.")
    explain(eval_letter("finanzamt_01"), LetterInfo(**model_info()), "en")
    assert "do not write that the letter mentions no consequences" in calls[0]["messages"][0]["content"]
