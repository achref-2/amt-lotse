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
    "tr": "tr_TR-dfki-medium",
    "uk": "uk_UA-ukrainian_tts-medium",
    "ru": "ru_RU-irina-medium",
    "fa": "fa_IR-gyro-medium",
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
    "tr": ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"],
    "uk": ["січня", "лютого", "березня", "квітня", "травня", "червня", "липня", "серпня", "вересня", "жовтня", "листопада", "грудня"],
    "ru": ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"],
    "fa": ["ژانویه", "فوریه", "مارس", "آوریل", "مه", "ژوئن", "ژوئیه", "اوت", "سپتامبر", "اکتبر", "نوامبر", "دسامبر"],
}

WEEKDAYS = {
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    "fr": ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"],
    "de": ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"],
    "ar": ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"],
    "tr": ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"],
    "uk": ["понеділок", "вівторок", "середа", "четвер", "пʼятниця", "субота", "неділя"],
    "ru": ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"],
    "fa": ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه"],
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
    "tr": {
        "intro": "Bu mektup {sender} tarafından gönderildi.",
        "deadline": "Önemli: son tarih {date}. Bu, {days} gün sonra.",
        "deadline_today": "Önemli: son tarih bugün, {date}.",
        "overdue": "Dikkat: son tarih {date} idi. Bu tarih geçti.",
        "no_deadline": "Bu mektupta belirli bir son tarih yok.",
        "pay": "{amount} ödemeniz gerekiyor.",
        "receive": "{amount} alacaksınız. Hiçbir şey ödemeniz gerekmiyor.",
        "no_pay": "Hiçbir şey ödemeniz gerekmiyor.",
        "unclear_amount": "Dikkat: ödenecek bir tutar var ama okuyamadım. Lütfen mektubu biriyle birlikte kontrol edin.",
        "reference": "Referans numaranız {ref}. Bu numarayı her zaman belirtin.",
        "explain": "Şimdi açıklama geliyor.",
        "repeat": "Bir kez daha, en önemli nokta: {action}",
        "short_deadline": "Son tarih: {date}.",
        "euro": "{e} avro {c} sent",
        "euro_round": "{e} avro",
        "help": "Emin değilseniz, güvendiğiniz birine ya da bir danışma merkezine asıl mektubu kontrol ettirin.",
        "bad_photo": "Bu mektubu iyi okuyamadım. Lütfen fotoğrafı tekrar çekin: iyi ışıkta, sayfanın tamamı görünecek şekilde ve telefon tam üstünde.",
    },
    "uk": {
        "intro": "Це лист від {sender}.",
        "deadline": "Важливо: строк — {date}. Залишилося днів: {days}.",
        "deadline_today": "Важливо: строк спливає сьогодні, {date}.",
        "overdue": "Увага: строк був {date}. Він уже минув.",
        "no_deadline": "У цьому листі немає точного строку.",
        "pay": "Вам потрібно сплатити {amount}.",
        "receive": "Ви отримаєте {amount}. Платити нічого не потрібно.",
        "no_pay": "Платити нічого не потрібно.",
        "unclear_amount": "Увага: у листі є сума до сплати, але я не зміг її прочитати. Перевірте лист разом із кимось.",
        "reference": "Ваш номер: {ref}. Завжди вказуйте цей номер.",
        "explain": "Тепер пояснення.",
        "repeat": "Ще раз найважливіше: {action}",
        "short_deadline": "Строк: {date}.",
        "euro": "{e} євро {c} {cents}",
        "euro_round": "{e} євро",
        "help": "Якщо ви не впевнені, попросіть людину, якій довіряєте, або консультаційний центр перевірити оригінал листа.",
        "bad_photo": "Я не зміг добре прочитати цей лист. Сфотографуйте його ще раз: при гарному світлі, щоб було видно всю сторінку, тримаючи телефон прямо над нею.",
    },
    "ru": {
        "intro": "Это письмо от {sender}.",
        "deadline": "Важно: срок — {date}. Осталось дней: {days}.",
        "deadline_today": "Важно: срок истекает сегодня, {date}.",
        "overdue": "Внимание: срок был {date}. Он уже прошёл.",
        "no_deadline": "В этом письме нет точного срока.",
        "pay": "Вам нужно заплатить {amount}.",
        "receive": "Вы получите {amount}. Платить ничего не нужно.",
        "no_pay": "Платить ничего не нужно.",
        "unclear_amount": "Внимание: в письме есть сумма к оплате, но я не смог её прочитать. Проверьте письмо вместе с кем-нибудь.",
        "reference": "Ваш номер: {ref}. Всегда указывайте этот номер.",
        "explain": "Теперь объяснение.",
        "repeat": "Ещё раз самое важное: {action}",
        "short_deadline": "Срок: {date}.",
        "euro": "{e} евро {c} {cents}",
        "euro_round": "{e} евро",
        "help": "Если вы не уверены, попросите человека, которому доверяете, или консультационный центр проверить оригинал письма.",
        "bad_photo": "Я не смог хорошо прочитать это письмо. Сфотографируйте его ещё раз: при хорошем свете, чтобы была видна вся страница, держа телефон прямо над ней.",
    },
    "fa": {
        "intro": "این نامه از طرف {sender} است.",
        "deadline": "مهم: مهلت {date} است. یعنی {days} روز دیگر.",
        "deadline_today": "مهم: مهلت امروز است، {date}.",
        "overdue": "توجه: مهلت {date} بود. این مهلت گذشته است.",
        "no_deadline": "در این نامه مهلت مشخصی وجود ندارد.",
        "pay": "شما باید {amount} پرداخت کنید.",
        "receive": "شما {amount} دریافت می‌کنید. لازم نیست چیزی پرداخت کنید.",
        "no_pay": "لازم نیست چیزی پرداخت کنید.",
        "unclear_amount": "توجه: مبلغی برای پرداخت وجود دارد، اما نتوانستم آن را بخوانم. لطفاً نامه را با کمک کسی بررسی کنید.",
        "reference": "شمارهٔ مرجع شما {ref} است. همیشه این شماره را ذکر کنید.",
        "explain": "حالا توضیح.",
        "repeat": "یک بار دیگر، مهم‌ترین نکته: {action}",
        "short_deadline": "مهلت: {date}.",
        "euro": "{e} یورو و {c} سنت",
        "euro_round": "{e} یورو",
        "help": "اگر مطمئن نیستید، از کسی که به او اعتماد دارید یا از یک مرکز مشاوره بخواهید نامهٔ اصلی را بررسی کند.",
        "bad_photo": "نتوانستم این نامه را خوب بخوانم. لطفاً دوباره عکس بگیرید: در نور خوب، طوری که کل صفحه دیده شود و گوشی درست بالای آن باشد.",
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
    """Date with weekday, as people say it: 'Friday, 4 December 2026', 'Freitag, 4. Dezember 2026'."""
    weekday = WEEKDAYS[lang][d.weekday()]
    if lang == "de":
        return f"{weekday}, {d.day}. {MONTHS[lang][d.month - 1]} {d.year}"
    if lang == "fr":
        return f"{weekday} {d.day} {MONTHS[lang][d.month - 1]} {d.year}"
    if lang == "ar":
        return f"يوم {weekday} {d.day} {MONTHS[lang][d.month - 1]} {d.year}"
    if lang == "tr":
        return f"{d.day} {MONTHS[lang][d.month - 1]} {d.year} {weekday}"
    if lang in ("ru", "uk"):
        # weekday in brackets: after "до" (until) it would need another grammatical case
        year = "года" if lang == "ru" else "року"
        return f"{d.day} {MONTHS[lang][d.month - 1]} {d.year} {year} ({weekday})"
    if lang == "fa":
        return f"{weekday} {d.day} {MONTHS[lang][d.month - 1]} {d.year}"
    return f"{weekday}, {d.day} {MONTHS[lang][d.month - 1]} {d.year}"


# Russian and Ukrainian change the noun after a number: 1 цент, 2 цента, 5 центов. ("евро/євро" never changes.)
CENT_FORMS = {"ru": ("цент", "цента", "центов"), "uk": ("цент", "центи", "центів")}


def plural(n: int, forms: tuple[str, str, str]) -> str:
    """East Slavic plural: forms = (1, 2-4, 5+), e.g. 1 цент, 3 цента, 11 центов, 21 цент."""
    if n % 10 == 1 and n % 100 != 11:
        return forms[0]
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return forms[1]
    return forms[2]


def say_amount(amount: Decimal, lang: str) -> str:
    euros = int(amount)
    cents = int((amount - euros) * 100)
    template = TEXT[lang]["euro"] if cents else TEXT[lang]["euro_round"]
    cents_word = plural(cents, CENT_FORMS[lang]) if lang in CENT_FORMS else ""
    return template.format(e=euros, c=cents, cents=cents_word)


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
