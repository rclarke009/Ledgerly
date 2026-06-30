# Current Ask Pipeline (State-Style Flow)

**Ledgerly / Finelly** — Ask orchestration as implemented in `app/ask_graph.py` and `app/main.py`.

> **Note:** Despite the filename `ask_graph.py` and `langgraph` in `requirements.txt`, the codebase **does not currently use LangGraph's `StateGraph` API**. The pipeline is a sequential async function (`build_prompt_and_chunks`) plus API branching in `main.py`.

---

## Main flow

```mermaid
flowchart TD
    START([POST /ask or /ask/stream]) --> API{API entry}
    API --> BUILD[build_prompt_and_chunks]

  subgraph PREP["Prep pipeline (app/ask_graph.py)"]
    BUILD --> QCHK{Question empty?}
    QCHK -->|yes| EXIT_EMPTY[Return: has_context=false]
    QCHK -->|no| SCOPE[resolve_doc_scope]
    SCOPE --> HIST{conversation_id?}
    HIST -->|yes| LOAD[load_conversation_turns]
    HIST -->|no| ROUTE
    LOAD --> ROUTE[heuristic_route]
    
    ROUTE --> R1{Route?}
    
    R1 -->|fast_path| FP[try_fast_path_answer]
    FP --> FP_OK{Answer found?}
    FP_OK -->|yes| RET_FP[Return direct_answer, route=fast_path, 0 LLM]
    FP_OK -->|no| LAYER2

    R1 -->|structured_data / rag / rag_only| LAYER2[_layer2_summary<br/>accounts · positions · obligations]
    LAYER2 --> TOOLS[run_ask_tools<br/>heuristic local tools]
    
    TOOLS --> RAG_GATE{_skip_rag_for_structured?}
    RAG_GATE -->|yes<br/>structured + data + no doc scope| SKIP_RAG[Skip embedding + retrieval]
    RAG_GATE -->|no| USE_RAG{use_rag AND route allows RAG?}
    USE_RAG -->|no| SKIP_RAG
    USE_RAG -->|yes| EMBED[expand_retrieval_query → embed_text]
    EMBED --> RETRIEVE[retrieve_top_k<br/>filters · boost · optional rerank]
    
    SKIP_RAG --> RELATED
    RETRIEVE --> RELATED[detect_related_documents]
    
    RELATED --> CTX{_need_more_context?<br/>no chunks AND no layer2 AND no tools}
    CTX -->|yes AND route ≠ structured_data| EXIT_NC[Return: has_context=false]
    CTX -->|no| PROMPT[_build_rag_messages]
    PROMPT --> RET_MSG[Return messages + chunks, has_context=true]
  end

  RET_FP --> API_OUT
  EXIT_EMPTY --> API_OUT
  EXIT_NC --> API_OUT
  RET_MSG --> API_OUT

  subgraph API_LAYER["API layer (app/main.py)"]
    API_OUT{has_context?}
    API_OUT -->|no| NO_CTX["Fixed: I don't have relevant context…"]
    API_OUT -->|yes| DIRECT{direct_answer?}
    DIRECT -->|yes| FAST_OUT[Return / stream answer<br/>no LLM]
    DIRECT -->|no| RL[rate_limiter.acquire]
    RL --> LLM[llm_client.answer_with_messages<br/>or stream deltas]
    LLM --> SAVE[insert_complete_answer]
  end

  style RET_FP fill:#d4edda
  style FAST_OUT fill:#d4edda
  style EXIT_NC fill:#f8d7da
  style EXIT_EMPTY fill:#f8d7da
```

---

## Routing (`heuristic_route`)

```mermaid
flowchart LR
    Q[User question] --> H{heuristic_route}
    H -->|preset chips / mortgage payment| FP[fast_path]
    H -->|1099, W-2, find document, mortgage statement…| RO[rag_only]
    H -->|matur, CD, bill, obligation, account, how much…| SD[structured_data]
    H -->|no match| RAG[rag default]
```

| Route | Typical intent | Retrieval | Tools / layer2 |
|-------|----------------|-----------|----------------|
| `fast_path` | Preset questions, mortgage payment math | Skipped if answer found | Skipped on early exit |
| `rag_only` | Document search / tax forms | Yes (if `use_rag`) | Yes |
| `structured_data` | CDs, bills, accounts, summaries | Often skipped when DB/tools suffice | Yes |
| `rag` | General fallback | Yes (if `use_rag`) | Yes |

---

## Streaming progress phases (`/ask/stream`)

```mermaid
flowchart LR
    P0["phase: routing"] --> P1["phase: tools"]
    P1 --> P2["phase: searching"]
    P2 --> P3["phase: generating"]
    P3 --> P4["top_chunks + deltas + done"]
```

Fast-path and no-context exits skip the LLM `generating` phase.

---

## Tool subgraph (`run_ask_tools`)

```mermaid
flowchart TD
    T0[select_tools_for_question] --> T1{ASK_TOOLS_ENABLED?}
    T1 -->|no| SKIP[empty tool_block]
    T1 -->|yes| PAT[Regex match on question]
    PAT --> EXEC[execute_tool × N<br/>get_positions, get_obligations,<br/>liquidity_cross_check, search_documents, …]
    EXEC --> FMT[format_tool_results → tool_block]
```

Tools are **local DB / finance logic only** — no external MCP calls in this router.

---

## End-to-end sequence (typical RAG path)

```mermaid
sequenceDiagram
    participant Client
    participant API as main.py
    participant Graph as build_prompt_and_chunks
    participant DB as SQLite/Postgres
    participant Embed as embeddings_client
    participant LLM as llm_client

    Client->>API: POST /ask/stream
    API->>Graph: build_prompt_and_chunks
    Graph->>Graph: heuristic_route → rag
    Graph->>DB: layer2 + tools
    Graph->>Embed: embed_text(retrieval_query)
    Graph->>DB: retrieve_top_k
    Graph-->>API: messages, chunks, has_context=true
    API->>LLM: answer_with_messages (stream)
    LLM-->>Client: NDJSON deltas + done
```

---

## Conceptual state shape (not LangGraph)

| Field | Set by |
|-------|--------|
| `question`, `scoped_request`, `prior_turns` | Input + conversation |
| `route` | `heuristic_route` |
| `direct_answer` | `try_fast_path_answer` |
| `layer2`, `tool_block`, `tool_results` | DB summary + tools |
| `top_chunks` | Retrieval |
| `related_documents` | `detect_related_documents` |
| `messages`, `has_context` | Prompt build / gates |

There is no shared mutable graph state object today — each step uses local variables inside `build_prompt_and_chunks`.

---

## Key source files

| File | Role |
|------|------|
| `app/ask_graph.py` | Prep pipeline: routing, fast paths, retrieval gate, prompt build |
| `app/main.py` | `/ask`, `/ask/stream` — LLM call, streaming, history |
| `app/ask_tool_router.py` | Heuristic tool selection and execution |
| `app/ask_fast_paths.py` | Deterministic preset answers (0 LLM) |
| `app/ask_conversation.py` | Doc scope inheritance, prior turns, retrieval query expansion |
| `app/retrieval.py` | Vector search, optional rerank, retrieval boost |
