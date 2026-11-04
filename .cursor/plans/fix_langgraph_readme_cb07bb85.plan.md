---
name: Fix LangGraph README
overview: Align the root README with the actual Ask pipeline, and drop the unused `langgraph` dependency so the docs and install requirements match the code.
todos:
  - id: readme
    content: Rewrite the two LangGraph claims in README.md to match heuristic routing in ask_graph.py
    status: completed
  - id: dep
    content: Remove unused langgraph from requirements.txt and the note in docs/ask-pipeline-flow.md
    status: completed
isProject: false
---

# Align README with the Ask pipeline

The product README claims a LangGraph Ask pipeline. The code does not use it.

- [README.md](README.md) line 15 calls the feature a **LangGraph Ask pipeline**, and the architecture table (line 37) lists **LangGraph** under Ask routing.
- [app/ask_graph.py](app/ask_graph.py) is a sequential async pipeline (`heuristic_route` → fast paths → structured data → `run_ask_tools` → retrieval / optional rerank → `build_prompt_and_chunks`). No file imports `langgraph` or `StateGraph`.
- [requirements.txt](requirements.txt) still lists `langgraph` (line 16), which [docs/ask-pipeline-flow.md](docs/ask-pipeline-flow.md) already flags as unused.

## Changes

- In [README.md](README.md), describe the Ask feature as heuristic routing plus local finance tools, retrieval, and optional reranking. Point at `app/ask_graph.py` as the implementation. Remove both LangGraph mentions.
- Remove `langgraph` from [requirements.txt](requirements.txt).
- Update the note at the top of [docs/ask-pipeline-flow.md](docs/ask-pipeline-flow.md) so it no longer says `langgraph` is in `requirements.txt`. Keep the explanation that the filename is historical and the pipeline is not a `StateGraph`.

## Left as-is

- [installer/output/Ledgerly/](installer/output/Ledgerly/) is a portable snapshot produced by [installer/build_portable_zip.py](installer/build_portable_zip.py). It will pick up the README and requirements on the next portable build.
- [docs/testing/langgraph-rag-testing-plan.md](docs/testing/langgraph-rag-testing-plan.md) and one sentence in [test_plan.md](test_plan.md) still describe an older LLM classifier / LangGraph graph. That is a separate docs rewrite, not this README fix.
