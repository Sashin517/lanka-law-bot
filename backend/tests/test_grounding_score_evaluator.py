"""Regression tests for persisted grounding-score evaluation semantics."""

from __future__ import annotations

from types import SimpleNamespace

from evaluation.evaluators.grounding_score import grounding_score_evaluator


def test_drafting_score_is_reported_as_a_real_judge_result() -> None:
    run = SimpleNamespace(
        outputs={
            "route": {"route": "drafting"},
            "grounding_score": 0.73,
        }
    )
    example = SimpleNamespace(outputs={"category": "drafting"})

    result = grounding_score_evaluator(run, example)

    assert result == {
        "key": "grounding_pass",
        "score": 0.73,
        "comment": "score=0.73",
    }
