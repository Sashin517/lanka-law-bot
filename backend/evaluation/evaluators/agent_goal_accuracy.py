"""Agent goal accuracy evaluator — LLM-as-judge for pipeline goal achievement.

Adapted from RAGAS ``AgentGoalAccuracyWithReference``.  Uses an LLM to
judge whether the multi-agent pipeline's final output achieved the
user's intent, considering the full execution trace.

Scoring: 0.0-1.0 continuous score via Gemini judge.

Provides both a standalone function (for backend_comparison.py) and a
LangSmith-compatible evaluator wrapper (for run_evaluation.py).
"""

from __future__ import annotations

import logging
import os
import re
import time

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate

logger = logging.getLogger(__name__)

_GEMINI_MODEL_NAME = "gemini-3.1-flash-lite-preview"
_MAX_RETRIES = 5

_GOAL_ACCURACY_PROMPT = PromptTemplate.from_template(
    """You are evaluating a multi-agent legal AI assistant pipeline.

The user's query was processed through a pipeline of specialized agents.
Your task is to judge whether the final output achieves the user's goal.

## User Query
{question}

## Query Mode
{mode}

## Pipeline Execution
Agents used: {agents_executed}
Plan type: {plan_type}

## Final Output
{response}

## Ground Truth (Expected Answer)
{ground_truth}

## Evaluation Criteria

Score the goal achievement from 0.0 to 1.0:
- 1.0 = Goal fully achieved: response correctly addresses the user's intent
        with appropriate legal content, proper citations, and the right format
        (e.g., draft for drafting, analysis for reasoning)
- 0.7 = Goal mostly achieved: core intent met but minor gaps
        (e.g., missing a secondary legal provision, slight format issue)
- 0.4 = Goal partially achieved: addresses the topic but misses key elements
        or uses wrong approach (e.g., simple answer when analysis was needed)
- 0.0 = Goal not achieved: irrelevant, empty, or fundamentally wrong response

Respond with ONLY a decimal number between 0.0 and 1.0.
"""
)


def _safe_parse_score(raw_content) -> float:
    """Extract a float score from LLM response content."""
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

    try:
        score = float(text)
    except ValueError:
        match = re.search(r'\b(0(?:\.\d+)?|1(?:\.0+)?)\b', text)
        if not match:
            logger.warning("Could not parse goal accuracy score from: %s", text[:100])
            return 0.0
        score = float(match.group(1))

    return max(0.0, min(1.0, score))


def agent_goal_accuracy_evaluator(
    question: str,
    mode: str,
    response: str,
    ground_truth: str,
    execution_trace: dict | None = None,
) -> dict:
    """LLM-as-judge: Did the agent pipeline achieve the user's goal?

    Parameters
    ----------
    question : str
        The user's original query.
    mode : str
        The query mode (quick_qa, deep_research, etc.).
    response : str
        The system's final response text.
    ground_truth : str
        The expected answer from the benchmark.
    execution_trace : dict | None
        The execution trace with plan_type and steps_executed.

    Returns
    -------
    dict
        Keys: ``goal_accuracy``, ``comment``.
    """
    if not response or "temporarily unavailable" in response.lower():
        return {
            "goal_accuracy": 0.0,
            "comment": "Empty or error response",
        }

    trace = execution_trace or {}
    plan_type = trace.get("plan_type", "unknown")
    steps = trace.get("steps_executed", [])
    agents_str = " → ".join(s.get("agent", "?") for s in steps) or "unknown"

    llm = ChatGoogleGenerativeAI(
        model=_GEMINI_MODEL_NAME,
        temperature=0,
        google_api_key=os.environ.get("GOOGLE_API_KEY"),
    )
    chain = _GOAL_ACCURACY_PROMPT | llm

    for attempt in range(_MAX_RETRIES):
        try:
            result = chain.invoke(
                {
                    "question": question,
                    "mode": mode,
                    "agents_executed": agents_str,
                    "plan_type": plan_type,
                    "response": response[:8000],
                    "ground_truth": ground_truth[:4000],
                }
            )
            score = _safe_parse_score(result.content)
            return {
                "goal_accuracy": score,
                "comment": f"plan_type={plan_type} agents={agents_str}",
            }
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e) or "Server disconnected" in str(e):
                wait = 15 * (2 ** attempt)
                logger.info("Goal accuracy rate-limited on attempt %d, waiting %ds", attempt + 1, wait)
                time.sleep(wait)
                continue
            logger.warning("Goal accuracy scoring failed on attempt %d: %s", attempt + 1, e)
            wait = 5 * (2 ** attempt)
            time.sleep(wait)
            continue

    logger.warning("Goal accuracy scoring exhausted retries")
    return {"goal_accuracy": 0.0, "comment": "Rate limit exhausted"}


# ── LangSmith-compatible evaluator wrapper ──────────────────────────


def agent_goal_accuracy_langsmith_evaluator(run, example):
    """LangSmith evaluator wrapper for agent goal accuracy.

    Extracts the necessary fields from the LangSmith run/example objects
    and delegates to the core evaluator function.  Uses ``markdown_content``
    (full response) instead of ``answer`` (truncated summary).
    """
    category = example.outputs.get("category", "")
    if category == "clarification":
        return {"key": "agent_goal_accuracy", "score": None, "comment": "Skipped for clarification"}

    question = example.inputs.get("question", "")
    mode = example.inputs.get("mode", "quick_qa")
    ground_truth = example.outputs.get("expected_answer", "")

    if not ground_truth:
        return {"key": "agent_goal_accuracy", "score": None, "comment": "No ground truth"}

    # Use markdown_content (full response) instead of answer (summary/first paragraph)
    response = (
        run.outputs.get("markdown_content", "")
        or run.outputs.get("answer", "")
    )

    execution_trace = run.outputs.get("execution_trace", {})

    result = agent_goal_accuracy_evaluator(
        question=question,
        mode=mode,
        response=response,
        ground_truth=ground_truth,
        execution_trace=execution_trace,
    )

    return {
        "key": "agent_goal_accuracy",
        "score": result["goal_accuracy"],
        "comment": result.get("comment", ""),
    }
