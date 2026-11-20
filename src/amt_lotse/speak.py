"""Read the letter summary aloud, fully offline, with Piper TTS.

Built for people who cannot easily read the letter themselves:
blind and visually impaired people, older people, and new immigrants.

Design rules:
- The most important facts come FIRST and are built from the checked extraction,
  not from the LLM (so dates and amounts are never invented).
- Dates and amounts are written out as words, so the voice reads them naturally.
- Speech is slower than normal by default, and the key action is repeated at the end.
"""

import sys
import wave
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
VOICES_DIR = PROJECT_ROOT / "voices"
OUTPUT_DIR = PROJECT_ROOT / "audio"

VOICES = {
    "en": "en_US-lessac-medium",
    "fr": "fr_FR-siwis-medium",
    "de": "de_DE-thorsten-medium",
    "ar": "ar_JO-kareem-medium",
}

MONTHS = {
    "en": ["January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"],
    "fr": ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
           "août", "septembre", "octobre", "novembre", "décembre"],
    "de": ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
           "August", "September", "Oktober", "November", "Dezember"],
    "ar": ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو",
           "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"],
}

TEXT = {
    "en": {
        "intro": "This is a letter from {sender}.",
        "deadline": "Important: the deadline is {date}. That is in {days} days.",
        "deadline_today": "Important: the deadline is today, {date}.",
        "overdue": "Warning: the deadline was {date}. It has already passed.",
        "no_deadline": "There is no fixed deadline in this letter.",
        "pay": "You have to pay {amount}.",
        "receive": "You will receive {amount}. You do not have to pay anything.",
        "no_pay": "You do not have to pay anything.",
        "unclear_amount": "Warning: there is an amount to pay, but I could not read it. Please check the letter with someone.",
        "reference": "Your reference number is {ref}. Always give this number.",
        "explain": "Here is the explanation.",
        "repeat": "Once again, the most important point: {action}",
        "short_deadline": "Deadline: {date}.",
        "euro": "{e} euros and {c} cents",
        "euro_round": "{e} euros",
        "help": "If you are unsure, ask someone you trust or an advice centre to check the original letter.",
        "bad_photo": "I could not read this letter well. Please take the photo again, in good light, with the whole page visible and the phone held straight above it.",
    },
    "fr": {
        "intro": "Ceci est une lettre de {sender}.",
        "deadline": "Important : la date limite est le {date}. C'est dans {days} jours.",
        "deadline_today": "Important : la date limite est aujourd'hui, le {date}.",
        "overdue": "Attention : la date limite était le {date}. Elle est déjà dépassée.",
        "no_deadline": "Il n'y a pas de date limite précise dans cette lettre.",
        "pay": "Vous devez payer {amount}.",
        "receive": "Vous allez recevoir {amount}. Vous n'avez rien à payer.",
        "no_pay": "Vous n'avez rien à payer.",
        "unclear_amount": "Attention : il y a un montant à payer, mais je n'ai pas pu le lire. Vérifiez la lettre avec quelqu'un.",
        "reference": "Votre numéro de référence est {ref}. Indiquez toujours ce numéro.",
        "explain": "Voici l'explication.",
        "repeat": "Encore une fois, le plus important : {action}",
        "short_deadline": "Date limite : {date}.",
        "euro": "{e} euros et {c} centimes",
        "euro_round": "{e} euros",
        "help": "En cas de doute, demandez à une personne de confiance ou à un centre de conseil de vérifier la lettre originale.",
        "bad_photo": "Je n'ai pas bien pu lire cette lettre. Reprenez la photo avec une bonne lumière, la page entière visible et le téléphone bien au-dessus.",
    },
    "de": {
        "intro": "Das ist ein Brief von {sender}.",
        "deadline": "Wichtig: Die Frist ist der {date}. Das ist in {days} Tagen.",
        "deadline_today": "Wichtig: Die Frist ist heute, der {date}.",
        "overdue": "Achtung: Die Frist war der {date}. Sie ist schon vorbei.",
        "no_deadline": "In diesem Brief gibt es keine feste Frist.",
        "pay": "Sie müssen {amount} bezahlen.",
        "receive": "Sie bekommen {amount}. Sie müssen nichts bezahlen.",
        "no_pay": "Sie müssen nichts bezahlen.",
        "unclear_amount": "Achtung: Es gibt einen Betrag zu bezahlen, aber ich konnte ihn nicht lesen. Bitte prüfen Sie den Brief mit jemandem.",
        "reference": "Ihre Nummer ist {ref}. Geben Sie diese Nummer immer an.",
        "explain": "Jetzt die Erklärung.",
        "repeat": "Noch einmal das Wichtigste: {action}",
        "short_deadline": "Frist: {date}.",
        "euro": "{e} Euro und {c} Cent",
        "euro_round": "{e} Euro",
        "help": "Wenn Sie unsicher sind, lassen Sie den Originalbrief von einer Vertrauensperson oder einer Beratungsstelle prüfen.",
        "bad_photo": "Ich konnte diesen Brief nicht gut lesen. Bitte machen Sie das Foto noch einmal, bei gutem Licht, mit der ganzen Seite, und halten Sie das Handy gerade darüber.",
    },
    "ar": {
        "intro": "هذه رسالة من {sender}.",
        "deadline": "مهم: آخر موعد هو {date}. أي بعد {days} يوما.",
        "deadline_today": "مهم: آخر موعد هو اليوم، {date}.",
        "overdue": "تنبيه: آخر موعد كان {date}. لقد انتهى بالفعل.",
        "no_deadline": "لا يوجد موعد نهائي محدد في هذه الرسالة.",
        "pay": "يجب عليك دفع {amount}.",
        "receive": "ستحصل على {amount}. لا يجب عليك دفع أي شيء.",
        "no_pay": "لا يجب عليك دفع أي شيء.",
        "unclear_amount": "تنبيه: هناك مبلغ يجب دفعه، لكنني لم أستطع قراءته. من فضلك راجع الرسالة مع شخص ما.",
        "reference": "رقمك المرجعي هو {ref}. اذكر هذا الرقم دائما.",
        "explain": "وهذا هو الشرح.",
        "repeat": "مرة أخرى، الأهم هو: {action}",
        "short_deadline": "آخر موعد: {date}.",
        "euro": "{e} يورو و {c} سنت",
        "euro_round": "{e} يورو",
        "help": "إذا لم تكن متأكدا، اطلب من شخص تثق به أو من مركز استشارة أن يراجع الرسالة الأصلية.",
        "bad_photo": "لم أستطع قراءة هذه الرسالة جيدا. من فضلك التقط الصورة مرة أخرى في إضاءة جيدة، مع ظهور الصفحة كاملة، وأمسك الهاتف مستقيما فوقها.",
    },
}


@dataclass
class SpokenFacts:
    sender: str
    deadline: date | None
    amount: Decimal | None
    receives: Decimal | None  # amount if the recipient GETS money
    reference: str | None
    amount_unclear: bool = False


def say_date(d: date, lang: str) -> str:
    return f"{d.day}. {MONTHS[lang][d.month - 1]} {d.year}" if lang == "de" else \
        f"{d.day} {MONTHS[lang][d.month - 1]} {d.year}"


def say_amount(amount: Decimal, lang: str) -> str:
    euros = int(amount)
    cents = int((amount - euros) * 100)
    template = TEXT[lang]["euro"] if cents else TEXT[lang]["euro_round"]
    return template.format(e=euros, c=cents)


def say_reference(ref: str) -> str:
    """Spell references character by character so they are easy to write down: 'KV-445566' -> 'K V 4 4 5 5 6 6'."""
    return " ".join(ch for ch in ref if ch.isalnum())


def build_script(facts: SpokenFacts, explanation: str, lang: str) -> str:
    t = TEXT[lang]
    parts = [t["intro"].format(sender=facts.sender)]

    if facts.deadline:
        days = (facts.deadline - date.today()).days
        d = say_date(facts.deadline, lang)
        if days < 0:
            parts.append(t["overdue"].format(date=d))
        elif days == 0:
            parts.append(t["deadline_today"].format(date=d))
        else:
            parts.append(t["deadline"].format(date=d, days=days))
    else:
        parts.append(t["no_deadline"])

    if facts.amount is not None:
        action = t["pay"].format(amount=say_amount(facts.amount, lang))
    elif facts.amount_unclear:
        action = t["unclear_amount"]
    elif facts.receives:
        action = t["receive"].format(amount=say_amount(facts.receives, lang))
    else:
        action = t["no_pay"]
    parts.append(action)

    if facts.reference:
        parts.append(t["reference"].format(ref=say_reference(facts.reference)))

    parts.append(t["explain"])
    parts.append(explanation)

    # Repeat the key point at the end: helps older listeners and anyone who missed it.
    if facts.deadline and facts.deadline >= date.today():
        short = t["short_deadline"].format(date=say_date(facts.deadline, lang))
        parts.append(t["repeat"].format(action=f"{action} {short}"))
    parts.append(t["help"])
    return "\n".join(parts)


def load_voice(lang: str):
    try:
        from piper import PiperVoice
        from piper.download_voices import download_voice
    except ImportError:
        sys.exit("Speech needs Piper. Install it with:  uv add piper-tts")

    name = VOICES[lang]
    model = VOICES_DIR / f"{name}.onnx"
    if not model.exists():
        print(f"Downloading voice {name} (only once) ...", flush=True)
        VOICES_DIR.mkdir(exist_ok=True)
        download_voice(name, VOICES_DIR)
    return PiperVoice.load(str(model))


def speak(script: str, lang: str, out_name: str, slow: bool = True, play: bool = True) -> Path:
    """Turn the script into a .wav file and (on Windows) play it."""
    from piper import SynthesisConfig

    voice = load_voice(lang)
    config = SynthesisConfig(length_scale=1.25 if slow else 1.0)  # >1 = slower

    OUTPUT_DIR.mkdir(exist_ok=True)
    out_path = OUTPUT_DIR / f"{out_name}_{lang}.wav"
    with wave.open(str(out_path), "wb") as wav_file:
        voice.synthesize_wav(script, wav_file, syn_config=config)

    if play and sys.platform == "win32":
        import winsound
        print("Playing audio ... (Ctrl+C to stop)", flush=True)
        winsound.PlaySound(str(out_path), winsound.SND_FILENAME)
    return out_path
