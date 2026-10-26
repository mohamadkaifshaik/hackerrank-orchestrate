# Usage report

Final full-dataset run: `python code/main.py` → `output.csv` (518 rows).

## Runtime model usage (measured)

| Provider | Model | Calls | Input tokens | Output tokens | Cost |
|---|---|---|---|---|---|
| none | none | 0 | 0 | 0 | $0.00 |

* Total tokens: 0. Average tokens per request: 0. Estimated cost per request: $0.00.
* The run is fully deterministic and offline (about 2 s). No API key was available, and the optional hook
  in `audit/llm.py` (`--llm`, reads `ANTHROPIC_API_KEY`) was not used: every request text was classified by
  the deterministic rules, none was ambiguous. `audit/llm.py` writes a ledger (`cache/usage_ledger.json`)
  and a response cache when it is used; neither file exists for this run, which is consistent with 0 calls.

## Manual AI-assisted extraction (disclosed)

Unstructured evidence was read once by the coding agent (Claude Code, `claude-sonnet-5-5`) during
development, not by the shipped program. The results are cached under their original evidence ids and the
program only reads those caches:

| Artifacts | Method | Cache |
|---|---|---|
| 11 PNG screenshots (evidence_04, 09, 14, 19, 23, 28, 32, 37, 42, 46, 60) | Built-in image viewing in the agent session; only printed values were recorded, anything not visible is `null` | `cache/image_extractions.json` |
| 4 PDFs (evidence_18, 27, 55, 58) | `pdftotext -layout` text read and transcribed by the agent | `cache/document_extractions.json` |

* These reads happened inside the interactive agent session, so they are **not metered as API calls** by the
  program and the harness did not report per-step token counts. No figure is claimed. For scale only: an image of
  this size is typically a few thousand input tokens, so the whole manual extraction is on the order of tens of
  thousands of tokens (an estimate, not a measurement).
* Reproducibility: with the caches present, reruns need no model. The full coding session is recorded in
  the root `log.txt`.
* Three screenshots deliberately keep unclear values as `null` (for example, evidence_32 does not show restore
  access); the pipeline treats that as "unproven", not as a guess.

## Totals

* Model-call count at run time: 0 (overall and per model).
* Manual extraction: 15 artifacts, 1 model (`claude-sonnet-5-5`), token count not metered.
