# Golden Set — Known-Right Retrieval and Answers

*Companion to [rag-testset.md](rag-testset.md). Fuzz children: [rag-testset-fuzz.md](rag-testset-fuzz.md). Fields and splits: [rag-testset-schema.md](rag-testset-schema.md).*

---

**Golden** here means human (or high-agreement) ground truth. You use it for recall@k / MRR (did the right chunk appear) and for end-to-end match (did the final answer match the reference). It is not where you dump paraphrase volume — that is fuzz, tagged with a `parent_id`.

## Write the span first, then the question

Pick a source span you can point at. Then write a question a user would actually ask that *requires* that span. If you write the question first, you invent unanswerable gold: the label says chunk X, but X does not contain the answer.

Record at least:

- `query`
- `relevant_chunk_ids` and/or `doc_ids` (whatever your index uses — stay consistent inside `evals/vN/`)
- optional `reference_answer` (only if you will score e2e against it)
- `notes` — why this is hard (sibling section, number vs prose, two reports)

## Hard negatives

A hard negative is a query that should *not* retrieve a tempting sibling: same report, wrong heading (roof vs HVAC, exterior vs interior water). Label the *correct* IDs. If the wrong sibling ranks first, retrieval failed even if a "related" report is in the list.

These are still gold items, not fuzz. The intent is specific; the trap is ranking.

## Refusal gold

Questions the corpus cannot answer. Expected behavior: cosine gate fires and/or the prompt refuses with "not enough information" — not a fabricated number from a nearby report.

Label: empty `relevant_chunk_ids` (or an explicit `expect_refusal: true`). Do not write a `reference_answer` that invents a fact. The gold is the *refusal*, not an answer string.

Out-of-index documents belong here for this eval version. If you later ingest that county's reports, that item moves to a new version with real IDs — it does not get silently edited in `v1`.

## Staleness

Chunk IDs die when you re-chunk or re-ingest. Version the set with the index: same `evals/vN/` directory as in the baseline walkthrough. New ingest → `vN+1` with relabeled IDs, not a hotfix in the frozen file.

## Anti-patterns

- **Paraphrasing the chunk into the question.** Retrieval becomes a near-duplicate search. Too easy; you will not catch embedding or chunk-boundary failures.
- **Leaking the answer into the query.** "Was wind speed 74 mph?" tests confirmation, not lookup.
- **Two gold answers for one ID.** Pick one reference or split into two items. Graders cannot agree if both "yes, minor" and "replace the whole roof" are marked correct.
- **Using fuzz volume as gold.** Ten paraphrases of one fact are one fact. Score them as children; do not pretend you have ten independent retrieval labels.

## Example JSONL

Shape matches `evals/v1/dataset.jsonl` in the baseline scenario. Extra fields (`split`, `tags`, `parent_id`) are defined in the schema doc; omit `parent_id` on core gold.

```json
{"id": "g-001", "split": "core", "query": "What wind speed was recorded at the Oak Street inspection?", "doc_ids": ["rpt-oak-2024"], "relevant_chunk_ids": ["rpt-oak-2024:weather"], "reference_answer": "74 mph peak gust, per the weather section.", "tags": ["fact_lookup"], "notes": "Number lives only in weather section, not summary."}
{"id": "g-002", "split": "core", "query": "Did the Oak Street report find HVAC damage from the same storm as the roof?", "doc_ids": ["rpt-oak-2024"], "relevant_chunk_ids": ["rpt-oak-2024:roof", "rpt-oak-2024:hvac"], "reference_answer": "Roof: hail damage. HVAC: no storm-related damage; age-related wear only.", "tags": ["multi_section", "hard_negative"], "notes": "HVAC section is the tempting wrong hit for 'damage'."}
{"id": "g-003", "split": "core", "query": "What deductible applies to flood at Oak Street?", "doc_ids": [], "relevant_chunk_ids": [], "expect_refusal": true, "tags": ["refusal", "ood"], "notes": "Reports cover wind/hail only; no flood policy language."}
```
