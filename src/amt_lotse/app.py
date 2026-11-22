"""Amt-Lotse web UI, designed for blind people, older people and new immigrants.

Start:
    uv run amt-lotse-ui          # only this computer: http://127.0.0.1:7860
    uv run amt-lotse-ui --lan    # also your phone on the same Wi-Fi (password protected)
    uv run amt-lotse-ui --tailscale   # phone app with HTTPS, also away from home (see README)
    uv run amt-lotse-ui --share       # temporary public link, e.g. for a demo (password protected, see warning)

Design rules
- Three steps only: 1 language, 2 letter, 3 result. Everything else is folded away.
- The whole page speaks the chosen language (labels, buttons, messages, lang/dir attributes,
  so screen readers switch to the right voice). The choice is remembered.
- Uploading a letter starts the explanation: no button needs to be found.
- The first thing in the result is ONE sentence: what you must do, by when. Built from
  code-checked facts, red when 7 days or fewer are left.
- Status messages are announced to screen readers; focus jumps to the result when it is ready.
- Large text, large buttons, visible keyboard focus, text size and high-contrast buttons.
"""

import argparse
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

# Privacy: Gradio sends usage statistics to its servers by default. Amt-Lotse promises that nothing leaves
# the computer, so this is switched off before Gradio is imported (Docker sets the same variable).
os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")

import gradio as gr  # noqa: E402

from amt_lotse.ask import answer_question
from amt_lotse.cli import LANGUAGES, RTL_LANGUAGES, explain
from amt_lotse.extract import ModelLoopError, ai_online
from amt_lotse.landing import (
    TEXT,
    ai_status_html,
    art_html,
    brand_html,
    example_labels,
    facts_html,
    hero_html,
    info_html,
)
from amt_lotse.pipeline import analyze, calendar_file, todo_box
from amt_lotse.reply import build_reply
from amt_lotse.speak import SpokenFacts, build_script, speak

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = [  # fictional test letters, safe to show
    PROJECT_ROOT / "data" / "photos" / "jobcenter_01_photo.jpg",
    PROJECT_ROOT / "data" / "photos" / "mahnung_01_scan.png",
    PROJECT_ROOT / "data" / "photos" / "finanzamt_02_digital.pdf",
    PROJECT_ROOT / "data" / "eval" / "krankenkasse_02.txt",
]
ICON = Path(__file__).resolve().parent / "static" / "icon.png"
LANG_CHOICES = [("English", "en"), ("Français", "fr"), ("العربية", "ar"), ("Türkçe", "tr"), ("Українська", "uk"),
                ("Русский", "ru"), ("فارسی", "fa"), ("Deutsch (einfach)", "de")]

# ---------------------------------------------------------------- all visible text, per language
UI = {
    "en": {
        "title": "Amt-Lotse", "subtitle": "Understand letters from German offices — in your language, read aloud, privately on this computer.",
        "step1": "1. Choose your language", "step2": "2. Your letter",
        "hint2": "Take a photo of the letter with your phone, or choose a file (photo, PDF or text). The explanation starts by itself. Several pages: choose them all, or add them one by one after the first.",
        "file": "Letter", "camera": "📷 Take a photo of the letter", "more": "📷 Add the next page", "pages_n": "Letter with {n} pages.", "bad_page": "Page {p} could not be read, so it was left out. Please photograph it again with “Add the next page”: good light, the whole page, phone straight above it.", "cut": "This letter is very long. Only the first pages were read.",

        "ask_h": "Ask a question about this letter", "ask_hint": "Press the microphone and ask in your language, or type your question. The answer comes only from this letter.", "ask_mic": "🎤 Speak your question", "ask_text": "Your question", "ask_ph": "For example: What happens if I don't pay?", "ask_btn": "Answer my question", "s_listen": "Listening to what you said …", "s_answer": "Looking for the answer in the letter …", "no_speech": "I could not understand the recording. Please try again, a little closer to the microphone.", "note_mic": "🎤 Or say it", "voice_error": "The recording could not be turned into text ({e}). Please try again or type your question.", "you_asked": "You asked",
        "examples": "Try it with an example letter (not a real letter)",
        "go": "Explain the letter", "step3": "3. Result",
        "listen_again": "Listen again", "calendar": "Add the deadline to my calendar",
        "read": "What the computer read (for a helper to check)",
        "reply": "Write a reply in German", "intent": "What do you want to say?",
        "note": "Your own information (optional, any language)", "note_ph": "e.g. I am sick until 10 December",
        "reply_btn": "Write the reply", "reply_text": "Reply in German – fill in every [ ] before sending", "download": "Download",
        "settings": "Settings", "read_aloud": "Read the result aloud automatically", "slow": "Speak slowly",
        "bigger": "Bigger text", "smaller": "Smaller text", "contrast": "High contrast",
        "footer": "This is an automatic summary. Always check the original letter. It is not legal advice — for important decisions, ask an advice centre (Beratungsstelle).",
        "s_read": "Reading the letter …", "s_facts": "Finding the deadline and the amount …",
        "s_explain": "Writing the explanation …", "s_audio": "Creating the audio …", "s_done": "Done. The result is below.",
        "s_reply": "Writing the reply …", "s_reply_done": "The reply is ready.",
        "first_time": "The first time can take 1–2 minutes. Please wait.",
        "bad": "The letter could not be read well. Please take the photo again: good light, the whole page, phone held straight above it.",
        "no_file": "Please add a letter first (step 2).", "error": "Something went wrong: {e}. Is Ollama running?", "stuck": "The AI model got stuck and repeated itself. Please press the button again. If it happens again, take a new, sharper photo.",
        "intents": {"more-time": "Ask for more time", "installments": "Ask to pay in parts (installments)",
                    "already-paid": "Say that I already paid", "reschedule": "Ask for a new appointment",
                    "question": "Ask a question about the letter"},
    },
    "fr": {
        "title": "Amt-Lotse", "subtitle": "Comprendre les lettres des administrations allemandes — dans votre langue, à voix haute, en privé sur cet ordinateur.",
        "step1": "1. Choisissez votre langue", "step2": "2. Votre lettre",
        "hint2": "Prenez la lettre en photo avec votre téléphone, ou choisissez un fichier (photo, PDF ou texte). L'explication démarre toute seule. Plusieurs pages : choisissez-les toutes, ou ajoutez-les une par une après la première.",
        "file": "Lettre", "camera": "📷 Photographier la lettre", "more": "📷 Ajouter la page suivante", "pages_n": "Lettre de {n} pages.", "bad_page": "La page {p} n'a pas pu être lue, elle a été retirée. Photographiez-la de nouveau avec « Ajouter la page suivante » : bonne lumière, page entière, téléphone bien au-dessus.", "cut": "Cette lettre est très longue. Seules les premières pages ont été lues.",

        "ask_h": "Poser une question sur cette lettre", "ask_hint": "Appuyez sur le micro et posez votre question dans votre langue, ou écrivez-la. La réponse vient uniquement de cette lettre.", "ask_mic": "🎤 Dites votre question", "ask_text": "Votre question", "ask_ph": "Par exemple : que se passe-t-il si je ne paie pas ?", "ask_btn": "Répondre à ma question", "s_listen": "J'écoute ce que vous avez dit …", "s_answer": "Je cherche la réponse dans la lettre …", "no_speech": "Je n'ai pas compris l'enregistrement. Réessayez, un peu plus près du micro.", "note_mic": "🎤 Ou dites-le", "voice_error": "L'enregistrement n'a pas pu être transformé en texte ({e}). Réessayez ou écrivez votre question.", "you_asked": "Votre question",
        "examples": "Essayer avec une lettre d'exemple (pas une vraie lettre)",
        "go": "Expliquer la lettre", "step3": "3. Résultat",
        "listen_again": "Écouter encore", "calendar": "Ajouter la date limite à mon agenda",
        "read": "Ce que l'ordinateur a lu (pour vérification par une autre personne)",
        "reply": "Écrire une réponse en allemand", "intent": "Que voulez-vous dire ?",
        "note": "Vos informations (facultatif, dans n'importe quelle langue)", "note_ph": "p. ex. je suis malade jusqu'au 10 décembre",
        "reply_btn": "Écrire la réponse", "reply_text": "Réponse en allemand – remplissez chaque [ ] avant l'envoi", "download": "Télécharger",
        "settings": "Réglages", "read_aloud": "Lire le résultat à voix haute automatiquement", "slow": "Parler lentement",
        "bigger": "Texte plus grand", "smaller": "Texte plus petit", "contrast": "Contraste élevé",
        "footer": "Ceci est un résumé automatique. Vérifiez toujours la lettre originale. Ce n'est pas un conseil juridique — pour les décisions importantes, demandez à un centre de conseil (Beratungsstelle).",
        "s_read": "Lecture de la lettre …", "s_facts": "Recherche de la date limite et du montant …",
        "s_explain": "Rédaction de l'explication …", "s_audio": "Création de l'audio …", "s_done": "Terminé. Le résultat est ci-dessous.",
        "s_reply": "Rédaction de la réponse …", "s_reply_done": "La réponse est prête.",
        "first_time": "La première fois peut prendre 1 à 2 minutes. Merci de patienter.",
        "bad": "La lettre n'a pas pu être bien lue. Reprenez la photo : bonne lumière, page entière, téléphone bien au-dessus.",
        "no_file": "Ajoutez d'abord une lettre (étape 2).", "error": "Une erreur est survenue : {e}. Ollama est-il lancé ?", "stuck": "Le modèle d'IA s'est bloqué et s'est répété. Appuyez de nouveau sur le bouton. Si cela recommence, prenez une nouvelle photo plus nette.",
        "intents": {"more-time": "Demander plus de temps", "installments": "Demander à payer en plusieurs fois",
                    "already-paid": "Dire que j'ai déjà payé", "reschedule": "Demander un nouveau rendez-vous",
                    "question": "Poser une question sur la lettre"},
    },
    "ar": {
        "title": "Amt-Lotse", "subtitle": "افهم رسائل الإدارات الألمانية — بلغتك، بصوت مسموع، وبخصوصية تامة على هذا الحاسوب.",
        "step1": "الخطوة 1: اختر لغتك", "step2": "الخطوة 2: رسالتك",
        "hint2": "التقط صورة للرسالة بهاتفك، أو اختر ملفا: صورة أو ملف PDF أو نص. يبدأ الشرح تلقائيا. عدة صفحات: اخترها كلها، أو أضفها واحدة بعد الأخرى بعد الأولى.",
        "file": "الرسالة", "camera": "📷 صوّر الرسالة", "more": "📷 أضف الصفحة التالية", "pages_n": "رسالة من {n} صفحات.", "bad_page": "لم تمكن قراءة الصفحة {p}، لذلك تم حذفها. من فضلك صوّرها مرة أخرى بزر «أضف الصفحة التالية»: إضاءة جيدة، الصفحة كاملة، والهاتف فوقها مباشرة.", "cut": "هذه الرسالة طويلة جدا. تمت قراءة الصفحات الأولى فقط.",

        "ask_h": "اسأل سؤالا عن هذه الرسالة", "ask_hint": "اضغط على الميكروفون واسأل بلغتك، أو اكتب سؤالك. الجواب يأتي فقط من هذه الرسالة.", "ask_mic": "🎤 قل سؤالك", "ask_text": "سؤالك", "ask_ph": "مثلا: ماذا يحدث إذا لم أدفع؟", "ask_btn": "أجب عن سؤالي", "s_listen": "أستمع إلى ما قلته …", "s_answer": "أبحث عن الجواب في الرسالة …", "no_speech": "لم أفهم التسجيل. من فضلك حاول مرة أخرى، أقرب قليلا من الميكروفون.", "note_mic": "🎤 أو قله بصوتك", "voice_error": "تعذر تحويل التسجيل إلى نص ({e}). من فضلك حاول مرة أخرى أو اكتب سؤالك.", "you_asked": "سؤالك",
        "examples": "جرّب برسالة نموذجية (ليست رسالة حقيقية)",
        "go": "اشرح الرسالة", "step3": "الخطوة 3: النتيجة",
        "listen_again": "استمع مرة أخرى", "calendar": "أضف الموعد النهائي إلى تقويمي",
        "read": "ما قرأه الحاسوب (ليتحقق منه شخص آخر)",
        "reply": "اكتب ردا بالألمانية", "intent": "ماذا تريد أن تقول؟",
        "note": "معلوماتك الخاصة (اختياري، بأي لغة)", "note_ph": "مثلا: أنا مريض حتى 10 ديسمبر",
        "reply_btn": "اكتب الرد", "reply_text": "الرد بالألمانية – املأ كل [ ] قبل الإرسال", "download": "تنزيل",
        "settings": "الإعدادات", "read_aloud": "اقرأ النتيجة بصوت مسموع تلقائيا", "slow": "تحدث ببطء",
        "bigger": "نص أكبر", "smaller": "نص أصغر", "contrast": "تباين عال",
        "footer": "هذا ملخص آلي. راجع دائما الرسالة الأصلية. هذه ليست استشارة قانونية — للقرارات المهمة اسأل مركز استشارة (Beratungsstelle).",
        "s_read": "جار قراءة الرسالة …", "s_facts": "جار البحث عن الموعد والمبلغ …",
        "s_explain": "جار كتابة الشرح …", "s_audio": "جار إنشاء الصوت …", "s_done": "انتهى. النتيجة في الأسفل.",
        "s_reply": "جار كتابة الرد …", "s_reply_done": "الرد جاهز.",
        "first_time": "قد تستغرق المرة الأولى دقيقة أو دقيقتين. من فضلك انتظر.",
        "bad": "لم تتم قراءة الرسالة جيدا. من فضلك التقط الصورة مرة أخرى: إضاءة جيدة، الصفحة كاملة، والهاتف مستقيم فوقها.",
        "no_file": "من فضلك أضف رسالة أولا (الخطوة 2).", "error": "حدث خطأ: {e}. هل برنامج Ollama يعمل؟", "stuck": "توقف نموذج الذكاء الاصطناعي وكرر نفسه. من فضلك اضغط على الزر مرة أخرى. إذا تكرر ذلك، التقط صورة جديدة أوضح.",
        "intents": {"more-time": "طلب مهلة إضافية", "installments": "طلب الدفع على أقساط",
                    "already-paid": "القول إنني دفعت بالفعل", "reschedule": "طلب موعد جديد",
                    "question": "طرح سؤال عن الرسالة"},
    },
    "de": {
        "title": "Amt-Lotse", "subtitle": "Briefe von Ämtern verstehen — in Ihrer Sprache, vorgelesen, privat auf diesem Computer.",
        "step1": "1. Sprache wählen", "step2": "2. Ihr Brief",
        "hint2": "Machen Sie mit dem Handy ein Foto vom Brief, oder wählen Sie eine Datei (Foto, PDF oder Text). Die Erklärung startet von selbst. Mehrere Seiten: alle auswählen, oder nach der ersten eine nach der anderen hinzufügen.",
        "file": "Brief", "camera": "📷 Brief fotografieren", "more": "📷 Nächste Seite hinzufügen", "pages_n": "Brief mit {n} Seiten.", "bad_page": "Seite {p} war nicht lesbar und wurde herausgenommen. Bitte fotografieren Sie sie noch einmal mit „Nächste Seite hinzufügen“: gutes Licht, ganze Seite, Handy gerade darüber.", "cut": "Dieser Brief ist sehr lang. Nur die ersten Seiten wurden gelesen.",

        "ask_h": "Eine Frage zu diesem Brief stellen", "ask_hint": "Drücken Sie auf das Mikrofon und fragen Sie in Ihrer Sprache, oder schreiben Sie die Frage. Die Antwort kommt nur aus diesem Brief.", "ask_mic": "🎤 Frage sprechen", "ask_text": "Ihre Frage", "ask_ph": "Zum Beispiel: Was passiert, wenn ich nicht zahle?", "ask_btn": "Frage beantworten", "s_listen": "Ich höre, was Sie gesagt haben …", "s_answer": "Ich suche die Antwort im Brief …", "no_speech": "Ich konnte die Aufnahme nicht verstehen. Bitte noch einmal, etwas näher am Mikrofon.", "note_mic": "🎤 Oder sprechen Sie es", "voice_error": "Die Aufnahme konnte nicht in Text umgewandelt werden ({e}). Bitte noch einmal versuchen oder die Frage schreiben.", "you_asked": "Ihre Frage",
        "examples": "Mit einem Beispielbrief ausprobieren (kein echter Brief)",
        "go": "Brief erklären", "step3": "3. Ergebnis",
        "listen_again": "Noch einmal anhören", "calendar": "Frist in meinen Kalender eintragen",
        "read": "Was der Computer gelesen hat (zum Prüfen durch eine Hilfsperson)",
        "reply": "Eine Antwort schreiben", "intent": "Was möchten Sie sagen?",
        "note": "Ihre eigenen Angaben (freiwillig, in jeder Sprache)", "note_ph": "z. B. Ich bin bis 10. Dezember krank",
        "reply_btn": "Antwort schreiben", "reply_text": "Antwort – füllen Sie jedes [ ] vor dem Senden aus", "download": "Herunterladen",
        "settings": "Einstellungen", "read_aloud": "Ergebnis automatisch vorlesen", "slow": "Langsam sprechen",
        "bigger": "Größere Schrift", "smaller": "Kleinere Schrift", "contrast": "Hoher Kontrast",
        "footer": "Dies ist eine automatische Zusammenfassung. Prüfen Sie immer den Originalbrief. Keine Rechtsberatung — bei wichtigen Entscheidungen fragen Sie eine Beratungsstelle.",
        "s_read": "Der Brief wird gelesen …", "s_facts": "Frist und Betrag werden gesucht …",
        "s_explain": "Die Erklärung wird geschrieben …", "s_audio": "Die Audiodatei wird erstellt …", "s_done": "Fertig. Das Ergebnis steht unten.",
        "s_reply": "Die Antwort wird geschrieben …", "s_reply_done": "Die Antwort ist fertig.",
        "first_time": "Beim ersten Mal kann es 1–2 Minuten dauern. Bitte warten.",
        "bad": "Der Brief war nicht gut lesbar. Bitte machen Sie das Foto noch einmal: gutes Licht, ganze Seite, Handy gerade darüber.",
        "no_file": "Bitte fügen Sie zuerst einen Brief hinzu (Schritt 2).", "error": "Es gab einen Fehler: {e}. Läuft Ollama?", "stuck": "Das KI-Modell ist hängen geblieben und hat sich wiederholt. Bitte drücken Sie noch einmal auf den Knopf. Wenn es wieder passiert, machen Sie ein neues, schärferes Foto.",
        "intents": {"more-time": "Um mehr Zeit bitten", "installments": "Um Ratenzahlung bitten",
                    "already-paid": "Sagen, dass ich schon bezahlt habe", "reschedule": "Um einen neuen Termin bitten",
                    "question": "Eine Frage zum Brief stellen"},
    },
    "tr": {
        "title": "Amt-Lotse",
        "subtitle": "Alman resmi kurumlarından gelen mektupları anlayın — kendi dilinizde, sesli olarak, bu bilgisayarda gizli kalarak.",
        "step1": "1. Dilinizi seçin",
        "step2": "2. Mektubunuz",
        "hint2": "Mektubun fotoğrafını telefonunuzla çekin ya da bir dosya seçin (fotoğraf, PDF veya metin). Açıklama kendiliğinden başlar. Birden fazla sayfa: hepsini seçin ya da ilkinden sonra tek tek ekleyin.",
        "file": "Mektup",
        "camera": "📷 Mektubun fotoğrafını çek",
        "more": "📷 Sonraki sayfayı ekle",
        "pages_n": "{n} sayfalık mektup.",
        "bad_page": "{p}. sayfa okunamadı, bu yüzden çıkarıldı. Lütfen “Sonraki sayfayı ekle” ile tekrar fotoğraflayın: iyi ışık, sayfanın tamamı, telefon tam üstünde.",
        "cut": "Bu mektup çok uzun. Sadece ilk sayfalar okundu.",
        "ask_h": "Bu mektup hakkında soru sorun",
        "ask_hint": "Mikrofona basın ve kendi dilinizde sorun ya da sorunuzu yazın. Cevap yalnızca bu mektuptan gelir.",
        "ask_mic": "🎤 Sorunuzu söyleyin",
        "ask_text": "Sorunuz",
        "ask_ph": "Örneğin: Ödemezsem ne olur?",
        "ask_btn": "Soruma cevap ver",
        "s_listen": "Söylediklerinizi dinliyorum …",
        "s_answer": "Cevabı mektupta arıyorum …",
        "no_speech": "Kaydı anlayamadım. Lütfen mikrofona biraz daha yakın olarak tekrar deneyin.",
        "note_mic": "🎤 Ya da söyleyin",
        "voice_error": "Kayıt metne çevrilemedi ({e}). Lütfen tekrar deneyin ya da sorunuzu yazın.",
        "you_asked": "Sorunuz",
        "examples": "Örnek bir mektupla deneyin (gerçek bir mektup değil)",
        "go": "Mektubu açıkla",
        "step3": "3. Sonuç",
        "listen_again": "Tekrar dinle",
        "calendar": "Son tarihi takvimime ekle",
        "read": "Bilgisayarın okudukları (kontrol edecek biri için)",
        "reply": "Almanca cevap yaz",
        "intent": "Ne söylemek istiyorsunuz?",
        "note": "Kendi bilgileriniz (isteğe bağlı, herhangi bir dilde)",
        "note_ph": "örn. 10 Aralık'a kadar hastayım",
        "reply_btn": "Cevabı yaz",
        "reply_text": "Almanca cevap – göndermeden önce her [ ] alanını doldurun",
        "download": "İndir",
        "settings": "Ayarlar",
        "read_aloud": "Sonucu otomatik olarak sesli oku",
        "slow": "Yavaş konuş",
        "bigger": "Daha büyük yazı",
        "smaller": "Daha küçük yazı",
        "contrast": "Yüksek kontrast",
        "footer": "Bu otomatik bir özettir. Her zaman asıl mektubu kontrol edin. Hukuki tavsiye değildir — önemli kararlar için bir danışma merkezine (Beratungsstelle) başvurun.",
        "s_read": "Mektup okunuyor …",
        "s_facts": "Son tarih ve tutar bulunuyor …",
        "s_explain": "Açıklama yazılıyor …",
        "s_audio": "Ses oluşturuluyor …",
        "s_done": "Tamam. Sonuç aşağıda.",
        "s_reply": "Cevap yazılıyor …",
        "s_reply_done": "Cevap hazır.",
        "first_time": "İlk seferde 1–2 dakika sürebilir. Lütfen bekleyin.",
        "bad": "Mektup iyi okunamadı. Lütfen fotoğrafı tekrar çekin: iyi ışık, sayfanın tamamı, telefon tam üstünde.",
        "no_file": "Lütfen önce bir mektup ekleyin (2. adım).",
        "error": "Bir hata oluştu: {e}. Ollama çalışıyor mu?",
        "stuck": "Yapay zekâ modeli takıldı ve kendini tekrarladı. Lütfen düğmeye tekrar basın. Tekrar olursa yeni ve daha net bir fotoğraf çekin.",
        "intents": {
            "more-time": "Ek süre iste",
            "installments": "Taksitle ödemek iste",
            "already-paid": "Zaten ödediğimi söyle",
            "reschedule": "Yeni randevu iste",
            "question": "Mektup hakkında soru sor",
        },
    },
    "uk": {
        "title": "Amt-Lotse",
        "subtitle": "Розумійте листи від німецьких установ — вашою мовою, вголос і конфіденційно, на цьому комп’ютері.",
        "step1": "1. Оберіть мову",
        "step2": "2. Ваш лист",
        "hint2": "Сфотографуйте лист телефоном або виберіть файл (фото, PDF чи текст). Пояснення почнеться саме. Кілька сторінок: виберіть усі одразу або додавайте по одній після першої.",
        "file": "Лист",
        "camera": "📷 Сфотографувати лист",
        "more": "📷 Додати наступну сторінку",
        "pages_n": "Сторінок у листі: {n}.",
        "bad_page": "Сторінку {p} не вдалося прочитати, тому її прибрано. Сфотографуйте її ще раз кнопкою «Додати наступну сторінку»: гарне світло, уся сторінка, телефон прямо над нею.",
        "cut": "Цей лист дуже довгий. Прочитано лише перші сторінки.",
        "ask_h": "Поставити запитання про цей лист",
        "ask_hint": "Натисніть на мікрофон і запитайте своєю мовою або напишіть запитання. Відповідь береться лише з цього листа.",
        "ask_mic": "🎤 Скажіть своє запитання",
        "ask_text": "Ваше запитання",
        "ask_ph": "Наприклад: що буде, якщо я не заплачу?",
        "ask_btn": "Відповісти на моє запитання",
        "s_listen": "Слухаю, що ви сказали …",
        "s_answer": "Шукаю відповідь у листі …",
        "no_speech": "Не вдалося розібрати запис. Спробуйте ще раз, трохи ближче до мікрофона.",
        "note_mic": "🎤 Або скажіть це",
        "voice_error": "Запис не вдалося перетворити на текст ({e}). Спробуйте ще раз або напишіть запитання.",
        "you_asked": "Ваше запитання",
        "examples": "Спробуйте на прикладі (не справжній лист)",
        "go": "Пояснити лист",
        "step3": "3. Результат",
        "listen_again": "Прослухати ще раз",
        "calendar": "Додати строк до мого календаря",
        "read": "Що прочитав комп’ютер (для перевірки помічником)",
        "reply": "Написати відповідь німецькою",
        "intent": "Що ви хочете сказати?",
        "note": "Ваша інформація (необов’язково, будь-якою мовою)",
        "note_ph": "наприклад: я хворію до 10 грудня",
        "reply_btn": "Написати відповідь",
        "reply_text": "Відповідь німецькою – перед надсиланням заповніть усі [ ]",
        "download": "Завантажити",
        "settings": "Налаштування",
        "read_aloud": "Автоматично читати результат уголос",
        "slow": "Говорити повільно",
        "bigger": "Більший текст",
        "smaller": "Менший текст",
        "contrast": "Високий контраст",
        "footer": "Це автоматичний короткий виклад. Завжди перевіряйте оригінал листа. Це не юридична консультація — для важливих рішень зверніться до консультаційного центру (Beratungsstelle).",
        "s_read": "Читаю лист …",
        "s_facts": "Шукаю строк і суму …",
        "s_explain": "Пишу пояснення …",
        "s_audio": "Створюю аудіо …",
        "s_done": "Готово. Результат нижче.",
        "s_reply": "Пишу відповідь …",
        "s_reply_done": "Відповідь готова.",
        "first_time": "Першого разу це може тривати 1–2 хвилини. Будь ласка, зачекайте.",
        "bad": "Лист не вдалося добре прочитати. Сфотографуйте його ще раз: гарне світло, уся сторінка, телефон прямо над нею.",
        "no_file": "Спочатку додайте лист (крок 2).",
        "error": "Сталася помилка: {e}. Чи запущено Ollama?",
        "stuck": "Модель ШІ зависла й повторювалася. Натисніть кнопку ще раз. Якщо це повториться, зробіть нове, чіткіше фото.",
        "intents": {
            "more-time": "Попросити більше часу",
            "installments": "Попросити оплату частинами (розстрочку)",
            "already-paid": "Повідомити, що я вже заплатив(ла)",
            "reschedule": "Попросити нову дату зустрічі",
            "question": "Поставити запитання про лист",
        },
    },
    "ru": {
        "title": "Amt-Lotse",
        "subtitle": "Понимайте письма из немецких ведомств — на вашем языке, вслух и конфиденциально, на этом компьютере.",
        "step1": "1. Выберите язык",
        "step2": "2. Ваше письмо",
        "hint2": "Сфотографируйте письмо телефоном или выберите файл (фото, PDF или текст). Объяснение начнётся само. Несколько страниц: выберите все сразу или добавляйте по одной после первой.",
        "file": "Письмо",
        "camera": "📷 Сфотографировать письмо",
        "more": "📷 Добавить следующую страницу",
        "pages_n": "Страниц в письме: {n}.",
        "bad_page": "Страницу {p} не удалось прочитать, поэтому она убрана. Сфотографируйте её ещё раз кнопкой «Добавить следующую страницу»: хороший свет, вся страница, телефон прямо над ней.",
        "cut": "Это письмо очень длинное. Прочитаны только первые страницы.",
        "ask_h": "Задать вопрос об этом письме",
        "ask_hint": "Нажмите на микрофон и спросите на своём языке или напишите вопрос. Ответ берётся только из этого письма.",
        "ask_mic": "🎤 Произнесите вопрос",
        "ask_text": "Ваш вопрос",
        "ask_ph": "Например: что будет, если я не заплачу?",
        "ask_btn": "Ответить на мой вопрос",
        "s_listen": "Слушаю, что вы сказали …",
        "s_answer": "Ищу ответ в письме …",
        "no_speech": "Не удалось разобрать запись. Попробуйте ещё раз, чуть ближе к микрофону.",
        "note_mic": "🎤 Или скажите это",
        "voice_error": "Запись не удалось превратить в текст ({e}). Попробуйте ещё раз или напишите вопрос.",
        "you_asked": "Ваш вопрос",
        "examples": "Попробуйте на примере (не настоящее письмо)",
        "go": "Объяснить письмо",
        "step3": "3. Результат",
        "listen_again": "Прослушать ещё раз",
        "calendar": "Добавить срок в мой календарь",
        "read": "Что прочитал компьютер (для проверки помощником)",
        "reply": "Написать ответ на немецком",
        "intent": "Что вы хотите сказать?",
        "note": "Ваша информация (необязательно, на любом языке)",
        "note_ph": "например: я болею до 10 декабря",
        "reply_btn": "Написать ответ",
        "reply_text": "Ответ на немецком – перед отправкой заполните все [ ]",
        "download": "Скачать",
        "settings": "Настройки",
        "read_aloud": "Автоматически читать результат вслух",
        "slow": "Говорить медленно",
        "bigger": "Крупнее текст",
        "smaller": "Мельче текст",
        "contrast": "Высокий контраст",
        "footer": "Это автоматическое краткое изложение. Всегда проверяйте оригинал письма. Это не юридическая консультация — для важных решений обратитесь в консультационный центр (Beratungsstelle).",
        "s_read": "Читаю письмо …",
        "s_facts": "Ищу срок и сумму …",
        "s_explain": "Пишу объяснение …",
        "s_audio": "Создаю аудио …",
        "s_done": "Готово. Результат ниже.",
        "s_reply": "Пишу ответ …",
        "s_reply_done": "Ответ готов.",
        "first_time": "В первый раз это может занять 1–2 минуты. Пожалуйста, подождите.",
        "bad": "Письмо не удалось хорошо прочитать. Сфотографируйте его ещё раз: хороший свет, вся страница, телефон прямо над ней.",
        "no_file": "Сначала добавьте письмо (шаг 2).",
        "error": "Произошла ошибка: {e}. Запущена ли Ollama?",
        "stuck": "Модель ИИ зависла и повторялась. Нажмите кнопку ещё раз. Если это повторится, сделайте новое, более чёткое фото.",
        "intents": {
            "more-time": "Попросить больше времени",
            "installments": "Попросить оплату частями (рассрочку)",
            "already-paid": "Сообщить, что я уже заплатил(а)",
            "reschedule": "Попросить новую дату встречи",
            "question": "Задать вопрос о письме",
        },
    },
    "fa": {
        "title": "Amt-Lotse",
        "subtitle": "نامه‌های اداره‌های آلمانی را بفهمید — به زبان خودتان، با صدای بلند، و به‌صورت خصوصی روی همین رایانه.",
        "step1": "۱. زبان خود را انتخاب کنید",
        "step2": "۲. نامهٔ شما",
        "hint2": "با تلفن از نامه عکس بگیرید یا یک فایل انتخاب کنید (عکس، PDF یا متن). توضیح خودبه‌خود شروع می‌شود. چند صفحه: همه را با هم انتخاب کنید یا بعد از صفحهٔ اول یکی‌یکی اضافه کنید.",
        "file": "نامه",
        "camera": "📷 از نامه عکس بگیرید",
        "more": "📷 صفحهٔ بعدی را اضافه کنید",
        "pages_n": "نامهٔ {n} صفحه‌ای.",
        "bad_page": "صفحهٔ {p} خوانده نشد و کنار گذاشته شد. لطفاً با دکمهٔ «صفحهٔ بعدی را اضافه کنید» دوباره از آن عکس بگیرید: نور خوب، کل صفحه، گوشی درست بالای آن.",
        "cut": "این نامه خیلی طولانی است. فقط صفحه‌های اول خوانده شد.",
        "ask_h": "دربارهٔ این نامه سؤال بپرسید",
        "ask_hint": "دکمهٔ میکروفون را بزنید و به زبان خودتان بپرسید، یا سؤالتان را بنویسید. پاسخ فقط از همین نامه می‌آید.",
        "ask_mic": "🎤 سؤالتان را بگویید",
        "ask_text": "سؤال شما",
        "ask_ph": "مثلاً: اگر پرداخت نکنم چه می‌شود؟",
        "ask_btn": "به سؤالم پاسخ بده",
        "s_listen": "دارم به حرف شما گوش می‌دهم …",
        "s_answer": "دارم پاسخ را در نامه پیدا می‌کنم …",
        "no_speech": "صدای ضبط‌شده را نفهمیدم. لطفاً دوباره، کمی نزدیک‌تر به میکروفون، امتحان کنید.",
        "note_mic": "🎤 یا آن را بگویید",
        "voice_error": "صدای ضبط‌شده به متن تبدیل نشد ({e}). لطفاً دوباره امتحان کنید یا سؤالتان را بنویسید.",
        "you_asked": "سؤال شما",
        "examples": "با یک نامهٔ نمونه امتحان کنید (نامهٔ واقعی نیست)",
        "go": "نامه را توضیح بده",
        "step3": "۳. نتیجه",
        "listen_again": "دوباره گوش بده",
        "calendar": "مهلت را به تقویمم اضافه کن",
        "read": "آنچه رایانه خواند (برای بررسی توسط یک کمک‌کننده)",
        "reply": "نوشتن پاسخ به آلمانی",
        "intent": "چه می‌خواهید بگویید؟",
        "note": "اطلاعات خودتان (اختیاری، به هر زبانی)",
        "note_ph": "مثلاً: تا 10 دسامبر بیمار هستم",
        "reply_btn": "پاسخ را بنویس",
        "reply_text": "پاسخ به آلمانی – پیش از فرستادن همهٔ [ ] ها را پر کنید",
        "download": "دانلود",
        "settings": "تنظیمات",
        "read_aloud": "نتیجه را خودکار با صدای بلند بخوان",
        "slow": "آهسته صحبت کن",
        "bigger": "متن بزرگ‌تر",
        "smaller": "متن کوچک‌تر",
        "contrast": "کنتراست بالا",
        "footer": "این یک خلاصهٔ خودکار است. همیشه نامهٔ اصلی را بررسی کنید. این مشاورهٔ حقوقی نیست — برای تصمیم‌های مهم از یک مرکز مشاوره (Beratungsstelle) کمک بگیرید.",
        "s_read": "در حال خواندن نامه …",
        "s_facts": "در حال پیدا کردن مهلت و مبلغ …",
        "s_explain": "در حال نوشتن توضیح …",
        "s_audio": "در حال ساختن صدا …",
        "s_done": "انجام شد. نتیجه در پایین است.",
        "s_reply": "در حال نوشتن پاسخ …",
        "s_reply_done": "پاسخ آماده است.",
        "first_time": "بار اول ممکن است ۱ تا ۲ دقیقه طول بکشد. لطفاً صبر کنید.",
        "bad": "نامه خوب خوانده نشد. لطفاً دوباره عکس بگیرید: نور خوب، کل صفحه، گوشی درست بالای آن.",
        "no_file": "لطفاً اول یک نامه اضافه کنید (مرحلهٔ ۲).",
        "error": "خطایی رخ داد: {e}. آیا Ollama در حال اجراست؟",
        "stuck": "مدل هوش مصنوعی گیر کرد و حرفش را تکرار کرد. لطفاً دوباره دکمه را بزنید. اگر باز هم تکرار شد، یک عکس تازه و واضح‌تر بگیرید.",
        "intents": {
            "more-time": "درخواست وقت بیشتر",
            "installments": "درخواست پرداخت قسطی",
            "already-paid": "بگویم که قبلاً پرداخت کرده‌ام",
            "reschedule": "درخواست وقت ملاقات جدید",
            "question": "پرسیدن سؤال دربارهٔ نامه",
        },
    },
}

# ---------------------------------------------------------------- look & feel
CSS = """
:root { --amt-scale: 1; --amt-blue: #1f5fd1; --amt-blue-dark: #174bb0; --amt-ink: #0f1b33; --amt-muted: #45536e;
  --amt-surface: #ffffff; --amt-soft: #f1f5fe; --amt-line: #dbe4f5; --amt-amber: #ffbf47; --amt-red: #c40000;
  --amt-green: #0f8a45; --amt-shadow: 0 1px 2px rgba(15,27,51,.06), 0 12px 32px -12px rgba(15,27,51,.18); }
.dark { --amt-ink: #e8eefc; --amt-muted: #aab6cd; --amt-surface: #131b2c; --amt-soft: #18223a; --amt-line: #2a3650;
  --amt-shadow: 0 1px 2px rgba(0,0,0,.3), 0 12px 32px -12px rgba(0,0,0,.6); }
body, gradio-app { background: radial-gradient(1200px 520px at 85% -10%, #dfe9ff 0%, transparent 60%),
  radial-gradient(900px 480px at -10% 10%, #fff3d6 0%, transparent 55%), #f7f9fe !important; }
.dark body, body.dark, .dark gradio-app { background: radial-gradient(1200px 520px at 85% -10%, #15254a 0%, transparent 60%), #0b1220 !important; }
.gradio-container { --amt-base: calc(20px * var(--amt-scale)); max-width: 1120px !important; margin: auto;
  background: transparent !important; color: var(--amt-ink); }
/* Gradio sets its own px sizes on inner elements, so every text element gets the base size directly. */
.gradio-container p, .gradio-container li, .gradio-container label, .gradio-container label span,
.gradio-container input, .gradio-container textarea, .gradio-container button, .gradio-container .prose,
.gradio-container .label-wrap span {
  font-size: var(--amt-base) !important; line-height: 1.6 !important; }
.gradio-container h2 { font-size: calc(var(--amt-base) * 1.35) !important; margin: .2em 0 .4em !important; letter-spacing: -.01em; }
.gradio-container h3 { font-size: calc(var(--amt-base) * 1.12) !important; }
.gradio-container button { min-height: 56px; border-radius: 14px !important; font-weight: 650 !important; }
.gradio-container .block { border-radius: 16px !important; }
.gradio-container .label-wrap { padding: 14px 18px !important; font-weight: 650; }

/* top bar: logo left, text size and contrast right */
#topbar { align-items: center; justify-content: space-between; flex-wrap: nowrap !important; gap: 12px;
  padding: 6px 0 2px; background: transparent !important; border: 0 !important; }
#topbar > * { flex: 0 1 auto !important; min-width: 0 !important; }
.brand { display: flex; align-items: center; gap: 12px; white-space: nowrap; font-weight: 800; letter-spacing: -.02em;
  font-size: calc(var(--amt-base) * 1.3); color: var(--amt-ink); }
.brand svg { width: 46px; height: 46px; flex: none; }
#toolbar { justify-content: flex-end; gap: 8px; flex-wrap: nowrap !important; background: transparent !important; border: 0 !important; }
#toolbar button { min-height: 46px !important; padding: 6px 14px !important; background: var(--amt-surface) !important;
  border: 1.5px solid var(--amt-line) !important; color: var(--amt-ink) !important; box-shadow: none !important;
  font-size: calc(var(--amt-base) * .8) !important; white-space: nowrap; width: auto !important; flex: none !important;
  display: inline-flex !important; align-items: center; }
#toolbar button::after { content: var(--amt-label, ""); font-weight: 500; margin-inline-start: 6px; }
#bigger { --amt-label: var(--amt-bigger); } #smaller { --amt-label: var(--amt-smaller); } #contrast { --amt-label: var(--amt-contrast); }

/* languages: a grid of big pills, the chosen one filled */
#langs { background: var(--amt-surface) !important; border: 1.5px solid var(--amt-line) !important; border-radius: 20px !important;
  padding: 10px 14px 14px !important; box-shadow: var(--amt-shadow); margin-top: 8px; }
#langs .prose p { margin: 0 0 6px !important; font-weight: 700; color: var(--amt-muted); font-size: calc(var(--amt-base) * .85) !important; }
#langs .form, #tool .form { background: transparent !important; border: 0 !important; box-shadow: none !important; gap: 8px !important; }
#lang { background: transparent !important; border: 0 !important; padding: 0 !important; box-shadow: none !important; }
#lang .wrap { background: transparent !important; padding: 0 !important; display: grid !important; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px !important; }
#lang label { justify-content: center; padding: 10px 12px !important; border-radius: 999px !important; border: 1.5px solid var(--amt-line) !important;
  background: var(--amt-soft) !important; box-shadow: none !important; transition: transform .12s ease, box-shadow .12s ease; cursor: pointer; }
#lang label:hover { transform: translateY(-1px); box-shadow: 0 6px 16px -8px rgba(31,95,209,.5) !important; }
#lang label.selected { background: var(--amt-blue) !important; border-color: var(--amt-blue) !important; }
#lang label.selected, #lang label.selected * { color: #fff !important; }
#lang input[type=radio] { position: absolute; opacity: 0; width: 1px !important; height: 1px !important; }
#lang label:has(input:focus-visible) { outline: 4px solid var(--amt-amber); outline-offset: 2px; }

/* hero */
#hero-row { align-items: center; gap: 24px; margin: 26px 0 8px; }
.hero .eyebrow { display: inline-block; margin: 0 0 12px !important; padding: 6px 14px; border-radius: 999px;
  background: #e6eeff; color: #143f94 !important; font-weight: 700; font-size: calc(var(--amt-base) * .8) !important; }
.dark .hero .eyebrow { background: #1b2c52; color: #bcd0ff !important; }
.hero h1 { font-size: calc(var(--amt-base) * 2.6) !important; line-height: 1.08 !important; letter-spacing: -.035em; margin: 0 0 16px !important;
  font-weight: 850; color: var(--amt-ink); }
.hero .lead { font-size: calc(var(--amt-base) * 1.1) !important; color: var(--amt-muted); margin: 0 0 18px !important; max-width: 36em; }
.badges { display: flex; flex-wrap: wrap; gap: 8px; list-style: none; padding: 0 !important; margin: 0 !important; }
.badges li { margin: 0 !important; padding: 7px 14px 7px 12px; border-radius: 999px; background: var(--amt-surface); border: 1.5px solid var(--amt-line);
  font-weight: 650; font-size: calc(var(--amt-base) * .78) !important; color: var(--amt-ink); }
.badges li::before { content: "✓"; color: var(--amt-green); font-weight: 900; margin-inline-end: 7px; }
.hero-art { display: flex; justify-content: center; }
.hero-art .art { width: 100%; max-width: 400px; height: auto; animation: amt-float 6s ease-in-out infinite; }
@keyframes amt-float { 50% { transform: translateY(-8px); } }
@media (prefers-reduced-motion: reduce) { .hero-art .art { animation: none; } * { transition: none !important; } }

/* the tool: one card, one main button */
#tool { background: var(--amt-surface) !important; border: 1.5px solid var(--amt-line) !important; border-radius: 24px !important;
  padding: 22px 24px !important; box-shadow: var(--amt-shadow); gap: 14px !important; margin-top: 10px; }
#tool .prose p { color: var(--amt-muted); }
#camera { font-size: calc(var(--amt-base) * 1.25) !important; min-height: 78px !important; border: 0 !important;
  background: linear-gradient(135deg, #2a6be0, #1748a8) !important; color: #fff !important;
  box-shadow: 0 10px 24px -10px rgba(23,72,168,.8) !important; transition: transform .12s ease, box-shadow .12s ease; }
#camera:hover { transform: translateY(-2px); box-shadow: 0 16px 30px -12px rgba(23,72,168,.9) !important; }
#letter { border: 2px dashed #9fb7e6 !important; background: var(--amt-soft) !important; min-height: 150px; }
#letter:hover { border-color: var(--amt-blue) !important; }
#letter [data-testid=upload-text] { color: var(--amt-ink) !important; }
/* Gradio's own "Drop File Here - or - Click to Upload" is English only: hidden, the translated text shown instead */
#letter [data-testid=upload-text] { font-size: 0 !important; }
#letter [data-testid=upload-text] .or { display: none !important; }
#letter [data-testid=upload-text]::after { content: var(--amt-drop, ""); font-weight: 650; font-size: var(--amt-base); display: block; margin-top: 6px; line-height: 1.4; }
#examples-h p { margin: 6px 0 0 !important; font-size: calc(var(--amt-base) * .85) !important; font-weight: 700; color: var(--amt-muted) !important; }
#examples { gap: 8px !important; flex-wrap: wrap !important; }
#examples button { flex: 1 1 200px !important; min-height: 50px; background: var(--amt-surface) !important; color: var(--amt-ink) !important;
  border: 1.5px solid var(--amt-line) !important; box-shadow: none !important; font-size: calc(var(--amt-base) * .82) !important;
  font-weight: 600 !important; justify-content: flex-start; }
#examples button:hover { border-color: var(--amt-blue) !important; background: var(--amt-soft) !important; }
#more { display: none !important; }      /* only opened by the "Add the next page" button */

/* status line: a calm pill, with a spinner while working */
#status p { margin: 0 !important; font-weight: 700; }
#status .busy, #status .done, #status .err { display: inline-flex; align-items: center; gap: 12px; padding: 10px 18px; border-radius: 999px; }
#status .busy { background: #e6eeff; color: #143f94 !important; }
#status .done { background: #e3f6ea; color: #0b5d2e !important; }
#status .err { background: #ffecec; color: #6b0000 !important; }
#status .busy::before { content: ""; width: 20px; height: 20px; flex: none; border-radius: 50%; border: 3px solid currentColor;
  border-right-color: transparent; animation: amt-spin .8s linear infinite; }
#status .done::before { content: "✓"; font-weight: 900; }
@keyframes amt-spin { to { transform: rotate(360deg); } }

/* online version: AI computer on or off */
#ai-status:not(:has(.ai-on)):not(:has(.ai-off)) { display: none !important; }   /* no commas inside :has(): Gradio rewrites them */
.ai-on { display: inline-flex; align-items: center; gap: 8px; margin: 0 !important; padding: 6px 14px; border-radius: 999px;
  background: #e3f6ea; color: #0b5d2e !important; font-weight: 700; font-size: calc(var(--amt-base) * .8) !important; }
.ai-on::before { content: ""; width: 10px; height: 10px; border-radius: 50%; background: #12a150; box-shadow: 0 0 0 4px rgba(18,161,80,.2); }
.ai-off { display: flex; flex-direction: column; gap: 4px; padding: 16px 20px; border-radius: 16px; background: #fff4e5 !important;
  border: 2px solid #e08a00; }
.ai-off, .ai-off * { color: #4a2c00 !important; }                 /* contrast 11:1 */
.ai-off strong { font-size: calc(var(--amt-base) * 1.1); }
.ai-off strong::before { content: "⏻  "; }
/* result */
#result { background: var(--amt-surface) !important; border: 1.5px solid var(--amt-line) !important; border-radius: 24px !important;
  padding: 22px 24px !important; box-shadow: var(--amt-shadow); margin-top: 18px; gap: 16px !important; animation: amt-in .35s ease both; }
@keyframes amt-in { from { opacity: 0; transform: translateY(12px); } }
/* Colours forced on every child: the dark theme otherwise paints light text on the light box (contrast 1:1). */
.todo { border-radius: 18px; padding: 20px 24px; margin: 0; background: #e8f1ff !important; border: 3px solid #2f6fdb; }
.todo, .todo * { color: #08245c !important; }            /* contrast 13:1 */
.todo.urgent { background: #ffecec !important; border-color: #c40000; }
.todo.urgent, .todo.urgent * { color: #6b0000 !important; }  /* contrast 11:1 */
.todo .when { display: inline-block; font-weight: 800; font-size: calc(var(--amt-base) * .9) !important; margin-bottom: 6px;
  padding: 3px 12px; border-radius: 999px; background: rgba(255,255,255,.7) !important; text-transform: uppercase; letter-spacing: .04em; }
.todo .what { font-size: calc(var(--amt-base) * 1.45) !important; line-height: 1.45; font-weight: 500; }
#actions { gap: 10px !important; flex-wrap: wrap !important; }
#actions > *, #actions button, #actions a { flex: 1 1 260px !important; }
#actions button { background: var(--amt-soft) !important; color: var(--amt-ink) !important; border: 1.5px solid var(--amt-line) !important; box-shadow: none !important; }
#actions button:hover { border-color: var(--amt-blue) !important; }
#listen button, button#listen { background: var(--amt-blue) !important; color: #fff !important; border-color: var(--amt-blue) !important; }
#audio { border: 1.5px solid var(--amt-line) !important; background: var(--amt-soft) !important; }
.facts ul { list-style: none; padding: 0 !important; margin: 0 !important; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.facts .fact { margin: 0 !important; display: grid; grid-template-columns: auto 1fr; grid-template-rows: auto auto; column-gap: 12px;
  padding: 14px 16px; border-radius: 16px; background: var(--amt-soft); border: 1.5px solid var(--amt-line); }
.facts .ico { grid-row: span 2; font-size: calc(var(--amt-base) * 1.5); line-height: 1.2; }
.facts .label { font-size: calc(var(--amt-base) * .78) !important; font-weight: 700; color: var(--amt-muted); text-transform: uppercase; letter-spacing: .04em; }
.facts .value { font-weight: 650; color: var(--amt-ink); overflow-wrap: anywhere; }
.facts .value small { display: block; font-weight: 500; color: var(--amt-muted); font-size: calc(var(--amt-base) * .8); }
.facts .money { font-size: calc(var(--amt-base) * 1.35); font-weight: 800; }
.facts .fact.hot { background: #fff1f1; border-color: #f1b3b3; } .facts .fact.hot .value, .facts .fact.hot .value small { color: #6b0000; }
.facts .fact.good { background: #ebf8f0; border-color: #a9dcbc; } .facts .fact.good .value { color: #0b5d2e; }
.facts .ref { font-family: ui-monospace, Consolas, monospace; letter-spacing: .08em; }
.facts .warn { margin: 0 0 10px !important; padding: 10px 14px; border-radius: 12px; background: #fff6e0; color: #4a2c00 !important; }
#explanation { padding: 18px 22px !important; border-radius: 18px; background: var(--amt-soft); border-inline-start: 6px solid var(--amt-blue); }
#explanation h3 { margin-top: 0 !important; }
#explanation:not(:has(h3)) { display: none !important; }   /* nothing explained (yet): no empty box */
#ask-card { background: var(--amt-soft) !important; border: 1.5px solid var(--amt-line) !important; border-radius: 20px !important; padding: 18px 20px !important; gap: 10px !important; }
#ask-card .prose h3 { margin: 0 !important; }
.answer { border-radius: 14px; padding: 16px 20px; background: #eef7f0 !important; border: 3px solid #12a150; }
.answer, .answer * { color: #0b3d1f !important; }            /* contrast 12:1 */
.answer.unknown { background: #fff6e0 !important; border-color: #b86e00; }
.answer.unknown, .answer.unknown * { color: #4a2c00 !important; }
.answer .q { font-style: italic; margin: 0 0 6px !important; }
.answer .a { font-size: calc(var(--amt-base) * 1.2) !important; margin: 0 !important; }
#ask-mic, #note-mic { min-height: 0; }

/* how it works + features */
.info { margin: 40px 0 10px; }
.info h2 { text-align: center; margin: 28px 0 18px !important; font-size: calc(var(--amt-base) * 1.6) !important; font-weight: 800; }
.steps, .feats { list-style: none; padding: 0 !important; margin: 0 !important; display: grid; gap: 16px; }
.steps { grid-template-columns: repeat(3, minmax(0, 1fr)); counter-reset: none; }
.feats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.steps li, .feats li { margin: 0 !important; padding: 22px; border-radius: 20px; background: var(--amt-surface); border: 1.5px solid var(--amt-line); box-shadow: var(--amt-shadow); }
.steps h3, .feats h3 { margin: 10px 0 4px !important; color: var(--amt-ink); }
.steps p, .feats p { margin: 0 !important; color: var(--amt-muted); }
.steps .num { display: inline-grid; place-items: center; width: 44px; height: 44px; border-radius: 14px; background: var(--amt-blue); color: #fff;
  font-weight: 800; font-size: calc(var(--amt-base) * 1.1); }
.feats .ico { display: inline-grid; place-items: center; width: 48px; height: 48px; border-radius: 14px; background: var(--amt-soft); font-size: 26px; }
#footer { margin-top: 18px; padding-top: 14px; border-top: 1.5px solid var(--amt-line); }
#footer p { color: var(--amt-muted); font-size: calc(var(--amt-base) * .82) !important; text-align: center; }

/* phones: one column, no wasted space, everything one thumb away */
@media (max-width: 720px) {
  .gradio-container { padding: 8px 10px !important; }
  #toolbar button { padding: 4px 10px !important; min-width: 46px !important; }
  #toolbar button::after { content: none; }
  .brand { font-size: calc(var(--amt-base) * 1.1); } .brand svg { width: 38px; height: 38px; }
  #lang .wrap { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px !important; }
  #lang label { padding: 8px 6px !important; } #lang label span { font-size: calc(var(--amt-base) * .82) !important; white-space: nowrap; }
  .badges li { font-size: calc(var(--amt-base) * .7) !important; padding: 5px 10px; }
  .hero .eyebrow { font-size: calc(var(--amt-base) * .7) !important; }
  #hero-row { margin: 14px 0 0; flex-direction: column; }
  .hero-art { display: none; }
  .hero h1 { font-size: calc(var(--amt-base) * 1.75) !important; }
  .hero .lead { font-size: var(--amt-base) !important; }
  #tool, #result { padding: 16px !important; border-radius: 20px !important; }
  #letter { min-height: 110px; }
  .steps, .feats, .facts ul { grid-template-columns: 1fr; }
  .todo .what { font-size: calc(var(--amt-base) * 1.25) !important; }
}
:focus-visible { outline: 4px solid #ffbf47 !important; outline-offset: 3px !important; }

/* High contrast: yellow on black, thick borders.
   Gradio copies every rule above with an extra ".gradio-container .contain" prefix, which makes them strong.
   :is(.gradio-container, #amt-hc#amt-hc) still matches only .gradio-container, but counts like two ids, so these win. */
body.amt-hc { --amt-ink: #ffeb3b; --amt-muted: #ffeb3b; --amt-surface: #000; --amt-soft: #000; --amt-line: #ffeb3b;
  --amt-blue: #ffeb3b; --amt-shadow: none; }
body.amt-hc, body.amt-hc gradio-app, body.amt-hc .gradio-container,
body.amt-hc :is(.gradio-container, #amt-hc#amt-hc) * {
  background: #000 !important; color: #ffeb3b !important; border-color: #ffeb3b !important; box-shadow: none !important; }
body.amt-hc :is(.gradio-container, #amt-hc#amt-hc) :is(.todo, button, .fact, #tool, #result, .steps li, .feats li, #lang label, #langs) {
  border: 3px solid #ffeb3b !important; }
/* the chosen language and the main buttons are shown inverted: black on yellow */
body.amt-hc :is(.gradio-container, #amt-hc#amt-hc#amt-hc) :is(#lang label.selected, #camera, #listen, .steps .num),
body.amt-hc :is(.gradio-container, #amt-hc#amt-hc#amt-hc) :is(#lang label.selected, #camera, #listen, .steps .num) * {
  background: #ffeb3b !important; color: #000 !important; }
"""

# Phone app (PWA): name, colours and icon for the home screen. Gradio adds manifest.json itself (pwa=True).
HEAD = """
<meta name="theme-color" content="#1f5fd1">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Amt-Lotse">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<link rel="apple-touch-icon" href="pwa_icon/180">
"""

# The big camera button: opens the phone's back camera straight away, using the same upload box,
# so the explanation starts by itself. On a computer the same button just opens the file chooser.
CAMERA_JS = """
() => {
  const input = document.querySelector('#letter input[type=file]');
  if (!input) return;
  const accept = input.getAttribute('accept');
  input.setAttribute('accept', 'image/*');
  input.setAttribute('capture', 'environment');
  input.click();
  setTimeout(() => {          // put the box back to normal: photos, PDFs and text files
    input.removeAttribute('capture');
    if (accept) input.setAttribute('accept', accept); else input.removeAttribute('accept');
  }, 1000);
}
"""
# "Add the next page": the same, into a second, invisible upload box, so the pages already there are kept.
MORE_JS = """
() => {
  const input = document.querySelector('#more input[type=file]');
  if (!input) return;
  const accept = input.getAttribute('accept');
  input.setAttribute('accept', 'image/*');
  input.setAttribute('capture', 'environment');
  input.click();
  setTimeout(() => {          // put the box back to normal: photos, PDFs and text files
    input.removeAttribute('capture');
    if (accept) input.setAttribute('accept', accept); else input.removeAttribute('accept');
  }, 1000);
}
"""

# Texts that live in CSS (the upload box, the toolbar labels) follow the language through CSS variables.
_LANG_DATA = json.dumps({lang: {"drop": TEXT[lang]["drop"], "bigger": UI[lang]["bigger"], "smaller": UI[lang]["smaller"],
                                "contrast": UI[lang]["contrast"]} for lang in UI}, ensure_ascii=False)
APPLY_LANG = """
const amtApply = (lang) => {
  const all = %s, d = all[lang] || all.en, r = document.documentElement;
  r.lang = lang; r.dir = (lang === 'ar' || lang === 'fa') ? 'rtl' : 'ltr';
  for (const k of ['drop', 'bigger', 'smaller', 'contrast']) r.style.setProperty('--amt-' + k, JSON.stringify(d[k]));
  for (const k of ['bigger', 'smaller', 'contrast']) {
    const b = document.getElementById(k); if (b) { b.setAttribute('aria-label', d[k]); b.title = d[k]; }
  }
  document.querySelectorAll('#letter .upload-container').forEach(b => b.setAttribute('aria-label', d.drop));
};
""" % _LANG_DATA

# Runs once when the page loads: remembers text size + contrast, makes status announcements audible.
ON_LOAD_JS = """
() => {""" + APPLY_LANG + """
  amtApply('en');
  const root = document.documentElement;
  const scale = parseFloat(localStorage.getItem('amt_scale') || '1');
  root.style.setProperty('--amt-scale', scale);
  if (localStorage.getItem('amt_hc') === '1') document.body.classList.add('amt-hc');
  const setLive = () => {
    const s = document.querySelector('#status'); if (s) { s.setAttribute('aria-live', 'polite'); s.setAttribute('role', 'status'); }
  };
  setLive(); setTimeout(setLive, 1500);

  // Screen readers: give every control a real name (Gradio leaves some empty or uses internal values).
  const fixNames = () => {
    document.querySelectorAll('#lang input[type=radio]').forEach(r => {
      const label = r.closest('label'); if (label) r.setAttribute('aria-label', label.innerText.trim());
    });
    document.querySelectorAll('button').forEach(b => {
      if (b.getAttribute('aria-label') || b.innerText.trim()) return;
      const text = (b.textContent || b.title || '').trim();
      if (text) b.setAttribute('aria-label', text);
    });
  };
  let pending = null;
  new MutationObserver(() => { clearTimeout(pending); pending = setTimeout(fixNames, 200); })
    .observe(document.body, { childList: true, subtree: true });
  fixNames();
}
"""
BIGGER_JS = "() => { const r=document.documentElement; let s=Math.min(1.8, parseFloat(localStorage.getItem('amt_scale')||'1')+0.15); localStorage.setItem('amt_scale', s); r.style.setProperty('--amt-scale', s); }"
SMALLER_JS = "() => { const r=document.documentElement; let s=Math.max(0.85, parseFloat(localStorage.getItem('amt_scale')||'1')-0.15); localStorage.setItem('amt_scale', s); r.style.setProperty('--amt-scale', s); }"
CONTRAST_JS = "() => { const on=document.body.classList.toggle('amt-hc'); localStorage.setItem('amt_hc', on ? '1' : '0'); }"
LISTEN_AGAIN_JS = """
() => {
  const a = document.querySelector('#audio audio');
  if (a) { a.currentTime = 0; a.play(); return; }
  const b = document.querySelector('#audio button[aria-label*="Play" i], #audio button[title*="Play" i]');
  if (b) b.click();
}
"""
SET_LANG_JS = "(lang) => {" + APPLY_LANG + " amtApply(lang); return lang; }"
FOCUS_RESULT_JS = """
() => { setTimeout(() => { const t = document.querySelector('#todo .todo') || document.querySelector('#status');
  if (t) { t.setAttribute('tabindex', '-1'); t.focus(); t.scrollIntoView({behavior: 'smooth', block: 'center'}); } }, 300); }
"""


def _status(text: str, kind: str = "") -> str:
    """kind: "busy" (spinner), "done", "err" or "" (plain)."""
    css = f' class="{kind}"' if kind else ""
    return f'<p dir="auto"{css}>{text}</p>'


def _copy_input(file_path: str) -> Path:
    # A private temp folder, so the OCR transcription (*.ocr.txt) is written there and not next to Gradio's cache.
    target = Path(tempfile.mkdtemp(prefix="amt_lotse_")) / Path(file_path).name
    shutil.copy(file_path, target)
    return target


# ---------------------------------------------------------------- actions
def new_letter(files, pages):
    """A new letter: the files in the upload box are its pages, in this order.
    The box is emptied afterwards: Gradio's multi-file box adds new uploads to the old ones,
    so a second letter would otherwise get mixed with the pages of the first.
    Without new files ("Explain" pressed again), the current letter is read again."""
    if not files:
        return pages or [], None
    return [str(_copy_input(f)) for f in files], None


def add_pages(files, pages):
    """'Add the next page': keep the pages so far, add the new ones at the end. Empties the extra upload box."""
    return (pages or []) + [str(_copy_input(f)) for f in (files or [])], None


def explain_letter(pages, lang, read_aloud, slow):
    """Generator: every `yield` updates the page, so the status line is announced step by step."""
    t, rtl = UI[lang], lang in RTL_LANGUAGES
    hidden = gr.update(visible=False)
    nothing = gr.update()
    # outputs: status, step3, todo, card, audio, listen_again, calendar, explanation, read_text, state, pages, more_btn
    if not pages:
        yield (_status(t["no_file"], "err"), hidden, "", "", None, hidden, hidden, "", "", None, nothing, hidden)
        return

    count = f" {t['pages_n'].format(n=len(pages))}" if len(pages) > 1 else ""
    yield (_status(f"{t['s_read']}{count} <small>{t['first_time']}</small>", "busy"), hidden, "", "", None, hidden, hidden,
           "", "", None, nothing, hidden)
    try:
        a = analyze([Path(p) for p in pages])
        if a.looks_bad:
            if a.bad_pages and len(pages) > 1:
                # several files, some unreadable: take those out and say which one to photograph again
                keep = [p for i, p in enumerate(pages, 1) if i not in a.bad_pages]
                message = " ".join(t["bad_page"].format(p=n) for n in a.bad_pages)
            else:
                keep, message = [], t["bad"]
            audio = str(speak(message, lang, "bad_photo", slow=slow, play=False)) if read_aloud else None
            bad = f'<div class="todo urgent" role="alert" dir="auto"><div class="what">{message}</div></div>'
            yield (_status(message, "err"), gr.update(visible=True), bad, "", audio, gr.update(visible=bool(audio)), hidden,
                   "", a.text, None, keep, gr.update(visible=bool(keep)))
            return

        todo, card = todo_box(a, lang), facts_html(a, lang, warning=t["cut"] if a.cut else "")
        cal = calendar_file(a, lang)
        yield (_status(t["s_explain"], "busy"), gr.update(visible=True), todo, card, None, hidden,
               gr.update(value=cal, visible=bool(cal)), "", a.text, None, nothing, hidden)

        explanation = explain(a.text, a.info, lang).split("\n\n(⚠")[0]
        shown = f"### 💬 {TEXT[lang]['expl_h']}\n\n{explanation}"
        audio = None
        if read_aloud:
            yield (_status(t["s_audio"], "busy"), gr.update(visible=True), todo, card, None, hidden,
                   gr.update(value=cal, visible=bool(cal)), gr.update(value=shown, rtl=rtl), a.text, None,
                   nothing, hidden)
            facts = SpokenFacts(sender=a.info.sender, deadline=a.deadline, amount=a.amount,
                                receives=a.receives, reference=a.reference, amount_unclear=a.amount_unclear)
            audio = str(speak(build_script(facts, explanation, lang), lang, Path(pages[0]).stem, slow=slow, play=False))

        state = {"text": a.text, "info": a.info.model_dump(), "reference": a.reference}
        yield (_status(t["s_done"] + count, "done"), gr.update(visible=True), todo, card, audio,
               gr.update(visible=bool(audio)), gr.update(value=cal, visible=bool(cal)),
               gr.update(value=shown, rtl=rtl), a.text, state, nothing, gr.update(visible=True))
    except Exception as e:  # e.g. Ollama not running
        yield (_status(_error(e, t), "err"), hidden, "", "", None, hidden, hidden, "", "", None, nothing, hidden)


def write_reply(state, intent, note, lang):
    t = UI[lang]
    if not state:
        yield "", _status(t["no_file"]), None
        return
    yield "", _status(t["s_reply"]), None
    from amt_lotse.extract import LetterInfo

    info = LetterInfo(**state["info"])
    draft = build_reply(state["text"], info, state["reference"], intent, LANGUAGES[lang], note or None)
    out = Path(tempfile.mkdtemp(prefix="amt_lotse_reply_")) / f"Antwort_{intent}.txt"
    out.write_text(draft.german, encoding="utf-8")
    notes = "".join(f"<p>⚠️ {w}</p>" for w in draft.warnings)
    yield draft.german, f"<p><b>{t['s_reply_done']}</b></p><p>{draft.summary}</p>{notes}", str(out)


def funnel_mode() -> bool:
    return os.environ.get("AMT_LOTSE_FUNNEL") == "1"


def cloud_mode() -> bool:
    """The always-online version: the app runs on a server (Hugging Face Space), the AI on the owner's PC."""
    return os.environ.get("AMT_LOTSE_CLOUD") == "1"


def _error(e: Exception, t: dict) -> str:
    """Error text for the user: a model loop gets its own message, it is not an Ollama problem.
    Online version: when the AI computer is off, say exactly that (not a technical error)."""
    if isinstance(e, ModelLoopError):
        return t["stuck"]
    if (cloud_mode() or funnel_mode()) and not ai_online():
        x = TEXT[next(lang for lang, texts in UI.items() if texts is t)]
        return f"{x['ai_off_h']}. {x['ai_off']}"
    return t["error"].format(e=e)


def ai_status(lang):
    """The banner of the online version; empty (hidden) when Amt-Lotse runs on this computer."""
    return ai_status_html(lang, ai_online()) if cloud_mode() or funnel_mode() else ""


def _transcribe(recording, lang):
    from amt_lotse.listen import transcribe

    return transcribe(recording, lang) if recording else ""


def hear_question(recording, lang):
    """Microphone -> text in the question box. The answer then starts by itself."""
    t = UI[lang]
    # On a failure the box is emptied, so the answer step that follows doesn't repeat an old question.
    if not recording:
        return "", "", None
    try:
        text = _transcribe(recording, lang)
    except Exception as e:  # e.g. faster-whisper not installed, unreadable recording
        return "", _status(t["voice_error"].format(e=e)), None
    if not text:
        return "", _status(t["no_speech"]), None
    return text, "", None   # None empties the microphone, ready for the next question


def answer(state, question, lang, read_aloud, slow):
    """Generator: status first, then the answer (shown and read aloud)."""
    t, rtl = UI[lang], lang in RTL_LANGUAGES
    if not state:
        yield _status(t["no_file"]), None
        return
    if not (question or "").strip():
        yield "", None
        return
    yield _status(t["s_answer"]), None
    from amt_lotse.extract import LetterInfo

    try:
        a = answer_question(state["text"], LetterInfo(**state["info"]), question, lang)
    except Exception as e:  # e.g. Ollama not running
        yield _status(_error(e, t)), None
        return
    sound = str(speak(a.text, lang, "answer", slow=slow, play=False)) if read_aloud else None
    css = "answer" if a.from_letter else "answer unknown"
    html = (f'<div class="{css}" dir="{"rtl" if rtl else "auto"}"><p class="q">{t["you_asked"]}: '
            f'{_escape(a.question)}</p><p class="a">{_escape(a.text)}</p></div>')
    yield html, sound


def add_to_note(recording, note, lang):
    """Microphone -> appended to the note for the reply letter (any language; the reply is written in German)."""
    t = UI[lang]
    if not recording:
        return gr.update(), "", None
    try:
        text = _transcribe(recording, lang)
    except Exception as e:
        return gr.update(), _status(t["voice_error"].format(e=e)), None
    if not text:
        return gr.update(), _status(t["no_speech"]), None
    return gr.update(value=f"{note} {text}".strip() if note else text), "", None


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def switch_language(lang):
    """Translate every label on the page."""
    t, x = UI[lang], TEXT[lang]
    rtl = lang in RTL_LANGUAGES
    return (
        hero_html(lang, cloud_mode()), info_html(lang, cloud_mode()), ai_status(lang), f"**{t['step1']}**", f"## {t['step2']}", t["hint2"],
        gr.update(value=t["camera"]), gr.update(label=x["or_file"]), t["examples"],
        *[gr.update(value=label) for label in example_labels(lang)],
        gr.update(value=x["again"]),
        f"## {t['step3']}", gr.update(value="🔊 " + t["listen_again"]), gr.update(label="📅 " + t["calendar"]),
        gr.update(label=t["read"]), gr.update(label=t["reply"]),
        gr.update(label=t["intent"], choices=[(label, key) for key, label in t["intents"].items()]),
        gr.update(label=t["note"], placeholder=t["note_ph"], rtl=rtl),
        gr.update(value=t["reply_btn"]), gr.update(label=t["reply_text"]), gr.update(label=t["download"]),
        gr.update(label="⚙️ " + t["settings"]), gr.update(label=t["read_aloud"]), gr.update(label=t["slow"]),
        f"### 💬 {t['ask_h']}", t["ask_hint"], gr.update(label=t["ask_mic"]),
        gr.update(label=t["ask_text"], placeholder=t["ask_ph"], rtl=rtl), gr.update(value=t["ask_btn"]),
        gr.update(label=t["note_mic"]), gr.update(value=t["more"]),
        t["footer"], lang,
    )


# ---------------------------------------------------------------- layout
def build_ui() -> gr.Blocks:
    t, x = UI["en"], TEXT["en"]
    with gr.Blocks(title="Amt-Lotse", analytics_enabled=False) as ui:
        saved_lang = gr.BrowserState("en", storage_key="amt_lotse_lang")
        state = gr.State()
        pages = gr.State([])

        # ----- top bar: logo, text size, contrast (their labels follow the language through CSS)
        with gr.Row(elem_id="topbar"):
            gr.HTML(brand_html())
            with gr.Row(elem_id="toolbar"):
                bigger = gr.Button("A+", size="sm", scale=0, elem_id="bigger")
                smaller = gr.Button("A−", size="sm", scale=0, elem_id="smaller")
                contrast = gr.Button("🌓", size="sm", scale=0, elem_id="contrast")

        # ----- step 1: the language first, so everything below is already in it
        with gr.Column(elem_id="langs"):
            step1 = gr.Markdown(f"**{t['step1']}**")
            lang = gr.Radio(LANG_CHOICES, value="en", show_label=False, elem_id="lang")

        # ----- landing: what it is, in one look
        with gr.Row(elem_id="hero-row"):
            hero = gr.HTML(hero_html("en", cloud_mode()), scale=6)
            gr.HTML(art_html(), scale=5)

        # ----- step 2: the tool, one main button
        with gr.Column(elem_id="tool"):
            # online version: is the AI computer on? (checked on load, then every 30 seconds)
            ai_banner = gr.HTML(elem_id="ai-status")
            step2 = gr.Markdown(f"## {t['step2']}")
            hint2 = gr.Markdown(t["hint2"])
            camera = gr.Button(t["camera"], variant="primary", size="lg", elem_id="camera")
            file_in = gr.File(label=x["or_file"], file_types=[".jpg", ".jpeg", ".png", ".webp", ".pdf", ".txt"],
                              type="filepath", file_count="multiple", elem_id="letter")
            more = gr.File(file_types=[".jpg", ".jpeg", ".png", ".webp", ".pdf", ".txt"], type="filepath",
                           file_count="multiple", elem_id="more", show_label=False)
            examples_h = gr.Markdown(t["examples"], elem_id="examples-h")
            with gr.Row(elem_id="examples"):
                example_btns = [gr.Button(label, size="md", visible=path.exists(), elem_classes="example")
                                for label, path in zip(example_labels("en"), EXAMPLES, strict=True)]
            status = gr.Markdown(elem_id="status")

        # ----- step 3: the result
        with gr.Column(visible=False, elem_id="result") as result:
            step3 = gr.Markdown(f"## {t['step3']}")
            todo = gr.HTML(elem_id="todo")
            with gr.Row(elem_id="actions"):
                listen_again = gr.Button("🔊 " + t["listen_again"], size="lg", visible=False, elem_id="listen")
                calendar = gr.DownloadButton("📅 " + t["calendar"], size="lg", visible=False)
                more_btn = gr.Button(t["more"], size="lg", visible=False, elem_id="more-btn")
                # the same letter again, e.g. after choosing another language: no new upload needed
                go = gr.Button(x["again"], size="lg", elem_id="go")
            # no "share" button: these are private letters
            audio = gr.Audio(type="filepath", autoplay=True, show_label=False, elem_id="audio", buttons=["download"])
            card = gr.HTML(elem_id="card")
            explanation = gr.Markdown(elem_id="explanation")

            with gr.Column(elem_id="ask-card"):
                ask_h = gr.Markdown(f"### 💬 {t['ask_h']}")
                ask_hint = gr.Markdown(t["ask_hint"])
                ask_mic = gr.Audio(sources=["microphone"], type="filepath", label=t["ask_mic"], elem_id="ask-mic",
                                   buttons=[])  # private: no share or download of the recording
                with gr.Row(equal_height=True):
                    ask_text = gr.Textbox(label=t["ask_text"], placeholder=t["ask_ph"], scale=4)
                    ask_btn = gr.Button(t["ask_btn"], variant="primary", size="lg", scale=1)
                ask_status = gr.Markdown(elem_id="ask-status")
                ask_answer = gr.HTML(elem_id="answer")
                ask_audio = gr.Audio(type="filepath", autoplay=True, show_label=False, elem_id="answer-audio",
                                     buttons=["download"])
            with gr.Accordion(t["read"], open=False) as read_box:
                read_text = gr.Textbox(lines=12, show_label=False, buttons=["copy"])
            with gr.Accordion(t["reply"], open=False) as reply_box:
                intent = gr.Dropdown([(label, key) for key, label in t["intents"].items()], value="question",
                                     label=t["intent"])
                note = gr.Textbox(label=t["note"], placeholder=t["note_ph"])
                note_mic = gr.Audio(sources=["microphone"], type="filepath", label=t["note_mic"], elem_id="note-mic",
                                    buttons=[])
                note_status = gr.Markdown()
                reply_btn = gr.Button(t["reply_btn"], size="lg")
                reply_status = gr.Markdown()
                reply_text = gr.Textbox(label=t["reply_text"], lines=16, buttons=["copy"])
                reply_file = gr.File(label=t["download"])

        # ----- landing: how it works, why it can be trusted
        info = gr.HTML(info_html("en", cloud_mode()))

        with gr.Accordion("⚙️ " + t["settings"], open=False) as settings_box:
            read_aloud = gr.Checkbox(value=True, label=t["read_aloud"])
            slow = gr.Checkbox(value=True, label=t["slow"])

        footer = gr.Markdown(t["footer"], elem_id="footer")

        # ----- events
        translated = [hero, info, ai_banner, step1, step2, hint2, camera, file_in, examples_h, *example_btns, go,
                      step3, listen_again, calendar, read_box, reply_box, intent, note, reply_btn, reply_text,
                      reply_file, settings_box, read_aloud, slow,
                      ask_h, ask_hint, ask_mic, ask_text, ask_btn, note_mic, more_btn, footer, saved_lang]
        explain_outputs = [status, result, todo, card, audio, listen_again, calendar, explanation, read_text, state,
                           pages, more_btn]

        ui.load(None, js=ON_LOAD_JS)
        ui.load(lambda saved: saved or "en", inputs=saved_lang, outputs=lang)
        lang.change(switch_language, inputs=lang, outputs=translated, js=SET_LANG_JS)
        if cloud_mode() or funnel_mode():
            ui.load(ai_status, lang, ai_banner, show_progress="hidden")
            gr.Timer(30).tick(ai_status, lang, ai_banner, show_progress="hidden")

        run = dict(fn=explain_letter, inputs=[pages, lang, read_aloud, slow], outputs=explain_outputs,
                   show_progress="hidden")
        # upload = a new letter, start automatically
        file_in.upload(new_letter, [file_in, pages], [pages, file_in], show_progress="hidden") \
            .then(**run).then(None, js=FOCUS_RESULT_JS)
        # "Explain again": the same pages, e.g. in the language chosen afterwards
        go.click(new_letter, [file_in, pages], [pages, file_in], show_progress="hidden") \
            .then(**run).then(None, js=FOCUS_RESULT_JS)
        # an example letter: one tap, and it is explained
        for button, path in zip(example_btns, EXAMPLES, strict=True):
            button.click(lambda p=str(path): [p], None, pages, show_progress="hidden") \
                .then(**run).then(None, js=FOCUS_RESULT_JS)
        # "Add the next page": one more photo, then the whole letter is read again
        more_btn.click(None, js=MORE_JS)
        more.upload(add_pages, [more, pages], [pages, more], show_progress="hidden") \
            .then(**run).then(None, js=FOCUS_RESULT_JS)

        reply_btn.click(write_reply, [state, intent, note, lang], [reply_text, reply_status, reply_file],
                        show_progress="hidden")
        ask = dict(fn=answer, inputs=[state, ask_text, lang, read_aloud, slow], outputs=[ask_answer, ask_audio],
                   show_progress="hidden")
        # speak -> the words appear in the box (so the person can check them) -> the answer starts by itself
        ask_mic.stop_recording(hear_question, [ask_mic, lang], [ask_text, ask_status, ask_mic], show_progress="hidden") \
            .success(**ask)
        ask_btn.click(**ask)
        ask_text.submit(**ask)
        note_mic.stop_recording(add_to_note, [note_mic, note, lang], [note, note_status, note_mic], show_progress="hidden")
        camera.click(None, js=CAMERA_JS)
        listen_again.click(None, js=LISTEN_AGAIN_JS)
        bigger.click(None, js=BIGGER_JS)
        smaller.click(None, js=SMALLER_JS)
        contrast.click(None, js=CONTRAST_JS)
    return ui


# ---------------------------------------------------------------- start
def lan_ip() -> str:
    """The computer's address in the home network, e.g. 192.168.178.23 (no data is sent)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]


def print_qr(url: str) -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Windows terminals need this for the QR blocks
    except (AttributeError, ValueError):
        pass
    try:
        import io

        import qrcode

        qr = qrcode.QRCode(border=2)
        qr.add_data(url)
        qr.make()
        out = io.StringIO()
        qr.print_ascii(out=out, invert=True)
        print(out.getvalue())
    except Exception:  # no QR in this terminal: the address is printed as text too
        pass


CLOUD_NOTE = """
  Amt-Lotse online version
  • This server shows the app (and runs speech-to-text and read-aloud). The AI runs on your PC: {host}
  • AI right now: {online}. When the PC is off, the page still works and says that the AI server is off.
  • Letters pass through this server (encrypted) on their way to your PC; they are not stored here.
"""
FUNNEL_NOTE = """
  Amt-Lotse online (Tailscale Funnel)
  • Website and phone app:  {url}
  • Status page (always online, says when this PC is off):  {status_page}
  • User: amt, password: the one in AMT_LOTSE_PASSWORD. Without it nobody can use the app.
  • Letters travel encrypted straight to THIS computer; Tailscale's relays can't read them, nothing is stored online.
  • Stop: Ctrl + C (the address then shows nothing; the status page says the AI server is off).
"""

STATUS_PAGE = "https://achref-2.github.io/amt-lotse/"
STATUS_ORIGINS = ("https://achref-2.github.io",)


def add_status_route(ui: gr.Blocks) -> None:
    """/amt-status: the only page without a password. It says just whether the AI is ready, so the status
    page on GitHub can show "AI server is off" or the "Open" button. No letter data, nothing else."""
    from fastapi import Request
    from fastapi.responses import JSONResponse

    def status(request: Request) -> JSONResponse:
        origin = request.headers.get("origin", "")
        headers = {"Cache-Control": "no-store", "Vary": "Origin"}
        if origin in STATUS_ORIGINS:
            headers["Access-Control-Allow-Origin"] = origin
        return JSONResponse({"app": True, "ai": ai_online()}, headers=headers)

    ui.app.add_api_route("/amt-status", status, methods=["GET"])
    ui.app.router.routes.insert(0, ui.app.router.routes.pop())   # before Gradio's own routes


def start_funnel(port: int) -> tuple[bool, str]:
    """Turns on Tailscale Funnel for this port (stays on after a restart; running it again changes nothing)."""
    try:
        done = subprocess.run(["tailscale", "funnel", "--bg", str(port)], capture_output=True, text=True, timeout=30)
        return done.returncode == 0, (done.stdout + done.stderr).strip()
    except FileNotFoundError:
        return False, "Tailscale was not found. Install it from https://tailscale.com/download and sign in."
    except subprocess.TimeoutExpired as e:
        # the first time, Tailscale may wait until Funnel is allowed for the tailnet (it prints a link for that)
        return False, ((e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or "")).strip()


SHARE_WARNING = """
  ⚠  PUBLIC LINK – please read
  • Anyone who has the link AND the password can use Amt-Lotse on this computer.
  • Letters (photos, texts) then travel through Gradio's share servers (gradio.live) to this computer.
    They are not stored there, but they leave this computer. Use only made-up test letters,
    never real ones, while the public link is on.
  • The link works until you stop the app (Ctrl + C), at most about 1 week.
"""


def print_phone_link(url: str, password: str) -> None:
    """The address as text and as a QR code: point the phone camera at the screen, no typing."""
    print("\n" + "=" * 60)
    print("  On your phone, scan this code with the camera, or type the address:")
    print(f"     {url}")
    print_qr(url)
    print("  User:      amt")
    print(f"  Password:  {password}")
    print("\n  Install it as an app: browser menu > 'Add to Home screen' / 'Install app'.")
    print("  Only use this in a network you trust (your home Wi-Fi), not in public Wi-Fi.")
    print("=" * 60 + "\n")


def tailscale_url(port: int) -> str | None:
    """https://<this-computer>.<your-tailnet>.ts.net if Tailscale is installed and 'tailscale serve' is set up."""
    try:
        status = json.loads(subprocess.run(["tailscale", "status", "--json"], capture_output=True, text=True,
                                           timeout=5).stdout)
        name = status["Self"]["DNSName"].rstrip(".")
        return f"https://{name}" if name else None
    except Exception:
        return None


def main() -> None:
    parser = argparse.ArgumentParser(prog="amt-lotse-ui")
    parser.add_argument("--lan", action="store_true",
                        help="also allow phones on the same Wi-Fi (asks for a password)")
    parser.add_argument("--tailscale", action="store_true",
                        help="phone app over Tailscale: HTTPS, installable, also away from home (asks for a password)")
    parser.add_argument("--cert", help="HTTPS certificate for --lan (e.g. made with mkcert), so the phone can install the app")
    parser.add_argument("--key", help="private key that belongs to --cert")
    parser.add_argument("--cloud", action="store_true",
                        help="always-online version (Hugging Face Space): this server shows the app, the AI runs on "
                             "your PC (OLLAMA_HOST, reached through Tailscale); needs AMT_LOTSE_PASSWORD")
    parser.add_argument("--funnel", action="store_true",
                        help="always online from anywhere (website + phone app, Wi-Fi or 4G): public HTTPS address "
                             "via Tailscale Funnel, AI on this PC; needs AMT_LOTSE_PASSWORD (10+ characters)")
    parser.add_argument("--share", action="store_true",
                        help="temporary public link via gradio.live, e.g. for a demo (asks for a password; "
                             "letters then pass through Gradio's servers)")
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--host", default="127.0.0.1",
                        help="network interface; Docker uses 0.0.0.0 (the port is still published only to this computer)")
    args = parser.parse_args()
    if bool(args.cert) != bool(args.key):
        parser.error("--cert and --key belong together")

    theme = gr.themes.Soft(text_size=gr.themes.sizes.text_lg, primary_hue="blue")
    # pwa=True: Gradio serves manifest.json, so phones can add Amt-Lotse to the home screen like an app
    common = dict(server_port=args.port, css=CSS, theme=theme, head=HEAD, favicon_path=str(ICON), pwa=True,
                  footer_links=[])  # no "Use via API" / "Built with Gradio": fewer distractions

    if args.share and (args.lan or args.tailscale):
        parser.error("--share is its own mode; use it without --lan/--tailscale")

    if args.cloud:
        # Online version: anyone can open the page, so the password is required and must be a real one.
        # The letters pass through this server on their way to the AI on your PC (see CLOUD_NOTE).
        if args.share or args.lan or args.tailscale:
            parser.error("--cloud is its own mode; use it without --share/--lan/--tailscale")
        password = os.environ.get("AMT_LOTSE_PASSWORD", "")
        if len(password) < 10:
            parser.error("--cloud needs a password of at least 10 characters in AMT_LOTSE_PASSWORD (a Space secret)")
        os.environ["AMT_LOTSE_CLOUD"] = "1"
        print(CLOUD_NOTE.format(host=os.environ.get("OLLAMA_HOST", "127.0.0.1:11434"),
                                online="reachable" if ai_online() else "NOT reachable (PC off?)"))
        build_ui().launch(server_name="0.0.0.0", auth=("amt", password),
                          auth_message="Amt-Lotse – please enter your password.", **common)
        return

    if args.funnel:
        # Public address: anyone can reach the login page, so a real password is required.
        # Amt-Lotse stays on 127.0.0.1; Tailscale passes the encrypted traffic on to it.
        if args.share or args.lan or args.tailscale or args.cloud:
            parser.error("--funnel is its own mode; use it without --share/--lan/--tailscale/--cloud")
        password = os.environ.get("AMT_LOTSE_PASSWORD", "")
        if len(password) < 10:
            parser.error("--funnel needs a password of at least 10 characters in AMT_LOTSE_PASSWORD "
                         "(once: setx AMT_LOTSE_PASSWORD \"your-password\", then open a new terminal)")
        os.environ["AMT_LOTSE_FUNNEL"] = "1"
        ok, output = start_funnel(args.port)
        if not ok:
            print("\n  Tailscale Funnel is not on yet:\n  " + (output or "no answer from Tailscale"))
            print(f"  Follow the link above if there is one, or run:  tailscale funnel --bg {args.port}\n")
        url = tailscale_url(args.port) or "https://<this-computer>.<your-tailnet>.ts.net"
        print(FUNNEL_NOTE.format(url=url, status_page=STATUS_PAGE))
        print_qr(url)
        ui = build_ui()
        ui.launch(server_name="127.0.0.1", auth=("amt", password), prevent_thread_lock=True, inbrowser=False,
                  auth_message="Amt-Lotse – please enter your password.", **common)
        add_status_route(ui)
        ui.block_thread()
        return

    if not (args.lan or args.tailscale or args.share):
        # 127.0.0.1 = only this computer can open it. Letters never leave the machine.
        build_ui().launch(server_name=args.host, inbrowser=args.host == "127.0.0.1", **common)
        return

    # Phone modes are reachable from other devices, so a password is always required.
    # Letters still never go to a cloud service: the phone sends the photo to THIS computer only.
    password = os.environ.get("AMT_LOTSE_PASSWORD") or secrets.token_urlsafe(6)
    auth = dict(auth=("amt", password), auth_message="Amt-Lotse – please enter the password shown on the computer.",
                inbrowser=False)

    if args.share:
        # Public link: Gradio opens a tunnel from its share server to this computer. Amt-Lotse itself stays
        # on 127.0.0.1; the password is what keeps strangers out, so it is never optional here.
        print(SHARE_WARNING)
        print("  Creating the public link (the first time Gradio downloads a small helper program) ...\n")
        ui = build_ui()
        _app, _local, share_url = ui.launch(server_name="127.0.0.1", share=True, prevent_thread_lock=True,
                                             **auth, **common)
        if not share_url:
            print("  The public link could not be created (no internet, or a firewall / antivirus blocks Gradio's")
            print("  helper program). Amt-Lotse still runs on this computer: http://127.0.0.1:" + str(args.port))
        else:
            print("=" * 60)
            print(f"  Public link:  {share_url}")
            print_qr(share_url)
            print("  User:      amt")
            print(f"  Password:  {password}")
            print("  Stop the public link: Ctrl + C")
            print("=" * 60 + "\n")
        ui.block_thread()      # keeps running; Ctrl + C closes the app and the public link
        return

    if args.tailscale:
        # Tailscale gives this computer a private HTTPS address that only your own devices can open,
        # at home and on the way. Amt-Lotse itself stays on 127.0.0.1; 'tailscale serve' passes the traffic on.
        url = tailscale_url(args.port)
        print(f"\n  First time only, run this once in another terminal:   tailscale serve --bg {args.port}")
        if not url:
            print("  Tailscale was not found. Install it from https://tailscale.com/download on this computer")
            print("  and on the phone, sign in with the same account, then start again.")
            url = "https://<this-computer>.<your-tailnet>.ts.net"
        print_phone_link(url, password)
        build_ui().launch(server_name="127.0.0.1", **auth, **common)
        return

    scheme = "https" if args.cert else "http"
    url = f"{scheme}://{lan_ip()}:{args.port}"
    print_phone_link(url, password)
    if not args.cert:
        print("  Note: without HTTPS the phone opens Amt-Lotse in the browser; it can't be installed as a full app.")
        print("  For the full app use --tailscale, or --cert/--key (README, 'Phone app').\n")
    # ssl_verify=False only affects Gradio's start-up check of its own address: a certificate made for the
    # Wi-Fi address (mkcert) doesn't match "localhost". The phone still checks the certificate normally.
    ssl = dict(ssl_certfile=args.cert, ssl_keyfile=args.key, ssl_verify=False) if args.cert else {}
    build_ui().launch(server_name="0.0.0.0", **auth, **ssl, **common)


if __name__ == "__main__":
    main()
