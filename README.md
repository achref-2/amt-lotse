# Amt-Lotse
**An AI assistant that explains German official letters, privately on your own machine.**

New in Germany? Letters from the Krankenkasse, the Beitragsservice or the Finanzamt are hard to understand, even with good German. Amt-Lotse reads the letter and tells you in simple words what it means: the **deadline**, the **amount**, and **what you have to do**.

## Why local first?
Official letters contain private data (IDs, addresses, tax numbers).
Amt-Lotse runs a local LLM via [Ollama](https://ollama.com), so **your letters never leave your machine**.

## Status
Early development: extracts deadline, amount, reference number and required action from text letters with a local model (Qwen2.5 3B).

## Quick start
Requirements: Python 3.14+, [uv](https://docs.astral.sh/uv/), [Ollama](https://ollama.com)

```bash
ollama pull qwen2.5:3b
uv sync
uv run python src/amt_lotse/extract.py
```

To try another model: set `AMT_LOTSE_MODEL`, e.g. `AMT_LOTSE_MODEL=qwen2.5:7b`.

## Evaluation
`uv run python -m amt_lotse.evaluate` scores the extractor against hand-labelled letters in `data/eval/`.

| Model | Fields correct | Time (4 letters) |
|---|---|---|
| qwen2.5:3b | 12/12 | 16 s |
| qwen2.5:7b | 12/12 | 79 s |

Qwen2.5 3B is the default: same accuracy, about 5× faster on a consumer GPU.

## Roadmap
- [x] Local LLM reads a sample letter
- [x] Structured extraction (deadline, amount, reference number) + evaluation set
- [ ] More and harder test letters
- [ ] OCR for scanned/photographed letters
- [ ] Explanations in English, French and Arabic + reply drafts
- [ ] MCP server + agent, web UI, Docker
