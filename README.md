
# Amt-Lotse
**An AI assistant that explains German official letters, privately on your own machine!!**

Are you new in Germany ? Letters from the krankenkasse ,Beitragsservice or Finanzamt are hard to understand , even with good German. So Amt-lotse reads the letters and tells you in SIMPLE WORDS what it means , the DEADLINE, the AMOUNT, and what you have to do.
## Why local at first ?
Official letters contain private data(ID, ...)
Amt-lotse runs a local LLM via OLLAMA ,  SO **tour letters never leave your machine!**


## Status 
Early development: currently extracts deadline , amount and required action from text letters with local model (Qwen2.5 7B)

## Quick start
Requirement :Pyhton 3.12+, [uv](https://docs.astral.sh/uv/),[Ollama]
Ollama pull qwen2.5:7b
uv sync
uv run python src/amt_lotse/hello_llm.py
 ## Evaluation
`uv run python -m amt_lotse.evaluate` scores the extractor against hand-labelled letters in `data/eval/`.

| Model | Fields correct | Time (4 letters) |
|---|---|---|
| qwen2.5:3b | 12/12 | 16 s |
| qwen2.5:7b | 12/12 | 79 s |

## Roadmap
 - [x] Local LLM reads a sample letter
 - 
 - OCR
 - Explanation in English , Frensh , Arabic + reply drafrs
 - MCP server + agent , web UI ,Docker