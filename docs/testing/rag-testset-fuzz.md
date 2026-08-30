# Fuzz, Paraphrases, and Stress — Around the Golden Core

*Companion to [rag-testset.md](rag-testset.md). Parents live in [rag-testset-golden.md](rag-testset-golden.md). `parent_id` and splits: [rag-testset-schema.md](rag-testset-schema.md).*

---

Fuzz is robustness around gold, not a second gold standard. You are asking: *same intent, does retrieval (and routing) still work?* You are not multiplying independent facts.

Every fuzz row should point at a golden `parent_id` so a failure attributes: "broke on paraphrase, not on the underlying fact" vs "the parent was already wrong."

## Paraphrase families

Same intent, different surface form. Typical family for one parent:

- **Typos / informal spelling**
- **Casual** vs **formal** register
- **Synonyms** (wind speed / peak gust / recorded velocity)
- **Reordered constraints** (site first vs quantity first)

Do not write a new `reference_answer` unless a human re-labels it. Default: inherit the parent's relevant IDs and, if you score e2e, the parent's answer — or score *retrieval overlap with parent gold* only.

## Query-type fuzz (Verbiage routing)

Verbiage auto-routes short/quoted queries to **lexical** (Postgres `ts_rank` + `websearch_to_tsquery`) and longer prose to **hybrid RRF**. Your fuzz set should include cases that **should stay on each path**, not only long questions.

| Intent | Surface | Expected path (this stack) |
|---|---|---|
| Quoted section or exact phrase | `"4.2 Roof covering"` | Lexical |
| Short identifier | report / claim number, site code | Lexical |
| Natural question | full sentence, no quotes | Hybrid |

If you only fuzz long paraphrases, you never test the lexical leg. If you only fuzz quoted titles, you never test dense retrieval.

## Adversarial / stress (system behavior, not attack recipes)

These check that the pipeline does not quietly do the wrong thing. They are not a guide for bypassing the product.

- **Distractor entities** in the question (mention report B while the answer is only in A) — retrieval should still prefer A's labeled chunks.
- **Conflicting numbers** in the query vs the corpus — the answer should follow the document, or refuse if the question is ill-posed; do not "average" them.
- **Empty query** / whitespace-only — should not call the LLM with garbage context; fail closed.
- **Huge query** — truncation, timeout, or reject; document the actual contract.
- **Unicode / punctuation** — quotes, curly apostrophes, units (`mph` vs `mi/h`).
- **Injection-shaped text in the *query*** vs the same string in a *document*. The system should treat user text as a question, not as instructions to ignore the corpus. Retrieved *documents* that contain "ignore previous instructions" should still be treated as source text to quote or refuse on, not as a new system prompt. You are testing isolation of roles (user vs corpus vs system), not how to jailbreak.

Keep these tagged (`adversarial`, `stress`). Most should not get a new reference answer.

## What not to assert

- Do not treat ten paraphrases as ten independent recall events in a headline metric without saying so. Report **parent-level** recall and **paraphrase-break rate** (share of children that miss the parent's IDs).
- Do not fail a fuzz child because the *wording* of the generated answer differs from gold if you only labeled retrieval — score the layer you labeled.
- Do not put canary logic in fuzz. Canaries are three dumb structural checks with no judge — baseline walkthrough Act 0 / Act 5.

## Hypothesis vs RAG fuzz

[testing-tools-practice.md](testing-tools-practice.md) uses Hypothesis for **properties of functions** (e.g. a zip range always comes back ordered). That is generated *inputs to code*. RAG fuzz is a **query distribution**: hand- or LLM-drafted variants of real user language, then labeled. Do not generate random unicode strings as "eval questions" and call them a golden set. Use Hypothesis on chunkers, validators, and API bounds; use this doc for retrieval/generation cases.
