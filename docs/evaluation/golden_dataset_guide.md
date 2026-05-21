# Golden Dataset Construction Guide - LankaLawBot

A practical guide for building a hand-curated benchmark that matches the current LankaLawBot implementation.

The current system is a FastAPI + LangGraph legal assistant. A query is submitted to `POST /api/search`, routed by the semantic router, handled by a worker agent, checked by the grounding verifier, and formatted into a response with route metadata, markdown, sources, confidence, and a grounding score.

## 1. Current System Contract

### Query Request

Each benchmark item should be executable against `/api/search` using this request shape:

```json
{
  "question": "What does Section 36 of the Rent Act define as premises?",
  "document_ids": [],
  "matter_id": null
}
```

`question` is required. `document_ids` and `matter_id` are used for uploaded document review, drafting with user-document context, document summaries, and user-document-specific QA.

### Pipeline Flow

The primary runtime path is:

```text
/api/search
  -> LangGraph router
  -> worker node
  -> grounding verifier
  -> formatter
```

The router selects one of these public routes:

| Route | Task Type | Typical Answer Mode | Purpose |
|---|---|---|---|
| `quick_qa` | `qa` | `direct_answer` | Fast statutory lookup or narrow legal question |
| `deep_research` | `research` | `research_memo` | Multi-hop or broad legal research |
| `reasoning` | `reasoning` | `issue_analysis` | Scenario analysis using IRAC-style reasoning |
| `drafting` | `drafting` | `draft` | Template-aware legal drafting |
| `review` | `review` | `review_report` | Review uploaded user documents against law |
| `unsupported` | `unsupported` | `unsupported` | Out-of-scope or unsafe queries |

Explicit citation fact-checking requests, such as "Verify whether Section 12 of the Rent Act says X", are dispatched to the internal `verify` worker. The public route metadata may still reflect the router's classified route, so benchmark these as `category: "verify"` with explicit verification expectations rather than inventing a public `verify` route enum.

### Response Fields To Evaluate

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
  "answer": "Short plain-text fallback answer.",
  "markdown_content": "Rich markdown answer shown in the frontend.",
  "sources": [],
  "confidence": "medium",
  "grounding_score": 0.93,
  "disclaimer": "This information is for research purposes only..."
}
```

Use `markdown_content` for answer-quality evaluation, `answer` as the plain-text fallback, `route` for routing diagnostics, `sources` for citation checks, and `grounding_score` for faithfulness/grounding thresholds.

## 2. Golden Dataset Schema

Each entry should include both legal ground truth and expected system behavior.

```json
{
  "id": "SL-001",
  "question": "What is the definition of premises under the Rent Act No. 7 of 1972?",
  "category": "quick_qa",
  "difficulty": "easy",
  "request": {
    "question": "What is the definition of premises under the Rent Act No. 7 of 1972?",
    "document_ids": [],
    "matter_id": null
  },
  "expected_route": "quick_qa",
  "expected_task_type": "qa",
  "expected_answer_mode": "direct_answer",
  "expected_target_corpus": "acts",
  "expected_needs_clarification": false,
  "requires_user_document": false,
  "document_fixture": null,
  "ground_truth_answer": "Human-written answer verified against the source text.",
  "expected_sources": [
    {
      "title": "Rent Act No. 7 of 1972",
      "section": "Section 36",
      "source_type": "legal_authority"
    }
  ],
  "relevant_sections": ["Section 36"],
  "requires_multi_source": false,
  "expected_grounding_min": 0.75,
  "expected_confidence": "high",
  "tags": ["rent", "definition", "statutory_lookup"],
  "annotator": "team_member_name",
  "verified_by": "second_reviewer",
  "notes": "Ground truth must be checked against the actual source text."
}
```

Required fields:

| Field | Purpose |
|---|---|
| `id` | Stable benchmark ID such as `SL-001` |
| `question` | Human-facing query text |
| `category` | Dataset category, not necessarily identical to route |
| `request` | Exact `/api/search` payload to run |
| `expected_route` | Expected public route enum |
| `expected_task_type` | Expected router task type |
| `expected_answer_mode` | Expected answer format |
| `expected_target_corpus` | Expected corpus: `acts`, `case_law`, `both`, `templates`, `user_document`, or `none` |
| `expected_needs_clarification` | Whether the router/graph should ask for more information |
| `ground_truth_answer` | Human-written expected legal answer or behavior assertion |
| `expected_sources` | Expected legal or user-document sources |
| `expected_grounding_min` | Minimum acceptable `grounding_score` for generated answers |

For uploaded-document tests, `document_fixture` should describe the fixture file that must be uploaded before running the benchmark:

```json
{
  "document_fixture": {
    "fixture_path": "benchmarks/fixtures/sample_lease.md",
    "document_type": "lease",
    "matter_id": "lease-review-001",
    "title": "Sample Commercial Lease",
    "expected_status": "completed"
  }
}
```

## 3. Recommended 100-Question Distribution

| # | Category | Count | Expected Route | Purpose |
|---|---:|---|---|---|
| 1 | Quick QA / Simple Lookup | 20 | `quick_qa` | Direct statutory retrieval |
| 2 | Deep Research / Multi-hop | 15 | `deep_research` | Query decomposition and multi-source synthesis |
| 3 | Reasoning / Scenario | 15 | `reasoning` | Application of law to facts |
| 4 | Drafting | 10 | `drafting` | Template-aware document generation |
| 5 | Review With Uploaded Documents | 10 | `review` | User-document retrieval plus legal cross-reference |
| 6 | Verify / Citation Fact-Checking | 10 | Mixed public route, verify worker expected | Confirm, reject, or qualify legal claims |
| 7 | Ambiguous / Clarification | 8 | Usually `quick_qa`, `review`, or `reasoning` | Clarification behavior |
| 8 | Unsupported / Negative | 8 | `unsupported` | Scope and safety rejection |
| 9 | Edge Cases | 4 | Mixed | Robustness and graceful degradation |
| **Total** | | **100** | | |

Start with a smaller 25-question smoke benchmark before building the full set. A good first split is 5 quick QA, 4 deep research, 4 reasoning, 3 drafting, 3 review, 3 verify, 2 unsupported, and 1 clarification case.

## 4. Category Guidance And Examples

### 4.1 Quick QA / Simple Lookup

Use direct questions that should be answered from a small number of legal corpus chunks. These should normally route to `quick_qa`, task type `qa`, answer mode `direct_answer`, and target corpus `acts`.

```json
{
  "id": "SL-001",
  "question": "What is the definition of premises under the Rent Act No. 7 of 1972?",
  "category": "quick_qa",
  "difficulty": "easy",
  "request": {
    "question": "What is the definition of premises under the Rent Act No. 7 of 1972?",
    "document_ids": [],
    "matter_id": null
  },
  "expected_route": "quick_qa",
  "expected_task_type": "qa",
  "expected_answer_mode": "direct_answer",
  "expected_target_corpus": "acts",
  "expected_needs_clarification": false,
  "requires_user_document": false,
  "document_fixture": null,
  "ground_truth_answer": "Write the verified statutory definition here with the exact section citation.",
  "expected_sources": [
    {
      "title": "Rent Act No. 7 of 1972",
      "section": "Section 36",
      "source_type": "legal_authority"
    }
  ],
  "relevant_sections": ["Section 36"],
  "requires_multi_source": false,
  "expected_grounding_min": 0.8,
  "expected_confidence": "high",
  "tags": ["rent", "definition", "quick_qa"]
}
```

Include definitions, section content, penalties, eligibility requirements, limitation periods, and scope/applicability questions.

### 4.2 Deep Research / Multi-hop

Use questions that require decomposition into focused sub-queries or synthesis across multiple provisions. These should route to `deep_research`, task type `research`, answer mode `research_memo`, and target corpus `acts` or `both`.

```json
{
  "id": "SL-021",
  "question": "How do the Rent Act and the Civil Procedure Code interact when a landlord seeks to recover possession for non-payment of rent?",
  "category": "deep_research",
  "difficulty": "hard",
  "request": {
    "question": "How do the Rent Act and the Civil Procedure Code interact when a landlord seeks to recover possession for non-payment of rent?",
    "document_ids": [],
    "matter_id": null
  },
  "expected_route": "deep_research",
  "expected_task_type": "research",
  "expected_answer_mode": "research_memo",
  "expected_target_corpus": "acts",
  "expected_needs_clarification": false,
  "requires_user_document": false,
  "document_fixture": null,
  "ground_truth_answer": "Human synthesis across the relevant rent and procedure provisions.",
  "expected_sources": [
    {
      "title": "Rent Act No. 7 of 1972",
      "section": "Relevant possession or ejectment provisions",
      "source_type": "legal_authority"
    },
    {
      "title": "Civil Procedure Code",
      "section": "Relevant procedural provisions",
      "source_type": "legal_authority"
    }
  ],
  "relevant_sections": ["Rent Act relevant sections", "Civil Procedure Code relevant sections"],
  "requires_multi_source": true,
  "expected_grounding_min": 0.7,
  "expected_confidence": "medium",
  "tags": ["rent", "civil_procedure", "multi_source"]
}
```

Include cross-act synthesis, multi-section procedures, broad research questions, and act-plus-case-law questions where the corpus supports case law.

### 4.3 Reasoning / Scenario Analysis

Use realistic fact patterns. These should normally route to `reasoning`, task type `reasoning`, answer mode `issue_analysis`, and produce an IRAC-style analysis.

```json
{
  "id": "SL-036",
  "question": "A commercial tenant has not paid rent for six months and says the landlord's rent increase was unlawful. What legal issues should the landlord consider before seeking eviction?",
  "category": "reasoning",
  "difficulty": "hard",
  "request": {
    "question": "A commercial tenant has not paid rent for six months and says the landlord's rent increase was unlawful. What legal issues should the landlord consider before seeking eviction?",
    "document_ids": [],
    "matter_id": null
  },
  "expected_route": "reasoning",
  "expected_task_type": "reasoning",
  "expected_answer_mode": "issue_analysis",
  "expected_target_corpus": "acts",
  "expected_needs_clarification": false,
  "requires_user_document": false,
  "document_fixture": null,
  "ground_truth_answer": "Human IRAC-style answer identifying the legal issues, applicable rules, application to the facts, and practical conclusion.",
  "expected_sources": [
    {
      "title": "Rent Act No. 7 of 1972",
      "section": "Relevant rent and possession provisions",
      "source_type": "legal_authority"
    }
  ],
  "relevant_sections": ["Relevant Rent Act sections"],
  "requires_multi_source": false,
  "expected_grounding_min": 0.7,
  "expected_confidence": "medium",
  "tags": ["rent", "eviction", "scenario", "reasoning"]
}
```

Cover landlord-tenant disputes, contract enforceability, employment/labour scenarios, debt recovery, property issues, company-law scenarios, and evidence/procedure scenarios.

### 4.4 Drafting

Drafting is implemented. The drafting node selects a template from the registry using question keywords and generates markdown using legal context when available.

Supported template families are:

| Template | Common Triggers |
|---|---|
| `contract` | contract, agreement, lease, employment, service agreement |
| `pleading` | plaint, petition, answer, pleading, court filing, motion |
| `notice` | notice, demand, letter of demand, quit notice, termination notice |
| `affidavit` | affidavit, sworn statement, declaration, deposition |

```json
{
  "id": "SL-051",
  "question": "Draft a letter of demand for six months of unpaid rent for a commercial property in Kandy.",
  "category": "drafting",
  "difficulty": "medium",
  "request": {
    "question": "Draft a letter of demand for six months of unpaid rent for a commercial property in Kandy.",
    "document_ids": [],
    "matter_id": null
  },
  "expected_route": "drafting",
  "expected_task_type": "drafting",
  "expected_answer_mode": "draft",
  "expected_target_corpus": "templates",
  "expected_needs_clarification": false,
  "requires_user_document": false,
  "document_fixture": null,
  "ground_truth_answer": "[DRAFT_TEST] The system should produce a structured letter of demand in markdown, use a notice-style template, include placeholders for missing party/property details, and cite legal sources only when retrieved.",
  "expected_sources": [],
  "relevant_sections": [],
  "requires_multi_source": false,
  "expected_grounding_min": 0.5,
  "expected_confidence": "medium",
  "tags": ["drafting", "notice", "letter_of_demand", "rent"]
}
```

Evaluate drafting on structure, required placeholders, legally cautious wording, source citation discipline, and whether the output is usable markdown. Do not mark a draft wrong solely because it does not match a single wording style.

### 4.5 Review With Uploaded Documents

Review requires uploaded user documents. If no `document_ids` are attached, the router should ask for clarification: "Please upload or attach the document you want reviewed."

For review tests with documents, upload the fixture through `/api/documents/upload`, wait until the document status is `completed`, then run `/api/search` with the returned document ID.

```json
{
  "id": "SL-061",
  "question": "Review this lease agreement and identify risky clauses for the tenant.",
  "category": "review",
  "difficulty": "medium",
  "request": {
    "question": "Review this lease agreement and identify risky clauses for the tenant.",
    "document_ids": ["<uploaded_fixture_document_id>"],
    "matter_id": "lease-review-001"
  },
  "expected_route": "review",
  "expected_task_type": "review",
  "expected_answer_mode": "review_report",
  "expected_target_corpus": "user_document",
  "expected_needs_clarification": false,
  "requires_user_document": true,
  "document_fixture": {
    "fixture_path": "benchmarks/fixtures/sample_lease.md",
    "document_type": "lease",
    "matter_id": "lease-review-001",
    "title": "Sample Commercial Lease",
    "expected_status": "completed"
  },
  "ground_truth_answer": "[REVIEW_TEST] The system should identify risky clauses from the uploaded lease, explain why they matter, and cross-reference relevant Sri Lankan legal sources where available.",
  "expected_sources": [
    {
      "title": "Sample Commercial Lease",
      "section": "Relevant clause labels",
      "source_type": "user_document"
    }
  ],
  "relevant_sections": [],
  "requires_multi_source": true,
  "expected_grounding_min": 0.7,
  "expected_confidence": "medium",
  "tags": ["review", "lease", "user_document", "risk_analysis"]
}
```

Review outputs should include `[DOC-*]` sources for uploaded-document clauses and may include `[LAW-*]` sources for statutory cross-references.

### 4.6 Verify / Citation Fact-Checking

Use these to test whether the system confirms, qualifies, or rejects a legal claim against retrieved source text. The internal verify worker is triggered by phrases such as "verify", "does Section X say", "is it true", and "confirm that".

```json
{
  "id": "SL-071",
  "question": "Verify whether Section 36 of the Rent Act defines premises.",
  "category": "verify",
  "difficulty": "medium",
  "request": {
    "question": "Verify whether Section 36 of the Rent Act defines premises.",
    "document_ids": [],
    "matter_id": null
  },
  "expected_route": "quick_qa",
  "expected_task_type": "qa",
  "expected_answer_mode": "direct_answer",
  "expected_target_corpus": "acts",
  "expected_needs_clarification": false,
  "requires_user_document": false,
  "document_fixture": null,
  "ground_truth_answer": "[VERIFY_TEST] The system should produce a verification-style answer such as CONFIRMED, PARTIALLY CORRECT, or UNCONFIRMED, based only on retrieved source text.",
  "expected_sources": [
    {
      "title": "Rent Act No. 7 of 1972",
      "section": "Section 36",
      "source_type": "legal_authority"
    }
  ],
  "relevant_sections": ["Section 36"],
  "requires_multi_source": false,
  "expected_grounding_min": 0.75,
  "expected_confidence": "medium",
  "tags": ["verify", "citation_fact_check", "rent"]
}
```

Include true claims, partially true claims, wrong section references, missing-source claims, and vague citation claims.

### 4.7 Ambiguous / Clarification

Ambiguous items should test `needs_clarification` and `clarification_question`. Some broad but answerable questions may receive a general answer; use this category when clarification is the desired behavior.

```json
{
  "id": "SL-081",
  "question": "Review this contract.",
  "category": "clarification",
  "difficulty": "easy",
  "request": {
    "question": "Review this contract.",
    "document_ids": [],
    "matter_id": null
  },
  "expected_route": "review",
  "expected_task_type": "review",
  "expected_answer_mode": "review_report",
  "expected_target_corpus": "user_document",
  "expected_needs_clarification": true,
  "requires_user_document": true,
  "document_fixture": null,
  "ground_truth_answer": "[CLARIFICATION_TEST] The system should ask the user to upload or attach the document to review.",
  "expected_sources": [],
  "relevant_sections": [],
  "requires_multi_source": false,
  "expected_grounding_min": 1.0,
  "expected_confidence": "low",
  "tags": ["review", "clarification", "missing_document"]
}
```

Include missing documents, vague act references, single-word legal topics, unclear jurisdiction, and broad questions that need narrowing.

### 4.8 Unsupported / Negative

Unsupported items should route to `unsupported`, target corpus `none`, retrieval depth `none`, and no sources.

```json
{
  "id": "SL-089",
  "question": "What is the capital of France?",
  "category": "unsupported",
  "difficulty": "easy",
  "request": {
    "question": "What is the capital of France?",
    "document_ids": [],
    "matter_id": null
  },
  "expected_route": "unsupported",
  "expected_task_type": "unsupported",
  "expected_answer_mode": "unsupported",
  "expected_target_corpus": "none",
  "expected_needs_clarification": false,
  "requires_user_document": false,
  "document_fixture": null,
  "ground_truth_answer": "[REJECTION_TEST] The system should state that the query is outside the supported Sri Lankan legal research scope.",
  "expected_sources": [],
  "relevant_sections": [],
  "requires_multi_source": false,
  "expected_grounding_min": 0.0,
  "expected_confidence": "low",
  "tags": ["unsupported", "non_legal"]
}
```

Include non-legal questions, foreign-jurisdiction questions, medical or financial advice, requests to forge documents, and gibberish.

### 4.9 Edge Cases

Use edge cases sparingly. They should test graceful degradation rather than perfect answers.

Examples:

| Edge Case | Expected Behavior |
|---|---|
| Repealed or historical law not in corpus | Admit limits and cite available transitional provisions if found |
| Very old ordinances | Answer only from available sources |
| Extremely long query | Route correctly and summarize the issue |
| Misspellings | Retrieve likely intended source where possible |
| Mixed Sinhala/Tamil legal terms | Ask clarification or answer if the legal issue is clear |
| No retrieved documents | Return a low-confidence no-results response |

## 5. Source And Fixture Preparation

### Legal Corpus

The legal corpus is stored in ChromaDB and retrieved with dense search, BM25, cross-encoder reranking, deduplication, and parent expansion. Benchmark questions should be grounded in sources that actually exist in the current Chroma database.

Before finalizing a question:

1. Confirm the act, section, and title exist in the indexed corpus.
2. Verify the exact legal answer against primary source text.
3. Record expected source titles and sections in `expected_sources`.
4. Avoid relying on external law reports unless those sources are available in the local corpus.

### User-Document Fixtures

Review and user-document tests require fixture uploads. Store small, synthetic but realistic documents under a benchmark fixture directory when benchmark files are later added.

Recommended fixture types:

| Fixture Type | Use Cases |
|---|---|
| Lease agreement | Review risky clauses, summarize document, draft related notices |
| Employment contract | Review termination, non-compete, salary, leave clauses |
| Service agreement | Drafting and risk review |
| Affidavit text | Drafting and verification of structure |
| Letter of demand | Review and drafting comparisons |

For each fixture, track:

```json
{
  "fixture_path": "benchmarks/fixtures/sample_lease.md",
  "document_type": "lease",
  "matter_id": "lease-review-001",
  "title": "Sample Commercial Lease",
  "upload_endpoint": "/api/documents/upload",
  "status_endpoint": "/api/documents/{document_id}/status"
}
```

## 6. Citation And Grounding Expectations

The current system uses source anchors in assembled context:

| Source Family | Anchor Pattern | Expected `source_type` |
|---|---|---|
| Legal corpus | `[LAW-1]`, `[LAW-2]` | `legal_authority` |
| Uploaded user documents | `[DOC-1]`, `[DOC-2]` | `user_document` |

Evaluation should check:

- Cited source titles and sections match expected sources where applicable.
- User-document review includes `[DOC-*]` sources for document claims.
- Legal claims use `[LAW-*]` sources when law is cited.
- Hallucinated anchors are stripped from `markdown_content`.
- `grounding_score` is present in every response.
- Low-grounding answers either retry successfully or degrade to a cautious low-confidence answer.

For human scoring, separate citation quality into:

| Score | Meaning |
|---:|---|
| 5 | All important claims have correct, relevant citations |
| 4 | Minor citation omissions, no wrong citations |
| 3 | Some relevant citations, but incomplete support |
| 2 | Citations are weak, vague, or partially mismatched |
| 1 | Wrong or hallucinated citations |

## 7. Construction Process

### Phase 1: Inventory Sources

List the indexed legal sources and select core domains such as rent, contract, evidence, civil procedure, arbitration, sale of goods, companies, consumer protection, land/property, employment/labour, debt recovery, and eviction.

For each selected source, capture:

- Canonical title.
- Year and act number where available.
- High-value sections.
- Known definitions.
- Procedural requirements.
- Penalties and consequences.

### Phase 2: Draft Questions

For each core act or domain, write:

- 2 to 3 quick QA items.
- 1 multi-hop or deep research item.
- 1 reasoning/scenario item.

Then add:

- 10 drafting prompts across contract, pleading, notice, and affidavit templates.
- 10 review prompts with uploaded fixture documents.
- 10 verify prompts with true, false, and partially true claims.
- 8 unsupported prompts.
- 8 ambiguous/clarification prompts.
- 4 edge cases.

### Phase 3: Write Ground Truth

Every legal answer must be written by a human from primary source text.

Good ground truth answers:

- Directly answer the question.
- Cite exact sections and source titles.
- Include relevant exceptions and qualifications.
- Distinguish source-backed conclusions from practical suggestions.
- Avoid adding law that is not in the verified source material.

Use behavior assertions for non-answer categories, such as drafting, review, clarification, unsupported, and verify items.

### Phase 4: Peer Review

Each item should be checked by a second reviewer for:

- Legal accuracy.
- Correct route expectations.
- Correct source expectations.
- Natural user wording.
- No duplicate or near-duplicate question.
- Appropriate difficulty.
- Appropriate grounding threshold.

### Phase 5: Version The Benchmark

When benchmark files are later added, use a versioned structure such as:

```text
backend/evaluation/benchmarks/
  sllb_v1.0.json
  sllb_v1.0_schema.json
  fixtures/
    sample_lease.md
    sample_employment_contract.md
  README.md
```

This guide does not create those benchmark files. It defines how to build them.

## 8. Quality Checklist

Before accepting a benchmark item:

- [ ] The question sounds like something a real user would ask.
- [ ] The expected route fields match the current router contract.
- [ ] The source exists in the current legal corpus or uploaded fixture set.
- [ ] The ground truth answer was written by a human.
- [ ] Legal claims cite exact sections where possible.
- [ ] The request payload is runnable against `/api/search`.
- [ ] User-document cases include fixture metadata.
- [ ] Review cases without documents expect clarification.
- [ ] Unsupported cases expect no sources.
- [ ] Verify cases state whether the claim should be confirmed, partially correct, or unconfirmed.
- [ ] `expected_grounding_min` is realistic for the category.
- [ ] Tags identify the domain, route, and special behavior.

## 9. Evaluation Metrics By Category

| Category | Primary Metric | Secondary Metrics |
|---|---|---|
| Quick QA | Answer correctness | Source precision, grounding score |
| Deep Research | Answer completeness | Context recall, source coverage, synthesis quality |
| Reasoning | Legal reasoning quality | Issue spotting, rule application, citation support |
| Drafting | Draft usefulness | Template fit, placeholder handling, legal caution |
| Review | Risk identification | User-document citation accuracy, legal cross-reference quality |
| Verify | Verdict correctness | Citation precision, unsupported-claim handling |
| Clarification | Clarification accuracy | Whether the requested missing input is specific |
| Unsupported | Rejection accuracy | No-source behavior, safety wording |
| Edge Cases | Graceful degradation | Honest limits, low-confidence handling |

## 10. Starter Benchmark Template

```json
{
  "benchmark_id": "SLLB-2026-v1.0",
  "metadata": {
    "name": "Sri Lankan Legal Benchmark",
    "version": "1.0",
    "created_date": "2026-05-13",
    "authors": ["Your Team"],
    "description": "Hand-curated benchmark for LankaLawBot's LangGraph legal assistant pipeline.",
    "system_under_test": {
      "api_endpoint": "/api/search",
      "pipeline": "router -> worker -> grounding -> formatter",
      "routes": ["quick_qa", "deep_research", "reasoning", "drafting", "review", "unsupported"],
      "response_fields": ["route", "answer", "markdown_content", "sources", "confidence", "grounding_score", "disclaimer"]
    },
    "category_distribution": {
      "quick_qa": 20,
      "deep_research": 15,
      "reasoning": 15,
      "drafting": 10,
      "review": 10,
      "verify": 10,
      "clarification": 8,
      "unsupported": 8,
      "edge_case": 4
    }
  },
  "questions": [
    {
      "id": "SL-001",
      "question": "...",
      "category": "quick_qa",
      "difficulty": "easy",
      "request": {
        "question": "...",
        "document_ids": [],
        "matter_id": null
      },
      "expected_route": "quick_qa",
      "expected_task_type": "qa",
      "expected_answer_mode": "direct_answer",
      "expected_target_corpus": "acts",
      "expected_needs_clarification": false,
      "requires_user_document": false,
      "document_fixture": null,
      "ground_truth_answer": "...",
      "expected_sources": [],
      "relevant_sections": [],
      "requires_multi_source": false,
      "expected_grounding_min": 0.75,
      "expected_confidence": "medium",
      "tags": [],
      "annotator": "",
      "verified_by": "",
      "notes": ""
    }
  ]
}
```

Prioritize correctness over volume. A small, well-reviewed benchmark is more useful than a large set with weak ground truth.
