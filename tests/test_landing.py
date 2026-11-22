"""The landing page and the facts card: every language complete, model text escaped, right-to-left where needed."""

from datetime import date, timedelta
from decimal import Decimal

from amt_lotse import app, landing
from amt_lotse.cli import LANGUAGES
from amt_lotse.extract import LetterInfo
from amt_lotse.pipeline import Analysis


def _analysis(sender="Muster Mobilfunk GmbH", **kw):
    info = LetterInfo(sender=sender, subject="Mahnung", letter_type="Mahnung", required_action="pay",
                      recipient_has_deadline=True, deadline_text="", amount_text="", money_direction="recipient_pays",
                      reference_number="")
    return Analysis(text="", ocr_used=False, looks_bad=False, truncated=False, info=info, **kw)


def test_every_language_has_every_text():
    english = landing.TEXT["en"]
    for lang in LANGUAGES:
        t = landing.TEXT[lang]
        assert t.keys() == english.keys(), lang
        for key, value in english.items():
            if isinstance(value, list):
                assert len(t[key]) == len(value), (lang, key)
        assert all(t[k].strip() for k in english if isinstance(english[k], str)), lang


def test_one_example_label_per_example_letter():
    for lang in LANGUAGES:
        assert len(landing.example_labels(lang)) == len(app.EXAMPLES)


def test_right_to_left_pages():
    assert 'dir="rtl"' in landing.hero_html("fa") and 'dir="rtl"' in landing.info_html("ar")
    assert 'dir="ltr"' in landing.hero_html("tr")


def test_sender_from_the_model_is_escaped():
    """The sender is read by the model from the letter, so it must never become HTML on the page."""
    html = landing.facts_html(_analysis(sender='<img src=x onerror="alert(1)">'), "en")
    assert "<img" not in html and "&lt;img" in html


def test_facts_card_marks_urgent_deadline_and_money():
    a = _analysis(deadline=date.today() + timedelta(days=3), amount=Decimal("56.13"), reference="RE-2026-08812")
    html = landing.facts_html(a, "en")
    assert 'class="fact hot"' in html          # 3 days left: shown in red
    assert "56,13" in html and "RE-2026-08812" in html


def test_facts_card_shows_the_long_letter_warning():
    html = landing.facts_html(_analysis(), "de", warning="Sehr langer Brief")
    assert 'class="warn"' in html and "Sehr langer Brief" in html
