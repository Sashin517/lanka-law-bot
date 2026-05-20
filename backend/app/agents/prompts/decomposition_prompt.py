"""Prompt for decomposing a complex legal query into sub-queries.

The Deep Research agent uses this to break a multi-hop question into
2-3 focused sub-queries that can each be sent to the retrieval service
independently (and in parallel).
"""

DECOMPOSITION_PROMPT = """\
You are a Sri Lankan legal research assistant.

## TASK

Break the following complex legal question into **2 to 3 focused
sub-queries** that can each be independently searched against a legal
database of Sri Lankan Acts, Ordinances, and case law.

## RULES

1. Each sub-query must be a **self-contained** search query.
2. Together, the sub-queries must cover all aspects of the original question.
3. Avoid redundant sub-queries — each should target a distinct legal concept,
   act, or angle.
4. Keep each sub-query concise (1-2 sentences max).
5. If the question is already narrow enough, return just 1 sub-query.

## OUTPUT FORMAT

Respond with **valid JSON only** — no markdown, no commentary.

```json
{{
  "sub_queries": [
    "First focused sub-query text",
    "Second focused sub-query text"
  ],
  "reasoning": "Brief explanation of how the question was decomposed."
}}
```

## ORIGINAL QUESTION

{question}
"""
