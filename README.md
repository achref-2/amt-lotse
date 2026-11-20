# Amt-Lotse
**An AI assistant that explains German official letters — in your language, out loud, and privately on your own machine.**

Letters from the Jobcenter, the Krankenkasse, the Finanzamt or the Ausländerbehörde are hard to understand, even with good German. For many people they are much harder:

- **new immigrants** who are still learning German,
- **blind and visually impaired people** who cannot read a paper letter,
- **older people** who find small print and official language overwhelming.

Amt-Lotse reads the letter and tells you in simple words: **who sent it, the deadline, how much you have to pay (or receive), and what you have to do** — in English, French, Arabic or simple German, and if you want, **read aloud**.

## Why local first?
Official letters contain private data (IDs, addresses, tax numbers).
Amt-Lotse runs local models via [Ollama](https://ollama.com) and [Piper](https://github.com/OHF-Voice/piper1-gpl), so **your letters never leave your machine** — no cloud API, no account.

## Example

```text
$ uv run amt-lotse data/eval/mahnung_01.txt --speak

============================================================
  From:       Muster Mobilfunk GmbH
  Subject:    2. Mahnung
  Deadline:   04.12.2026  (in 14 days)
  You pay:    56,13 €
  Reference:  RE-2026-08812  (always quote this number)
============================================================

What this means:

The letter was sent by Muster Mobilfunk GmbH. It is a second reminder
for an unpaid invoice. You have to pay 56,13 € by 4 December 2026 and
use the reference number RE-2026-08812. If you do not pay on time, the
debt may be passed to a collection agency, which causes extra costs.

Creating audio ...
Audio saved: audio/mahnung_01_en.wav
```

## Features
- **Structured extraction** – sender, deadline, amount, reference number, required action (local LLM, JSON schema output)
- **Plain-language explanation** in English, French, Arabic or simple German (`--lang en|fr|ar|de`)
- **Read aloud** (`--speak`), designed for accessibility:
  - key facts first: deadline, amount, reference number
  - facts come from the checked extraction, not from free LLM text, so dates and amounts are not invented
  - dates and amounts spoken as words, reference numbers spelled out so they can be written down
  - slower speech by default, the most important point repeated at the end
  - saved as `.wav`, so it can be replayed or sent to someone
- **Guardrails** on top of the LLM:
  - yes/no gating for deadlines and payments (an info date is not a deadline, a refund is not a payment)
  - rule-based credit check (*Guthaben*, *Erstattung*) after the model
  - language and script check with automatic retry
- **Evaluation harness** with hand-labelled test letters

## Quick start
Requirements: Python 3.14+, [uv](https://docs.astral.sh/uv/), [Ollama](https://ollama.com)

```bash
ollama pull qwen2.5:3b     # reads the letter
ollama pull qwen2.5:7b     # writes the explanation
uv sync

uv run amt-lotse data/eval/mahnung_01.txt                     # English
uv run amt-lotse data/eval/jobcenter_01.txt --lang ar --speak # Arabic, read aloud
```

Voices for `--speak` are downloaded automatically on first use (into `voices/`).

| Option | Effect |
|---|---|
| `--lang en\|fr\|ar\|de` | language of the explanation and audio |
| `--speak` | read aloud and save as `audio/<letter>_<lang>.wav` |
| `--normal-speed` | normal speaking speed (default is slower) |
| `--no-play` | only save the audio file |

Models can be changed with `AMT_LOTSE_MODEL` (extraction) and `AMT_LOTSE_EXPLAIN_MODEL` (explanation).

## Architecture

```text
letter.txt ──► extract (Qwen2.5 3B, JSON schema) ──► guardrails ──► summary card
                                                         │
                                                         ├──► explain (Qwen2.5 7B, chosen language) ──► language check
                                                         │
                                                         └──► speak (Piper TTS, offline) ──► audio/*.wav
```

| File | Role |
|---|---|
| `src/amt_lotse/extract.py` | LLM extraction, date/amount parsing, guardrails |
| `src/amt_lotse/cli.py` | `amt-lotse` command, explanation, language check |
| `src/amt_lotse/speak.py` | spoken script in 4 languages, Piper TTS |
| `src/amt_lotse/evaluate.py` | scores the extractor against `data/eval/` |

## Evaluation
`uv run python -m amt_lotse.evaluate` scores the extractor against 12 hand-labelled letters in `data/eval/` (Jobcenter, Ausländerbehörde, Finanzamt, Krankenkasse, Beitragsservice, landlord, university, debt reminder).

The test letters contain deliberate traps: several dates where only one is a deadline, a refund that looks like a payment, invoice + fees + total, two reference numbers, amounts like `1.343,27 €`, and a relative deadline ("innerhalb von vier Wochen").

| Model | Fields correct | Time (12 letters) |
|---|---|---|
| qwen2.5:3b + guardrails | **36/36** | ~35 s |

Earlier, on the first 4 letters, 3B and 7B both reached 12/12, with 3B about 5× faster — so 3B is the default for extraction. The explanation step uses 7B, because 3B often failed to answer in Arabic.

All test letters are fictional and marked as test data.

## Limitations
- Input is plain text for now (no photos or scans yet).
- The free-text explanation is not evaluated yet and can be imprecise — always check the original letter.
- This is not legal advice. For important decisions, ask an advice centre (Beratungsstelle).

## Roadmap
- [x] Local LLM reads a sample letter
- [x] Structured extraction (deadline, amount, reference number) + evaluation set
- [x] Harder test letters with traps (12 letters, 36/36)
- [x] Explanations in English, French, Arabic and simple German
- [x] Read aloud with offline TTS, accessibility-first
- [ ] Evaluation for the explanation text
- [ ] OCR for scanned/photographed letters
- [ ] Reply drafts (e.g. asking for a payment plan or more time)
- [ ] Web UI with a big "Listen" button, voice input
- [ ] MCP server + agent, Docker
