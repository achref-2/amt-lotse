"""Builds docs/index.html: the always-online start page on GitHub Pages (https://achref-2.github.io/amt-lotse/).

The page itself is static, so it is online even when the PC is off. It asks the app on the PC
(<APP>/amt-status, reached through Tailscale Funnel) whether the AI is ready, then shows either
an "Open Amt-Lotse" button or "The AI server is off". Texts and artwork come from landing.py.

    uv run python scripts/build_status_page.py https://<your-pc>.<your-tailnet>.ts.net
"""

import json
import sys
from html import escape
from pathlib import Path

from amt_lotse.app import LANG_CHOICES
from amt_lotse.cli import RTL_LANGUAGES
from amt_lotse.landing import HERO_ART, LOGO, TEXT

ROOT = Path(__file__).resolve().parents[1]
KEYS = ["eyebrow", "tagline", "lead", "ai_on", "ai_off_h", "ai_off", "open_app", "checking"]

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Amt-Lotse – understand letters from German offices</title>
<meta name="description" content="Explains letters from German offices in 8 languages, reads them aloud and drafts replies. The AI runs privately.">
<link rel="icon" href="data:image/svg+xml,{icon}">
<style>
:root {{ --blue:#1f5fd1; --blue-dark:#174bb0; --ink:#0f1b33; --muted:#45536e; --surface:#fff; --soft:#f1f5fe;
  --line:#dbe4f5; --green:#0f8a45; --red:#c40000; --shadow:0 1px 2px rgba(15,27,51,.06),0 12px 32px -12px rgba(15,27,51,.18); }}
@media (prefers-color-scheme: dark) {{ :root {{ --ink:#e8eefc; --muted:#aab6cd; --surface:#131b2c; --soft:#0e1524;
  --line:#2a3650; --shadow:0 1px 2px rgba(0,0,0,.3),0 12px 32px -12px rgba(0,0,0,.6); }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; font:20px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,"Noto Sans",sans-serif; color:var(--ink);
  background:var(--soft); }}
main {{ max-width:1080px; margin:auto; padding:20px 20px 40px; }}
.top {{ display:flex; align-items:center; justify-content:space-between; gap:16px; flex-wrap:wrap; }}
.brand {{ display:flex; align-items:center; gap:12px; font-weight:800; font-size:1.25em; }}
.brand svg {{ width:44px; height:44px; }}
.langs {{ display:flex; flex-wrap:wrap; gap:8px; }}
.langs button {{ font:inherit; font-size:.8em; padding:6px 14px; border-radius:999px; border:1px solid var(--line);
  background:var(--surface); color:var(--ink); cursor:pointer; }}
.langs button[aria-pressed="true"] {{ background:var(--blue); border-color:var(--blue); color:#fff; }}
.hero {{ display:grid; grid-template-columns:1.25fr 1fr; gap:24px; align-items:center; margin-top:28px; }}
.eyebrow {{ color:var(--blue); font-weight:700; margin:0; }}
h1 {{ font-size:2.3em; line-height:1.15; margin:.25em 0 .35em; }}
.lead {{ color:var(--muted); margin:0 0 18px; }}
.badges {{ display:flex; flex-wrap:wrap; gap:8px; padding:0; margin:0; list-style:none; }}
.badges li {{ background:var(--surface); border:1px solid var(--line); border-radius:999px; padding:4px 14px; font-size:.8em; }}
.art {{ width:100%; height:auto; }}
.status {{ margin-top:28px; background:var(--surface); border:1px solid var(--line); border-radius:20px; padding:24px;
  box-shadow:var(--shadow); display:flex; align-items:center; gap:20px; flex-wrap:wrap; min-height:110px; }}
.status p {{ margin:0; }}
.dot {{ width:16px; height:16px; border-radius:50%; background:#aab6cd; flex:none; }}
.on .dot {{ background:var(--green); box-shadow:0 0 0 6px rgba(15,138,69,.15); }}
.off .dot {{ background:var(--red); box-shadow:0 0 0 6px rgba(196,0,0,.12); }}
.msg {{ flex:1; min-width:220px; }}
.msg strong {{ display:block; font-size:1.15em; }}
.open {{ display:inline-block; background:var(--blue); color:#fff; text-decoration:none; font-weight:700;
  padding:16px 30px; border-radius:14px; font-size:1.1em; }}
.open:hover {{ background:var(--blue-dark); }}
.open[hidden] {{ display:none; }}
footer {{ margin-top:32px; color:var(--muted); font-size:.8em; }}
footer a {{ color:var(--blue); }}
@media (max-width:720px) {{ .hero {{ grid-template-columns:1fr; }} .art {{ max-width:300px; margin:auto; display:block; }}
  h1 {{ font-size:1.7em; }} .open {{ width:100%; text-align:center; }} }}
</style>
</head>
<body>
<main>
  <div class="top"><div class="brand">{logo}<span>Amt-Lotse</span></div>
    <nav class="langs" aria-label="Language">{langs}</nav></div>
  <section class="hero">
    <div><p class="eyebrow" data-t="eyebrow"></p><h1 data-t="tagline"></h1><p class="lead" data-t="lead"></p>
      <ul class="badges" id="badges"></ul>
      <div class="status" id="status" aria-live="polite">
        <span class="dot"></span>
        <p class="msg"><strong id="msg-h" data-t="checking"></strong><span id="msg"></span></p>
        <a class="open" id="open" href="{app}" hidden data-t="open_app"></a>
      </div></div>
    <div>{art}</div>
  </section>
  <footer>Source code and how it works: <a href="https://github.com/achref-2/amt-lotse">github.com/achref-2/amt-lotse</a></footer>
</main>
<script>
const APP = {app_js};
const TEXT = {text};
const RTL = {rtl};
let lang = "en", state = "checking";
try {{ lang = localStorage.getItem("amt-lang") || ""; }} catch (e) {{}}
if (!TEXT[lang]) {{ const nav = (navigator.language || "en").slice(0, 2); lang = TEXT[nav] ? nav : "en"; }}

function render() {{
  const t = TEXT[lang];
  document.documentElement.lang = lang;
  document.documentElement.dir = RTL.includes(lang) ? "rtl" : "ltr";
  document.querySelectorAll("[data-t]").forEach(el => {{ el.textContent = t[el.dataset.t]; }});
  document.getElementById("badges").innerHTML = "";
  t.badges.forEach(b => {{ const li = document.createElement("li"); li.textContent = b;
    document.getElementById("badges").appendChild(li); }});
  document.querySelectorAll(".langs button").forEach(b => b.setAttribute("aria-pressed", b.dataset.lang === lang));
  const box = document.getElementById("status");
  box.className = "status " + state;
  const h = document.getElementById("msg-h"), m = document.getElementById("msg");
  document.getElementById("open").hidden = state !== "on";
  if (state === "on") {{ h.textContent = t.ai_on; m.textContent = ""; }}
  else if (state === "off") {{ h.textContent = t.ai_off_h; m.textContent = t.ai_off; }}
  else {{ h.textContent = t.checking; m.textContent = ""; }}
}}

async function check() {{
  const stop = new AbortController();
  const timer = setTimeout(() => stop.abort(), 8000);
  try {{
    const r = await fetch(APP + "/amt-status", {{ cache: "no-store", signal: stop.signal }});
    const s = await r.json();
    state = s.ai ? "on" : "off";
  }} catch (e) {{ state = "off"; }}
  clearTimeout(timer);
  render();
}}

document.querySelectorAll(".langs button").forEach(b => b.addEventListener("click", () => {{
  lang = b.dataset.lang;
  try {{ localStorage.setItem("amt-lang", lang); }} catch (e) {{}}
  render();
}}));
render();
check();
setInterval(check, 30000);
</script>
</body>
</html>
"""


def build(app_url: str) -> str:
    app_url = app_url.rstrip("/")
    if not app_url.startswith("https://"):
        raise SystemExit("The app address must start with https:// (Tailscale Funnel gives one)")
    # badge 1 says "AI on this computer" in the app; here the visitor's computer is not the one with the AI
    texts = {lang: {**{k: TEXT[lang][k] for k in KEYS}, "badges": [TEXT[lang]["badge_cloud"], *TEXT[lang]["badges"][1:]]}
             for lang in TEXT}
    langs = "".join(f'<button type="button" data-lang="{code}">{escape(name)}</button>' for name, code in LANG_CHOICES)
    icon = LOGO.replace("\n", "").replace("#", "%23").replace('"', "'").replace("<", "%3C").replace(">", "%3E")
    return PAGE.format(icon=icon, logo=LOGO, art=HERO_ART, langs=langs, app=escape(app_url),
                       app_js=json.dumps(app_url), text=json.dumps(texts, ensure_ascii=False),
                       rtl=json.dumps(sorted(RTL_LANGUAGES)))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    out = ROOT / "docs" / "index.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(build(sys.argv[1]), encoding="utf-8")
    print(f"Wrote {out}. Push it, then: GitHub → Settings → Pages → Branch main, folder /docs.")
