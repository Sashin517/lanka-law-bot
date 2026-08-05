"""LLM-as-judge correctness evaluator.

Scores whether the generated answer is factually aligned with the ground truth.
Skips clarification-type entries where no substantive answer is expected.

Uses ``markdown_content`` (the full response) instead of ``summary`` (first
paragraph only) to give the judge the complete response for evaluation.
"""

import os
import logging
import re
import time

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate

logger = logging.getLogger(__name__)

_eval_llm = ChatGoogleGenerativeAI(
    model="gemini-3.1-flash-lite-preview",
    temperature=0,
    google_api_key=os.environ.get("GOOGLE_API_KEY"),
)

_PROMPT = PromptTemplate.from_template(
    """You are an expert legal evaluator grading a legal AI assistant's answer.

Question: {input}
Ground Truth Answer: {expected}
Generated Answer: {output}

Evaluate whether the Generated Answer captures the core legal facts and reasoning
present in the Ground Truth Answer. The answer does NOT need to be word-for-word
identical, but:
- Key legal provisions (act names, section numbers) must be correct
- The legal conclusion must be substantively aligned
- No critical legal facts should be contradicted

Score on a scale of 0.0 to 1.0:
- 1.0 = Fully correct, all key legal facts present
- 0.7 = Mostly correct, minor omissions or imprecisions
- 0.4 = Partially correct, some key facts missing or wrong
- 0.0 = Incorrect or irrelevant

Respond with ONLY a decimal number between 0.0 and 1.0.
"""
)


def _safe_parse_score(raw_content) -> float:
    """Extract a float score from LLM response content.

    Handles common response formats:
    - Plain number: '0.7'
    - With prefix: 'Score: 0.7'
    - With explanation: '0.7\\n\\nThe answer covers...'
    - List content from Gemini: [{'text': '0.7'}]
    """
    if isinstance(raw_content, list):
        parts = []
        for part in raw_content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                parts.append(part.get("text", ""))
        text = "".join(parts).strip()
    elif isinstance(raw_content, str):
        text = raw_content.strip()
    else:
        text = str(raw_content).strip()

    # Try direct float parse first
    try:
        return float(text)
    except ValueError:
        pass

    # Try to find a score-like decimal in the response
    # Match patterns like '0.7', '0.85', '1.0', also '0' and '1'
    match = re.search(r'\b(0(?:\.\d+)?|1(?:\.0+)?)\b', text)
    if match:
        return float(match.group(1))

    logger.warning("Could not parse correctness score from: %s", text[:100])
    return 0.0


def correctness_evaluator(run, example):
    """Score 0.0-1.0: is the generated answer factually aligned with ground truth?"""
    category = example.outputs.get("category", "")

    # Skip clarification tests — they don't produce substantive answers
    if category == "clarification":
        return {
            "key": "correctness",
            "score": None,
            "comment": "Skipped for clarification",
        }

    question = example.inputs.get("question", "")
    expected_answer = example.outputs.get("expected_answer", "")

    # Use markdown_content (full response) instead of summary (first paragraph).
    # Falls back to answer → summary for backward compatibility.
    generated_answer = (
        run.outputs.get("markdown_content", "")
        or run.outputs.get("answer", "")
    )

    if not expected_answer:
        return {
            "key": "correctness",
            "score": None,
            "comment": "No ground truth provided",
        }

    if not generated_answer:
        return {"key": "correctness", "score": 0.0, "comment": "No answer generated"}

    # Cap response length to avoid token overflow while still giving
    # the judge the complete meaningful content (not just first paragraph)
    generated_answer = generated_answer[:8000]

    chain = _PROMPT | _eval_llm

    # Retry with exponential backoff for rate-limit (429) errors
    max_retries = 5
    for attempt in range(max_retries):
        try:
            result = chain.invoke(
                {
                    "input": question,
                    "expected": expected_answer,
                    "output": generated_answer,
                }
            )
            score = _safe_parse_score(result.content)
            score = max(0.0, min(1.0, score))
            return {"key": "correctness", "score": score}
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e) or "Server disconnected" in str(e):
                wait = 15 * (2**attempt)  # 15s, 30s, 60s, 120s, 240s
                logger.info("Correctness rate-limited on attempt %d, waiting %ds", attempt + 1, wait)
                time.sleep(wait)
                continue
            # Other errors — warn and continue retrying (or fail if attempts exhausted)
            logger.warning("Correctness scoring failed on attempt %d: %s", attempt + 1, e)
            wait = 5 * (2**attempt)
            time.sleep(wait)
            continue

    return {
        "key": "correctness",
        "score": 0.0,
        "comment": "Rate limit exhausted after retries",
    }
