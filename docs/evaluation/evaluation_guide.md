# LankaLawBot Evaluation Guide

This guide describes how to evaluate the current LankaLawBot implementation. It documents the active FastAPI + LangGraph multi-agent system, legal/user-document retrieval, grounding verification, and the existing LangSmith evaluation script.

## 1. Current System Under Test

### Runtime Flow

The primary API path is:

```text
POST /api/search
  -> LangGraph router
  -> worker node
  -> grounding verifier
  -> formatter
  -> JSON response
```

The request body is defined by `LegalQuery`:

```json
{
  "question": "What is the definition of premises under the Rent Act?",
  "document_ids": [],
  "matter_id": null,
  "doc_type": null,
  "start_year": null
}
```

The current endpoint uses `question`, `document_ids`, and `matter_id` to build the graph state. `doc_type` and `start_year` exist on the request schema but are not currently consumed by `/api/search`.

### Graph Nodes

| Node | Role | Evaluation Focus |
|---|---|---|
| `router` | Classifies intent and builds retrieval plan | Route accuracy, clarification behavior |
| `quick_qa` | Fast single-pass legal QA | Direct correctness, source precision |
| `deep_research` | Decomposes complex questions and synthesizes a memo | Multi-hop completeness, source coverage |
| `reasoning` | Applies law to facts using IRAC-style analysis | Issue spotting, rule application |
| `drafting` | Generates template-aware legal drafts | Draft usability, template fit |
| `review` | Reviews uploaded user documents against legal sources | Risk identification, `[DOC-*]` citation quality |
| `verify` | Fact-checks explicit citation/legal-claim verification requests | Verdict correctness |
| `grounding` | LLM-as-judge faithfulness gate with retry/fallback | Groundedness, hallucination handling |
| `formatter` | Builds the final API response | Response contract stability |
| `unsupported` | Handles out-of-scope queries | Correct rejection, no-source behavior |

Unsupported responses skip grounding and go directly to `formatter`.

### Public Response Contract

The formatter returns:

```json
{
  "route": {
    "route": "quick_qa",
    "task_type": "qa",
    "answer_mode": "direct_answer",
    "target_corpus": "acts",
    "confidence": "high",
    "needs_clarification": false,
    "clarification_question": null,
    "routing_reason": "The query asks for a direct statutory definition."
  },
  "answer": "Plain-text fallback answer.",
  "markdown_content": "Markdown answer rendered by the frontend.",
  "sources": [],
  "confidence": "medium",
  "grounding_score": 0.92,
  "disclaimer": "This information is for research purposes only..."
}
```

Evaluate `markdown_content` as the primary generated answer, `answer` as the plain-text summary/fallback, `sources` as the citation list, and `grounding_score` as the current faithfulness signal.

## 2. Architecture-Specific Metrics

| Component | Current Implementation | Primary Metrics |
|---|---|---|
| Intent routing | LLM-first semantic router with fallback rules | Route accuracy, macro F1, clarification accuracy |
| Legal retrieval | Chroma legal corpus with dense retrieval, BM25, ensemble fusion, cross-encoder reranking, parent expansion | Hit rate, MRR, NDCG@k, context precision/recall |
| User-document retrieval | Qdrant user-doc corpus with Voyage embeddings, BM25 over selected documents, reciprocal rank fusion, reranking, parent expansion | Clause recall, source precision, document-grounding accuracy |
| Quick QA | Single-pass retrieval plus markdown/JSON generation | Answer correctness, citation precision, grounding score |
| Deep research | Query decomposition, parallel retrieval, synthesis | Completeness, multi-source coverage, information integration |
| Reasoning | Expanded retrieval and IRAC-style analysis | Issue spotting, rule quality, application quality |
| Drafting | Template-aware generation for contracts, pleadings, notices, affidavits | Template fit, completeness, placeholder handling, legal caution |
| Review | User document retrieval plus legal cross-reference | Risk identification, clause citation accuracy, legal-source support |
| Verify | Targeted retrieval and claim comparison | Confirm/partial/unconfirmed verdict accuracy |
| Grounding verifier | LLM judge with retry and fallback | Grounding pass rate, retry success rate, hallucination reduction |

## 3. Benchmark Dataset Requirements

Use the repo guide at `docs/evaluation/golden_dataset_guide.md` as the schema and construction reference.

Minimum useful benchmark:

| Category | Recommended Minimum | Full Benchmark Target |
|---|---:|---:|
| Quick QA | 5 | 20 |
| Deep research | 4 | 15 |
| Reasoning | 4 | 15 |
| Drafting | 3 | 10 |
| Review with uploaded documents | 3 | 10 |
| Verify | 3 | 10 |
| Clarification | 1 | 8 |
| Unsupported | 2 | 8 |
| Edge cases | 0-1 | 4 |

Each item should include:

- Exact `/api/search` request payload.
- Expected route metadata.
- Human-written ground truth answer or behavior assertion.
- Expected legal/user-document sources.
- `expected_grounding_min`.
- User-document fixture metadata when `document_ids` are required.

For LangSmith evaluation with the current script, every dataset example must provide:

```json
{
  "inputs": {
    "question": "What is the definition of premises under the Rent Act?"
  },
  "outputs": {
    "expected_answer": "Human-written verified answer."
  }
}
```

The existing script only reads `inputs.question` and `outputs.expected_answer`.

## 4. LangSmith Evaluation

The repo currently includes `backend/scripts/evaluate.py`. It runs a LangSmith dataset through `process_query_with_route()` and scores factual correctness with a Gemini judge.

### Environment

Set the normal Google API key and LangSmith variables in `backend/.env` or the shell:

```env
GOOGLE_API_KEY=...
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=...
LANGCHAIN_PROJECT=lankalawbot-evaluation
```

### Dataset Shape

Create a LangSmith dataset where:

- `inputs.question` is the user query.
- `outputs.expected_answer` is the human ground truth.

The current script returns only:

```json
{
  "answer": "response.summary"
}
```

That means the built-in script evaluates summary correctness only. Route metadata, sources, markdown, and grounding score require either manual inspection in traces or a future script extension.

### Run

From `backend/`:

```bash
python scripts/evaluate.py --dataset lankalawbot-legal-benchmark-v1
```

The script uses:

- Target function: `process_query_with_route(question)`.
- Judge model: `gemini-2.0-flash`.
- Evaluator key: `correctness`.
- Concurrency: `max_concurrency=2`.

### Recommended LangSmith Additions

When extending the script, add evaluators for:

| Evaluator | Required Output |
|---|---|
| Route accuracy | `route.route`, `route.task_type`, `route.answer_mode`, `route.target_corpus` |
| Citation accuracy | `sources[].title`, `sources[].section`, `sources[].source_type` |
| Grounding threshold | `grounding_score >= expected_grounding_min` |
| Clarification behavior | `route.needs_clarification` and `route.clarification_question` |
| Unsupported behavior | `route.route == unsupported`, no sources, scope response |

## 5. Manual Evaluation Rubrics

### Answer Quality

| Score | Meaning |
|---:|---|
| 5 | Fully correct, complete, and grounded in cited sources |
| 4 | Correct with minor omissions |
| 3 | Mostly correct but incomplete or weakly supported |
| 2 | Contains material omissions or questionable legal application |
| 1 | Incorrect, hallucinated, or unsupported |

### Routing

| Score | Meaning |
|---:|---|
| 1 | Expected route metadata matches |
| 0 | Wrong public route or missing required clarification |

For nuanced cases, record the observed route and reviewer comment rather than forcing a binary judgment.

### Citation Quality

| Score | Meaning |
|---:|---|
| 5 | Every important legal/document claim has a correct source |
| 4 | Minor citation omissions, no wrong citations |
| 3 | Some relevant citations but incomplete support |
| 2 | Weak, vague, or partially mismatched citations |
| 1 | Wrong or hallucinated citations |

### Drafting

Score drafting outputs on:

- Correct document family: contract, pleading, notice, or affidavit.
- Usable markdown structure.
- Required placeholders for missing facts.
- Legally cautious wording.
- Appropriate legal citations only when sources are retrieved.

### Review

Score review outputs on:

- Whether actual uploaded-document clauses are cited with `[DOC-*]`.
- Whether legal assertions are supported with `[LAW-*]`.
- Whether risks are concrete and actionable.
- Whether the system avoids inventing document terms.

## 6. Automated Metrics

### Retrieval Metrics

Use retrieval metrics where expected source IDs, titles, or sections are known:

| Metric | Applies To | Notes |
|---|---|---|
| Hit Rate@k | Legal and user-document retrieval | Did any expected source appear? |
| MRR | Legal retrieval | Rewards ranking expected source early |
| NDCG@k | Reranking studies | Useful when relevance has graded labels |
| Context Precision | RAG quality | How much retrieved context is relevant |
| Context Recall | RAG quality | Whether all needed sources were retrieved |

### Generation Metrics

| Metric | Applies To |
|---|---|
| Correctness | Quick QA, deep research, verify |
| Completeness | Deep research, reasoning |
| Faithfulness / groundedness | All generated answers |
| Citation precision | All cited legal claims |
| Clarification accuracy | Ambiguous and missing-document cases |
| Unsupported rejection rate | Unsupported category |

### RAGAS

RAGAS is useful for future automated RAG scoring, but it is not currently installed in `backend/requirements.txt` and there is no repo RAGAS runner. Treat RAGAS as optional until a dependency and script are added.

If added later, start with:

- Faithfulness.
- Answer relevancy.
- Context precision.
- Context recall.
- Answer correctness with curated references.

Use `markdown_content` as the generated response and retrieved source excerpts as contexts.

## 7. Ablation Studies

Ablations should map to current config or code paths.

| Experiment | Current Lever | Hypothesis |
|---|---|---|
| Full pipeline | Default config | Baseline |
| Dense only | Disable or bypass BM25 in legal retrieval | Hybrid retrieval should improve recall |
| Sparse only | Disable dense retrieval | Dense retrieval should improve semantic matching |
| No reranking | Bypass `RERANKER_MODEL` / cross-encoder compression | Reranking should improve top-k precision |
| No parent expansion | Set `expand_parents=False` in retrieval calls | Parent context should improve completeness |
| Legal top-k tuning | Vary `legal_top_k`, `RETRIEVAL_CANDIDATES_K`, `RERANKER_TOP_N` | Larger pools may improve recall but increase latency |
| Weight tuning | Vary `DENSE_WEIGHT=0.6`, `SPARSE_WEIGHT=0.4` | Best balance may differ by query type |
| Grounding disabled | Skip grounding node in an experimental graph | Grounding should reduce unsupported claims |
| Router fallback only | Set `ROUTER_ENABLE_LLM=false` | LLM router should improve difficult routing |
| User-doc retrieval variants | Compare Qdrant dense only, BM25 only, and fused retrieval | Hybrid should improve clause recall |

Recommended ablation table:

| Configuration | Correctness | Context Precision | Context Recall | Citation Quality | Grounding Pass Rate | Latency P95 |
|---|---:|---:|---:|---:|---:|---:|
| Full pipeline | | | | | | |
| Dense only | | | | | | |
| Sparse only | | | | | | |
| No reranking | | | | | | |
| No parent expansion | | | | | | |
| Router fallback only | | | | | | |

Keep ablation changes isolated and record exact config values for reproducibility.

## 8. Performance Evaluation

Measure latency by stage where possible:

| Stage | What To Capture |
|---|---|
| Router | Classification latency and fallback rate |
| Legal retrieval | Chroma dense/BM25/rerank total time |
| User-document retrieval | Qdrant dense, BM25, fusion, rerank time |
| Generation | Worker LLM latency |
| Grounding | Judge LLM latency and retry count |
| Total | End-to-end `/api/search` latency |

Report:

- Mean, median, P95, and P99 latency.
- Token usage where available from provider traces.
- Number of retrieved sources.
- Retry count from grounding.
- Failure and no-result rates.

LangSmith traces are useful for stage-level inspection because the graph nodes and several services are decorated with `@traceable`.

## 9. Current Configuration Snapshot

These are the important setting names to record with every evaluation run:

| Setting | Current Default | Meaning |
|---|---:|---|
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Legal corpus embedding model |
| `CHROMA_PATH` | `backend/database/chroma_db` | Legal vector store path |
| `RETRIEVAL_CANDIDATES_K` | `15` | Initial legal retrieval candidate count |
| `DENSE_WEIGHT` | `0.6` | Dense retrieval ensemble weight |
| `SPARSE_WEIGHT` | `0.4` | BM25 retrieval ensemble weight |
| `RERANKER_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Cross-encoder reranker |
| `RERANKER_TOP_N` | `5` | Legal reranker output count |
| `RELEVANCE_SCORE_THRESHOLD` | `0.0` | Low-score pruning threshold |
| `PARENT_CHUNK_SIZE` | `2000` | Legal parent chunk size |
| `PARENT_CHUNK_OVERLAP` | `200` | Legal parent chunk overlap |
| `CHILD_CHUNK_SIZE` | `500` | Legal child chunk size |
| `CHILD_CHUNK_OVERLAP` | `100` | Legal child chunk overlap |
| `QDRANT_COLLECTION_USER_DOCS` | `user_documents` | User-document vector collection |
| `VOYAGE_EMBEDDING_MODEL` | `voyage-law-2` | User-document embedding model |
| `USER_PARENT_CHUNK_SIZE` | `2200` | User-document parent chunk size |
| `USER_CHILD_CHUNK_SIZE` | `550` | User-document child chunk size |
| `USER_DOC_RERANKER_TOP_N` | `8` | User-document reranker output count |
| `LLM_MODEL_NAME` | `gemini-3.1-flash-lite-preview` | Main generation/router model default |
| `LLM_TEMPERATURE` | `0.1` | Worker generation temperature |
| `LLM_MAX_TOKENS` | `2048` | Worker generation token limit |
| `ROUTER_ENABLE_LLM` | `true` | Whether semantic router uses LLM |
| `ROUTER_TEMPERATURE` | `0.0` | Router temperature |
| `ROUTER_MAX_TOKENS` | `1024` | Router token limit |

Because settings can be overridden through `.env`, always record actual runtime values in experiment notes.

## 10. Reporting Template

Use this structure for project reports or papers:

```text
RQ1: Does the current hybrid retrieval pipeline improve source recall?
Report Hit Rate@k, MRR, Context Recall, and latency for full, dense-only, sparse-only, and no-rerank variants.

RQ2: Does grounding verification reduce unsupported legal claims?
Report grounding pass rate, retry success rate, citation quality, and human faithfulness scores with and without grounding.

RQ3: Does the multi-agent route design improve task-specific quality?
Report route accuracy, correctness by route, and qualitative examples for quick QA, research, reasoning, drafting, review, and verify.

RQ4: Can the system reliably use uploaded user documents?
Report review risk-identification scores, [DOC-*] citation precision, and user-document retrieval hit rate.
```

For each result table:

- State benchmark version.
- State config snapshot.
- State model names.
- Report sample count per category.
- Include confidence intervals or standard deviation when running repeated trials.
- Include limitations, especially missing corpus coverage and evaluator-LLM bias.

## 11. Minimum Viable Evaluation Plan

If time is limited:

| Priority | Task | Output |
|---|---|---|
| P0 | Build 25-question smoke benchmark | Curated JSON or LangSmith dataset |
| P0 | Run current LangSmith correctness script | Correctness score and traces |
| P0 | Manually score route accuracy and citation quality | Per-category spreadsheet |
| P1 | Add 3 ablations: dense-only, no rerank, no grounding | Comparison table |
| P1 | Add 3 user-document fixtures and review tests | Review/citation quality scores |
| P2 | Expand to 100-question benchmark | Publication-ready benchmark |
| P2 | Add RAGAS or custom retrieval metrics runner | Automated retrieval/generation metrics |

Do not report a single aggregate score alone. Always break results down by route/category because quick lookup, reasoning, drafting, review, and unsupported behavior measure different capabilities.
