"""Amt-Lotse web UI (Gradio). Runs only on this computer: http://127.0.0.1:7860

Start:  uv run amt-lotse-ui
"""

import shutil
import tempfile
from pathlib import Path

import gradio as gr

from amt_lotse.cli import LANGUAGES, explain
from amt_lotse.pipeline import analyze, summary_card
from amt_lotse.reply import INTENTS, build_reply
from amt_lotse.speak import TEXT, SpokenFacts, build_script, speak

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = [  # fictional test letters, safe to show
    PROJECT_ROOT / "data" / "photos" / "jobcenter_01_photo.jpg",
    PROJECT_ROOT / "data" / "photos" / "mahnung_01_scan.png",
    PROJECT_ROOT / "data" / "photos" / "finanzamt_02_digital.pdf",
    PROJECT_ROOT / "data" / "eval" / "krankenkasse_02.txt",
]

LANG_CHOICES = [("English", "en"), ("Français", "fr"), ("العربية", "ar"), ("Deutsch (einfach)", "de")]
REPLY_CHOICES = [(v["label"], k) for k, v in INTENTS.items()]

UI_TEXT = {
    "en": {"working": "Reading the letter … this can take up to a minute.", "bad": "⚠️ The letter could not be read well. Please take the photo again: good light, the whole page, phone held straight above it.",
           "no_file": "Please upload a photo, PDF or text file first.", "error": "Something went wrong: {e}. Is Ollama running?"},
    "fr": {"working": "Lecture de la lettre … cela peut prendre une minute.", "bad": "⚠️ La lettre n'a pas pu être bien lue. Reprenez la photo : bonne lumière, page entière, téléphone bien au-dessus.",
           "no_file": "Veuillez d'abord ajouter une photo, un PDF ou un fichier texte.", "error": "Une erreur est survenue : {e}. Ollama est-il lancé ?"},
    "ar": {"working": "جار قراءة الرسالة … قد يستغرق ذلك دقيقة.", "bad": "⚠️ لم تتم قراءة الرسالة جيدا. من فضلك التقط الصورة مرة أخرى: إضاءة جيدة، الصفحة كاملة، والهاتف مستقيم فوقها.",
           "no_file": "من فضلك أضف صورة أو ملف PDF أو ملفا نصيا أولا.", "error": "حدث خطأ: {e}. هل برنامج Ollama يعمل؟"},
    "de": {"working": "Der Brief wird gelesen … das kann eine Minute dauern.", "bad": "⚠️ Der Brief war nicht gut lesbar. Bitte machen Sie das Foto noch einmal: gutes Licht, ganze Seite, Handy gerade darüber.",
           "no_file": "Bitte laden Sie zuerst ein Foto, PDF oder eine Textdatei hoch.", "error": "Es gab einen Fehler: {e}. Läuft Ollama?"},
}

STEPS = {
    "en": ["📷 Reading the letter …", "🔍 Finding deadline and amount …", "✍️ Writing the explanation …", "🔊 Creating audio …", "✉️ Writing the reply …"],
    "fr": ["📷 Lecture de la lettre …", "🔍 Recherche de la date limite et du montant …", "✍️ Rédaction de l'explication …", "🔊 Création de l'audio …", "✉️ Rédaction de la réponse …"],
    "ar": ["📷 جار قراءة الرسالة …", "🔍 جار البحث عن الموعد والمبلغ …", "✍️ جار كتابة الشرح …", "🔊 جار إنشاء الصوت …", "✉️ جار كتابة الرد …"],
    "de": ["📷 Der Brief wird gelesen …", "🔍 Frist und Betrag werden gesucht …", "✍️ Die Erklärung wird geschrieben …", "🔊 Die Audiodatei wird erstellt …", "✉️ Die Antwort wird geschrieben …"],
}

CSS = """
.big-button button, button.big-button { font-size: 1.4rem !important; min-height: 64px; }
.card { font-size: 1.25rem; line-height: 1.6; }
.card code { font-size: 1.2rem; }
.explanation { font-size: 1.15rem; line-height: 1.7; }
"""


def _input_path(file_path: str | None, photo_path: str | None) -> Path | None:
    chosen = photo_path or file_path
    if not chosen:
        return None
    # Copy into a temp folder so the OCR transcription (*.ocr.txt) is written there, not next to Gradio's cache.
    tmp = Path(tempfile.mkdtemp(prefix="amt_lotse_"))
    target = tmp / Path(chosen).name
    shutil.copy(chosen, target)
    return target


def explain_letter(file_path, photo_path, lang, read_aloud, slow, progress=gr.Progress()):
    t = UI_TEXT[lang]
    steps = STEPS[lang]
    rtl = lang == "ar"
    path = _input_path(file_path, photo_path)
    if path is None:
        raise gr.Error(t["no_file"])

    try:
        progress(0.05, desc=steps[0])
        a = analyze(path, on_step=lambda: progress(0.4, desc=steps[1]))
        if a.looks_bad:
            audio = speak(TEXT[lang]["bad_photo"], lang, "bad_photo", slow=slow, play=False) if read_aloud else None
            return (gr.update(value=t["bad"], rtl=rtl), gr.update(value="", rtl=rtl), audio, a.text, None)

        progress(0.6, desc=steps[2])
        explanation = explain(a.text, a.info, lang).split("\n\n(⚠")[0]
        card = summary_card(a, lang)

        audio = None
        if read_aloud:
            progress(0.85, desc=steps[3])
            facts = SpokenFacts(sender=a.info.sender, deadline=a.deadline, amount=a.amount,
                                receives=a.receives, reference=a.reference, amount_unclear=a.amount_unclear)
            audio = str(speak(build_script(facts, explanation, lang), lang, path.stem, slow=slow, play=False))

        state = {"text": a.text, "info": a.info.model_dump(), "reference": a.reference}
        return (gr.update(value=card, rtl=rtl), gr.update(value=explanation, rtl=rtl), audio, a.text, state)
    except gr.Error:
        raise
    except Exception as e:  # e.g. Ollama not running
        raise gr.Error(t["error"].format(e=e))


def write_reply(state, intent, note, lang, progress=gr.Progress()):
    progress(0.1, desc=STEPS[lang][4])
    if not state:
        raise gr.Error(UI_TEXT[lang]["no_file"])
    from amt_lotse.extract import LetterInfo

    info = LetterInfo(**state["info"])
    draft = build_reply(state["text"], info, state["reference"], intent, LANGUAGES[lang], note or None)
    out = Path(tempfile.mkdtemp(prefix="amt_lotse_reply_")) / f"Antwort_{intent}.txt"
    out.write_text(draft.german, encoding="utf-8")
    notes = draft.summary + "".join(f"\n\n⚠️ {w}" for w in draft.warnings)
    return draft.german, gr.update(value=notes, rtl=lang == "ar"), str(out)


def build_ui() -> gr.Blocks:
    with gr.Blocks(title="Amt-Lotse") as ui:
        gr.Markdown("# 📬 Amt-Lotse\n**Understand German official letters — in your language, out loud, privately on this computer.**")

        lang = gr.Radio(LANG_CHOICES, value="en", label="Language / Langue / اللغة / Sprache")

        with gr.Row():
            file_in = gr.File(label="Letter: photo, PDF or text", file_types=[".jpg", ".jpeg", ".png", ".pdf", ".txt"], type="filepath")
            photo_in = gr.Image(label="…or take a photo", sources=["webcam", "upload"], type="filepath")

        examples = [[str(p)] for p in EXAMPLES if p.exists()]
        if examples:
            gr.Examples(examples, inputs=[file_in], label="🧪 Try an example letter (fictional test data)")

        with gr.Row():
            read_aloud = gr.Checkbox(value=True, label="🔊 Read aloud")
            slow = gr.Checkbox(value=True, label="🐢 Slow speech")

        go = gr.Button("📖 Explain this letter", variant="primary", size="lg", elem_classes="big-button")
        gr.Markdown("<small>⏳ The first time can take 1–2 minutes while the AI models load. The progress is shown below.</small>")

        card = gr.Markdown(elem_classes="card")
        audio = gr.Audio(label="🔊 Listen", autoplay=True, type="filepath")
        explanation = gr.Markdown(elem_classes="explanation")
        with gr.Accordion("What the computer read (for a helper to check)", open=False):
            read_text = gr.Textbox(lines=12, show_label=False, buttons=["copy"])

        state = gr.State()

        gr.Markdown("---\n## ✉️ Write a reply in German")
        with gr.Row():
            intent = gr.Dropdown(REPLY_CHOICES, value="question", label="What do you want to say?")
            note = gr.Textbox(label="Your own information (any language, optional)", placeholder="e.g. I am sick until 10 December")
        reply_btn = gr.Button("✍️ Write reply", size="lg")
        reply_text = gr.Textbox(label="Reply letter (German) – fill in every [placeholder]", lines=18, buttons=["copy"])
        reply_notes = gr.Markdown()
        reply_file = gr.File(label="Download")

        gr.Markdown("<small>Automatic summary – always double-check the original letter. Not legal advice: for important decisions, ask an advice centre (Beratungsstelle).</small>")

        go.click(explain_letter, [file_in, photo_in, lang, read_aloud, slow],
                 [card, explanation, audio, read_text, state])
        reply_btn.click(write_reply, [state, intent, note, lang], [reply_text, reply_notes, reply_file])
    return ui


def main() -> None:
    # 127.0.0.1 = only this computer can open it. Letters never leave the machine.
    build_ui().launch(server_name="127.0.0.1", inbrowser=True, css=CSS)


if __name__ == "__main__":
    main()
