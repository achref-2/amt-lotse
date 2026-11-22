"""Questions about a letter ("What happens if I don't pay?"), answered ONLY from the letter.

Rules, because people act on these answers:
- If the letter does not say it, the answer says so: no guessing, no general legal advice.
- Dates and euro amounts in the answer must appear in the letter. Otherwise the model is asked again,
  and if it still invents one, the safe "the letter does not say this" answer is used instead.
- The answer must be in the user's language (same check as the explanation).
"""

from dataclasses import dataclass

from amt_lotse.cli import EXPLAIN_MODEL, LANGUAGES, is_in_language
from amt_lotse.evaluate_text import amounts_in, dates_in
from amt_lotse.extract import LetterInfo, client, options_for

NOT_IN_LETTER = "NOT_IN_LETTER"

NOT_SAID = {
    "en": "The letter does not say this. Please ask the office that sent it, or an advice centre (Beratungsstelle).",
    "fr": "La lettre ne le dit pas. Demandez au bureau qui l'a envoyée ou à un centre de conseil (Beratungsstelle).",
    "ar": "الرسالة لا تذكر ذلك. من فضلك اسأل المكتب الذي أرسلها أو مركز استشارة (Beratungsstelle).",
    "de": "Das steht nicht im Brief. Fragen Sie bitte das Amt, das den Brief geschickt hat, oder eine Beratungsstelle.",
}


@dataclass
class Answer:
    text: str
    from_letter: bool        # False = the letter doesn't answer it (safe fallback text)
    question: str


def _ask_model(letter: str, info: LetterInfo, question: str, language: str) -> str:
    response = client.chat(
        model=EXPLAIN_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You answer questions about ONE German official letter for people who do not read German well. "
                    f"You ALWAYS answer in {language}. "
                    "Use ONLY information that is written in the letter. "
                    f"If the letter does not contain the answer, reply with exactly {NOT_IN_LETTER} and nothing else. "
                    "Never guess, never give general legal advice, never say that nothing will happen. "
                    "Answer in 1 to 3 short, simple sentences. Copy dates and amounts exactly from the letter. "
                    "Keep German official terms and explain them in brackets."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Letter:\n\n{letter}\n\n"
                    f"Facts (trust these): deadline={info.deadline_text}, "
                    f"amount={info.amount_text if info.recipient_must_pay else None}, "
                    f"money_direction={info.money_direction}.\n\n"
                    f"Question: {question}\n\nAnswer in {language}."
                ),
            },
        ],
        options=options_for(letter, question),
    )
    return response["message"]["content"].strip()


def invents_numbers(answer: str, letter: str) -> bool:
    """True if the answer contains a date or euro amount that is not in the letter."""
    return bool(dates_in(answer) - dates_in(letter)) or bool(amounts_in(answer) - amounts_in(letter))


def answer_question(letter: str, info: LetterInfo, question: str, lang: str) -> Answer:
    question = question.strip()
    language = LANGUAGES[lang]
    for _attempt in range(2):
        text = _ask_model(letter, info, question, language)
        if NOT_IN_LETTER in text:
            return Answer(NOT_SAID[lang], from_letter=False, question=question)
        if is_in_language(text, lang) and not invents_numbers(text, letter):
            return Answer(text, from_letter=True, question=question)
    return Answer(NOT_SAID[lang], from_letter=False, question=question)
