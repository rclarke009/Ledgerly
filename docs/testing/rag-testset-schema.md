# Schema, Splits, and Hygiene

*Companion to [rag-testset.md](rag-testset.md). Item craft: [golden](rag-testset-golden.md) · [fuzz](rag-testset-fuzz.md). Freeze ritual: [baseline-scenario-verbiage.md](baseline-scenario-verbiage.md).*

---

This file is so you can add cases without poisoning the freezer. One schema per `evals/vN/`; new fields mean a new version if old graders would break.

## Record fields

| Field | Required | Notes |
|---|---|---|
| `id` | yes | Stable string, unique in this version (`g-001`, `f-001`) |
| `split` | yes | `core` \| `fuzz` \| `canary` \| `held_out` |
| `query` | yes | Exact string you will send |
| `doc_ids` | retrieval items | Corpus docs a human marked relevant |
| `relevant_chunk_ids` | retrieval items | Prefer chunks when your metric is recall@k on chunks |
| `reference_answer` | e2e slice only | Omit on refusal gold and most fuzz |
| `expect_refusal` | refusal items | `true` when gate / "not enough information" is the gold |
| `tags` | yes | Coverage axes from the index matrix (`fact_lookup`, `hard_negative`, …) |
| `parent_id` | fuzz children | Golden `id` this variant comes from |
| `notes` | recommended | Why it is hard; do not put the answer here |
| `labeler` | yes | Person (or `pair:a+b` if dual-labeled) |
| `labeled_at` | yes | ISO date |

Canary rows can be a separate tiny file (as in the baseline scenario) graded structurally. If they live in the same JSONL, `split: canary` and no LLM judge in `grade.py` for that split.

## Splits

- **`core`** — Frozen gold. Tune chunk size, top-k, gate threshold against this. Headline recall@k is this split unless you say otherwise.
- **`held_out`** — Same labeling standard, **not** used for tuning. Run once when you claim a number for a paper, a job story, or a release note. If you peek and retune, it is no longer held out — cut a new version.
- **`fuzz`** — Children of `core` (or of held_out if you explicitly want an unseen-paraphrase check). Do not mix into the core recall average without labeling it as such.
- **`canary`** — Tiny, deterministic, no judge. See baseline Act 0 / Act 5. Do not grow this into a second eval set.

## Synthetic generation

LLM-written questions are **drafts**. Allowed: propose paraphrases, propose questions from a span. Not allowed: freeze retrieval IDs or reference answers without a human checking that the span actually answers the question.

Never freeze an LLM-written gold answer that you have not verified against the chunk. That labels the model's prior, not the corpus.

## Flywheel

Production thumbs-down (or "I don't know" that should have been answerable) → candidate list → human label → **`evals/vN+1/`**. Never edit `vN`. The baseline walkthrough's 120-question file is an example of a frozen snapshot, not a living spreadsheet.

If the index or chunker changes, IDs in `vN` may be invalid. Relabel in the new directory; do not "fix" old JSONL in place.
