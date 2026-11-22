"""Amt-Lotse web UI, designed for blind people, older people and new immigrants.

Start:
    uv run amt-lotse-ui          # only this computer: http://127.0.0.1:7860
    uv run amt-lotse-ui --lan    # also your phone on the same Wi-Fi (password protected)
    uv run amt-lotse-ui --tailscale   # phone app with HTTPS, also away from home (see README)

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
from amt_lotse.cli import LANGUAGES, explain
from amt_lotse.extract import ModelLoopError
from amt_lotse.pipeline import analyze, calendar_file, summary_card, todo_box
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
LANG_CHOICES = [("English", "en"), ("Français", "fr"), ("العربية", "ar"), ("Deutsch (einfach)", "de")]

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
}

# ---------------------------------------------------------------- look & feel
CSS = """
:root { --amt-scale: 1; }
.gradio-container { --amt-base: calc(20px * var(--amt-scale)); max-width: 920px !important; margin: auto; }
/* Gradio sets its own px sizes on inner elements, so every text element gets the base size directly. */
.gradio-container p, .gradio-container li, .gradio-container label, .gradio-container label span,
.gradio-container input, .gradio-container textarea, .gradio-container button, .gradio-container .prose {
  font-size: var(--amt-base) !important; line-height: 1.6 !important; }
.gradio-container h1 { font-size: calc(var(--amt-base) * 2) !important; }
.gradio-container h2 { font-size: calc(var(--amt-base) * 1.4) !important; margin-top: 1.2em !important; }
.gradio-container button { min-height: 56px; }
#go, #go button { font-size: calc(var(--amt-base) * 1.3) !important; min-height: 76px !important; }
#more { display: none !important; }      /* only opened by the "Add the next page" button */
#camera { font-size: calc(var(--amt-base) * 1.2) !important; min-height: 72px !important; }
/* phones: no wasted space at the sides, everything one thumb away */
@media (max-width: 600px) {
  .gradio-container { padding: 8px !important; }
  #toolbar { flex-direction: row !important; flex-wrap: nowrap !important; gap: 6px !important; }
  #toolbar > *, #toolbar button { min-width: 0 !important; flex: 1 1 0 !important; }
  #toolbar button { padding: 4px 6px !important; font-size: calc(var(--amt-base) * 0.72) !important; white-space: normal; }
  .gradio-container h1 { font-size: calc(var(--amt-base) * 1.6) !important; margin-top: 4px !important; }
}
#lang label { padding: 12px 18px !important; }
#lang input[type=radio] { width: 22px !important; height: 22px !important; }
.gr-accordion { overflow: visible !important; }
:focus-visible { outline: 4px solid #ffbf47 !important; outline-offset: 3px !important; }

/* Colours forced on every child: the dark theme otherwise paints light text on the light box (contrast 1:1). */
.todo { border-radius: 14px; padding: 18px 22px; margin: 6px 0 4px; background: #e8f1ff !important; border: 3px solid #2f6fdb; }
.todo, .todo * { color: #08245c !important; }            /* contrast 13:1 */
.todo.urgent { background: #ffecec !important; border-color: #c40000; }
.todo.urgent, .todo.urgent * { color: #6b0000 !important; }  /* contrast 11:1 */
.todo .when { font-weight: 800; font-size: calc(var(--amt-base) * 1.1) !important; margin-bottom: 4px; }
.todo .what { font-size: calc(var(--amt-base) * 1.35) !important; line-height: 1.5; }
#card { font-size: 1.1em; }
.answer { border-radius: 14px; padding: 16px 20px; background: #eef7f0 !important; border: 3px solid #12a150; }
.answer, .answer * { color: #0b3d1f !important; }            /* contrast 12:1 */
.answer.unknown { background: #fff6e0 !important; border-color: #b86e00; }
.answer.unknown, .answer.unknown * { color: #4a2c00 !important; }
.answer .q { font-style: italic; margin: 0 0 6px !important; }
.answer .a { font-size: calc(var(--amt-base) * 1.2) !important; margin: 0 !important; }
#ask-mic, #note-mic { min-height: 0; }
#card .ref { font-family: ui-monospace, Consolas, monospace; font-size: 1.15em; letter-spacing: 0.08em; }
#status { font-weight: 700; min-height: 1.6em; }
#toolbar { justify-content: flex-end; gap: 8px; }
#toolbar button { min-height: 44px; font-size: calc(var(--amt-base) * 0.85) !important; }

/* High contrast: yellow on black, thick borders */
body.amt-hc, body.amt-hc .gradio-container, body.amt-hc .gradio-container * {
  background: #000 !important; color: #ffeb3b !important; border-color: #ffeb3b !important; }
body.amt-hc .todo, body.amt-hc button { border: 3px solid #ffeb3b !important; }
/* the chosen option and the main button are shown inverted: black on yellow */
html body.amt-hc #lang label.selected, html body.amt-hc #go { background-color: #ffeb3b !important; color: #000 !important; }
html body.amt-hc #lang label.selected *, html body.amt-hc #go * { background-color: transparent !important; color: #000 !important; }
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

# Runs once when the page loads: remembers text size + contrast, makes status announcements audible.
ON_LOAD_JS = """
() => {
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
SET_LANG_JS = """
(lang) => {
  document.documentElement.lang = lang;
  document.documentElement.dir = (lang === 'ar') ? 'rtl' : 'ltr';
  return lang;
}
"""
FOCUS_RESULT_JS = """
() => { setTimeout(() => { const t = document.querySelector('#todo .todo') || document.querySelector('#status');
  if (t) { t.setAttribute('tabindex', '-1'); t.focus(); t.scrollIntoView({behavior: 'smooth', block: 'center'}); } }, 300); }
"""


def _status(text: str) -> str:
    return f'<p dir="auto">{text}</p>'


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
    t, rtl = UI[lang], lang == "ar"
    hidden = gr.update(visible=False)
    nothing = gr.update()
    # outputs: status, step3, todo, card, audio, listen_again, calendar, explanation, read_text, state, pages, more_btn
    if not pages:
        yield (_status(t["no_file"]), hidden, "", "", None, hidden, hidden, "", "", None, nothing, hidden)
        return

    count = f" {t['pages_n'].format(n=len(pages))}" if len(pages) > 1 else ""
    yield (_status(f"{t['s_read']}{count} <small>{t['first_time']}</small>"), hidden, "", "", None, hidden, hidden,
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
            yield (_status(message), gr.update(visible=True), bad, "", audio, gr.update(visible=bool(audio)), hidden,
                   "", a.text, None, keep, gr.update(visible=bool(keep)))
            return

        todo, card = todo_box(a, lang), summary_card(a, lang)
        if a.cut:
            card = f"⚠️ {t['cut']}\n\n{card}"
        cal = calendar_file(a, lang)
        yield (_status(t["s_explain"]), gr.update(visible=True), todo, gr.update(value=card, rtl=rtl), None, hidden,
               gr.update(value=cal, visible=bool(cal)), "", a.text, None, nothing, hidden)

        explanation = explain(a.text, a.info, lang).split("\n\n(⚠")[0]
        audio = None
        if read_aloud:
            yield (_status(t["s_audio"]), gr.update(visible=True), todo, gr.update(value=card, rtl=rtl), None, hidden,
                   gr.update(value=cal, visible=bool(cal)), gr.update(value=explanation, rtl=rtl), a.text, None,
                   nothing, hidden)
            facts = SpokenFacts(sender=a.info.sender, deadline=a.deadline, amount=a.amount,
                                receives=a.receives, reference=a.reference, amount_unclear=a.amount_unclear)
            audio = str(speak(build_script(facts, explanation, lang), lang, Path(pages[0]).stem, slow=slow, play=False))

        state = {"text": a.text, "info": a.info.model_dump(), "reference": a.reference}
        yield (_status(t["s_done"] + count), gr.update(visible=True), todo, gr.update(value=card, rtl=rtl), audio,
               gr.update(visible=bool(audio)), gr.update(value=cal, visible=bool(cal)),
               gr.update(value=explanation, rtl=rtl), a.text, state, nothing, gr.update(visible=True))
    except Exception as e:  # e.g. Ollama not running
        yield (_status(_error(e, t)), hidden, "", "", None, hidden, hidden, "", "", None, nothing, hidden)


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


def _error(e: Exception, t: dict) -> str:
    """Error text for the user: a model loop gets its own message, it is not an Ollama problem."""
    return t["stuck"] if isinstance(e, ModelLoopError) else t["error"].format(e=e)


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
    t, rtl = UI[lang], lang == "ar"
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
    t = UI[lang]
    rtl = lang == "ar"
    return (
        f"# {t['title']}\n{t['subtitle']}",
        f"## {t['step1']}", f"## {t['step2']}", t["hint2"],
        gr.update(value=t["camera"]), gr.update(label=t["file"]), gr.update(label=t["examples"]), gr.update(value=t["go"]),
        f"## {t['step3']}", gr.update(value=t["listen_again"]), gr.update(label=t["calendar"]),
        gr.update(label=t["read"]), gr.update(label=t["reply"]),
        gr.update(label=t["intent"], choices=[(label, key) for key, label in t["intents"].items()]),
        gr.update(label=t["note"], placeholder=t["note_ph"], rtl=rtl),
        gr.update(value=t["reply_btn"]), gr.update(label=t["reply_text"]), gr.update(label=t["download"]),
        gr.update(label=t["settings"]), gr.update(label=t["read_aloud"]), gr.update(label=t["slow"]),
        gr.update(value="A+ " + t["bigger"]), gr.update(value="A− " + t["smaller"]), gr.update(value="◐ " + t["contrast"]),
        f"### {t['ask_h']}", t["ask_hint"], gr.update(label=t["ask_mic"]),
        gr.update(label=t["ask_text"], placeholder=t["ask_ph"], rtl=rtl), gr.update(value=t["ask_btn"]),
        gr.update(label=t["note_mic"]), gr.update(value=t["more"]),
        t["footer"], lang,
    )


# ---------------------------------------------------------------- layout
def build_ui() -> gr.Blocks:
    t = UI["en"]
    with gr.Blocks(title="Amt-Lotse", analytics_enabled=False) as ui:
        saved_lang = gr.BrowserState("en", storage_key="amt_lotse_lang")
        state = gr.State()

        with gr.Row(elem_id="toolbar"):
            bigger = gr.Button("A+ " + t["bigger"], size="sm", scale=0)
            smaller = gr.Button("A− " + t["smaller"], size="sm", scale=0)
            contrast = gr.Button("◐ " + t["contrast"], size="sm", scale=0)

        header = gr.Markdown(f"# {t['title']}\n{t['subtitle']}")

        step1 = gr.Markdown(f"## {t['step1']}")
        lang = gr.Radio(LANG_CHOICES, value="en", show_label=False, elem_id="lang")

        step2 = gr.Markdown(f"## {t['step2']}")
        hint2 = gr.Markdown(t["hint2"])
        camera = gr.Button(t["camera"], variant="primary", size="lg", elem_id="camera")
        file_in = gr.File(label=t["file"], file_types=[".jpg", ".jpeg", ".png", ".webp", ".pdf", ".txt"],
                          type="filepath", file_count="multiple", elem_id="letter")
        more = gr.File(file_types=[".jpg", ".jpeg", ".png", ".webp", ".pdf", ".txt"], type="filepath",
                       file_count="multiple", elem_id="more", show_label=False)
        pages = gr.State([])
        with gr.Accordion(t["examples"], open=False) as examples_box:
            gr.Examples([[[str(p)]] for p in EXAMPLES if p.exists()], inputs=[file_in], label="")
        go = gr.Button(t["go"], variant="primary", size="lg", elem_id="go")
        status = gr.Markdown(elem_id="status")

        with gr.Column(visible=False) as result:
            step3 = gr.Markdown(f"## {t['step3']}")
            todo = gr.HTML(elem_id="todo")
            more_btn = gr.Button(t["more"], size="lg", visible=False, elem_id="more-btn")
            with gr.Row():
                listen_again = gr.Button(t["listen_again"], size="lg", visible=False, elem_id="listen")
                calendar = gr.DownloadButton(t["calendar"], size="lg", visible=False)
            # no "share" button: these are private letters
            audio = gr.Audio(type="filepath", autoplay=True, show_label=False, elem_id="audio", buttons=["download"])
            card = gr.Markdown(elem_id="card")
            explanation = gr.Markdown(elem_id="explanation")

            ask_h = gr.Markdown(f"### {t['ask_h']}")
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

        with gr.Accordion(t["settings"], open=False) as settings_box:
            read_aloud = gr.Checkbox(value=True, label=t["read_aloud"])
            slow = gr.Checkbox(value=True, label=t["slow"])

        footer = gr.Markdown(t["footer"])

        # ----- events
        translated = [header, step1, step2, hint2, camera, file_in, examples_box, go, step3, listen_again, calendar,
                      read_box, reply_box, intent, note, reply_btn, reply_text, reply_file, settings_box,
                      read_aloud, slow, bigger, smaller, contrast,
                      ask_h, ask_hint, ask_mic, ask_text, ask_btn, note_mic, more_btn, footer, saved_lang]
        explain_outputs = [status, result, todo, card, audio, listen_again, calendar, explanation, read_text, state,
                           pages, more_btn]

        ui.load(None, js=ON_LOAD_JS)
        ui.load(lambda saved: saved or "en", inputs=saved_lang, outputs=lang)
        lang.change(switch_language, inputs=lang, outputs=translated, js=SET_LANG_JS)

        run = dict(fn=explain_letter, inputs=[pages, lang, read_aloud, slow], outputs=explain_outputs,
                   show_progress="hidden")
        # upload = a new letter, start automatically
        file_in.upload(new_letter, [file_in, pages], [pages, file_in], show_progress="hidden") \
            .then(**run).then(None, js=FOCUS_RESULT_JS)
        go.click(new_letter, [file_in, pages], [pages, file_in], show_progress="hidden") \
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


def print_phone_link(url: str, password: str) -> None:
    """The address as text and as a QR code: point the phone camera at the screen, no typing."""
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Windows terminals need this for the QR blocks
    except (AttributeError, ValueError):
        pass
    print("\n" + "=" * 60)
    print("  On your phone, scan this code with the camera, or type the address:")
    print(f"     {url}")
    try:
        import io

        import qrcode

        qr = qrcode.QRCode(border=2)
        qr.add_data(url)
        qr.make()
        out = io.StringIO()
        qr.print_ascii(out=out, invert=True)
        print(out.getvalue())
    except Exception:  # no QR in this terminal: the address above is enough
        pass
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

    if not (args.lan or args.tailscale):
        # 127.0.0.1 = only this computer can open it. Letters never leave the machine.
        build_ui().launch(server_name=args.host, inbrowser=args.host == "127.0.0.1", **common)
        return

    # Phone modes are reachable from other devices, so a password is always required.
    # Letters still never go to a cloud service: the phone sends the photo to THIS computer only.
    password = os.environ.get("AMT_LOTSE_PASSWORD") or secrets.token_urlsafe(6)
    auth = dict(auth=("amt", password), auth_message="Amt-Lotse – please enter the password shown on the computer.",
                inbrowser=False)

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
