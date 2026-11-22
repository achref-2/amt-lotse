"""Every language has every text: a missing key would crash the page for exactly those users."""

import pytest

from amt_lotse.ask import NOT_SAID
from amt_lotse.cli import LANGUAGES
from amt_lotse.pipeline import CARD, TODO
from amt_lotse.speak import MONTHS, TEXT, VOICES, WEEKDAYS


@pytest.mark.parametrize("table", [TEXT, TODO, CARD], ids=["speech", "todo", "card"])
def test_same_keys_in_every_language(table):
    keys = set(table["en"])
    for lang in LANGUAGES:
        assert set(table[lang]) == keys, f"{lang}: missing {keys - set(table[lang])}, extra {set(table[lang]) - keys}"


def test_ui_texts_complete():
    from amt_lotse.app import UI
    keys = set(UI["en"])
    for lang in LANGUAGES:
        assert set(UI[lang]) == keys, f"{lang}: missing {keys - set(UI[lang])}"


def test_months_weekdays_voices_answers():
    for lang in LANGUAGES:
        assert len(MONTHS[lang]) == 12 and len(WEEKDAYS[lang]) == 7
        assert lang in VOICES and lang in NOT_SAID
