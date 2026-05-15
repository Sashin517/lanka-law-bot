"""LLM-as-judge correctness evaluator.

Scores whether the generated answer is factually aligned with the ground truth.
Skips clarification-type entries where no substantive answer is expected.
"""

import os

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate

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


def correctness_evaluator(run, example):
    """Score 0.0-1.0: is the generated answer factually aligned with ground truth?"""
    category = example.outputs.get("category", "")

    # Skip clarification tests — they don't produce substantive answers
    if category == "clarification":
        return {"key": "correctness", "score": None, "comment": "Skipped for clarification"}

    question = example.inputs.get("question", "")
    expected_answer = example.outputs.get("expected_answer", "")
    generated_answer = run.outputs.get("answer", "")

    if not expected_answer:
        return {"key": "correctness", "score": None, "comment": "No ground truth provided"}

    if not generated_answer:
        return {"key": "correctness", "score": 0.0, "comment": "No answer generated"}

    chain = _PROMPT | _eval_llm

    # Retry with exponential backoff for rate-limit (429) errors
    import time
    max_retries = 3
    for attempt in range(max_retries):
        try:
            result = chain.invoke({
                "input": question,
                "expected": expected_answer,
                "output": generated_answer,
            })
            score = float(result.content.strip())
            score = max(0.0, min(1.0, score))
            return {"key": "correctness", "score": score}
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                wait = 15 * (2 ** attempt)  # 15s, 30s, 60s
                time.sleep(wait)
                continue
            # Non-rate-limit error — fail immediately
            return {"key": "correctness", "score": 0.0, "comment": f"LLM error: {e}"}

    return {"key": "correctness", "score": 0.0, "comment": "Rate limit exhausted after retries"}
