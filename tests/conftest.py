"""Shared test helpers.

The tests never call a real model: GitHub's servers have no Ollama and no GPU. Where the app normally asks
a model, `fake_model` plays the model's answers, including WRONG ones, so we can check that the rules
around the models catch the mistakes. A test that forgets to set up answers fails loudly.
"""

import json
from pathlib import Path

import pytest

from amt_lotse import extract

EVAL_DIR = Path(__file__).resolve().parents[1] / "data" / "eval"


@pytest.fixture(autouse=True)
def no_real_model(monkeypatch):
    def refuse(**_kwargs):
        raise AssertionError("A test tried to call the real model. Use the fake_model fixture.")

    monkeypatch.setattr(extract.client, "chat", refuse)


@pytest.fixture
def fake_model(monkeypatch):
    """fake_model("answer 1", {"sender": ...}, ...): each model call gets the next answer (dicts become JSON).
    Returns the list of calls, so a test can look at what was sent."""
    calls = []

    def install(*answers):
        queue = list(answers)

        def chat(**kwargs):
            calls.append(kwargs)
            if not queue:
                raise AssertionError("The model was called more often than the test expected.")
            answer = queue.pop(0)
            content = json.dumps(answer, ensure_ascii=False) if isinstance(answer, dict) else answer
            return {"message": {"content": content}, "done_reason": "stop"}

        monkeypatch.setattr(extract.client, "chat", chat)
        return calls

    return install


def model_info(**fields) -> dict:
    """A LetterInfo answer as the model would give it; tests override only what matters."""
    base = {
        "sender": "Absender", "subject": "Betreff", "letter_type": "Brief", "required_action": "lesen",
        "recipient_has_deadline": False, "deadline_text": None, "amount_text": None,
        "money_direction": "no_payment", "reference_number": None,
    }
    base.update(fields)
    return base


def eval_letter(name: str) -> str:
    return (EVAL_DIR / f"{name}.txt").read_text(encoding="utf-8")
