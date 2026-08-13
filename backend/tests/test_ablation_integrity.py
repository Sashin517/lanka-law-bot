from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from evaluation.ablation import (
    AblationConfigurationError,
    describe_neo4j_effects,
    describe_pinecone_effects,
    retrieval_search_kwargs,
    validate_retrieval_combination,
)
from app.services.retrieval.neo4j_queries import GRAPH_TRAVERSAL_QUERY
from evaluation.ablation_runner import (
    MetricEvaluationError,
    MetricOutcome,
    _cited_contexts,
    _invoke_completeness_judge_with_retries,
    _is_retryable_judge_error,
    add_quality_metrics,
    benchmark_identity,
    build_run_metadata,
    validate_cached_result,
)


class AblationIntegrityTests(unittest.TestCase):
    def test_graph_traversal_uses_current_hardcoded_relationship_types(self):
        self.assertIn(":CITES_STATUTE|INTERPRETS", GRAPH_TRAVERSAL_QUERY)
        self.assertIn(":CITES_CASE", GRAPH_TRAVERSAL_QUERY)
        self.assertIn(":RELATES_TO|ESTABLISHES_PRINCIPLE", GRAPH_TRAVERSAL_QUERY)
        self.assertNotIn(
            "type(amendment_rel) IN $amendment_relationship_types",
            GRAPH_TRAVERSAL_QUERY,
        )

    def test_transient_judge_disconnect_is_retryable(self):
        self.assertTrue(
            _is_retryable_judge_error(
                RuntimeError("Server disconnected without sending a response.")
            )
        )
        self.assertTrue(
            _is_retryable_judge_error(RuntimeError("503 Service Unavailable"))
        )
        self.assertFalse(
            _is_retryable_judge_error(RuntimeError("API key not valid"))
        )

    def test_completeness_judge_recovers_after_transient_disconnect(self):
        attempts = iter(
            [
                RuntimeError("Server disconnected without sending a response."),
                SimpleNamespace(content="0.8"),
            ]
        )

        def invoke():
            value = next(attempts)
            if isinstance(value, Exception):
                raise value
            return value

        with patch("evaluation.ablation_runner.time.sleep") as sleep:
            outcome = _invoke_completeness_judge_with_retries(invoke)

        self.assertEqual(outcome, MetricOutcome(value=0.8))
        sleep.assert_called_once_with(5)

    def test_retrieval_kwargs_emit_expand_parents_once_and_drop_pipeline_keys(self):
        options = retrieval_search_kwargs(
            {
                "expand_parents": False,
                "disable_dense": True,
                "skip_verification": True,
                "description": "not a retrieval option",
            }
        )
        self.assertEqual(
            options,
            {
                "expand_parents": False,
                "disable_bm25": False,
                "disable_dense": True,
                "disable_reranking": False,
            },
        )

    def test_contradictory_retrieval_ablation_is_rejected(self):
        with self.assertRaises(AblationConfigurationError):
            validate_retrieval_combination(
                {"disable_bm25": True, "disable_dense": True}
            )

    def test_pinecone_sparse_only_requires_bm25_and_never_uses_dense_fallback(self):
        with self.assertRaisesRegex(AblationConfigurationError, "sparse_only requires"):
            describe_pinecone_effects(
                {"disable_dense": True},
                bm25_available=False,
                reranking_available=False,
            )

    def test_neo4j_effect_descriptions_match_requested_ablation(self):
        self.assertEqual(
            describe_neo4j_effects({"disable_bm25": True})["retrieval_channels"],
            ["dense"],
        )
        self.assertEqual(
            describe_neo4j_effects({"disable_dense": True})["retrieval_channels"],
            ["sparse"],
        )
        self.assertFalse(
            describe_neo4j_effects({"disable_reranking": True})["reranking_enabled"]
        )

    def test_cache_metadata_rejects_a_different_benchmark(self):
        first = [{"id": "A", "question": "first"}]
        second = [{"id": "B", "question": "second"}]
        effects = {
            "backend": "pinecone",
            "retrieval_channels": ["dense", "sparse"],
        }
        first_metadata = build_run_metadata(
            benchmark_identity(first, Path("first.json")),
            "full_pipeline",
            {"description": "baseline"},
            effects,
        )
        second_metadata = build_run_metadata(
            benchmark_identity(second, Path("second.json")),
            "full_pipeline",
            {"description": "baseline"},
            effects,
        )
        cached = {
            "run_metadata": first_metadata,
            "total": 1,
            "results": [{"id": "A"}],
        }

        with self.assertRaisesRegex(ValueError, "metadata does not match"):
            validate_cached_result(cached, second_metadata)

    def test_metric_contexts_include_only_sources_cited_in_final_answer(self):
        sources = [
            {"citation_id": "[LAW-1]", "content": "cited statute"},
            {"citation_id": "[LAW-2]", "content": "retrieved but not cited"},
            {"citation_id": "[LAW-3]", "content": "also cited"},
        ]

        contexts = _cited_contexts(
            "The rule is established by [LAW-1] and qualified by [LAW-3].",
            sources,
        )

        self.assertEqual(contexts, ["cited statute", "also cited"])

    def test_evaluator_failure_is_missing_data_not_a_zero_score(self):
        result = {
            "config_name": "full_pipeline",
            "results": [
                {
                    "id": "A",
                    "mode": "quick_qa",
                    "question": "Question",
                    "ground_truth": "Reference",
                    "output": {
                        "answer": "Answer without a resolvable citation",
                        "sources": [],
                        "skipped": False,
                    },
                }
            ],
        }

        with patch(
            "evaluation.ablation_runner.score_answer_completeness",
            return_value=MetricOutcome(value=None, error="judge unavailable"),
        ):
            with self.assertRaises(MetricEvaluationError):
                add_quality_metrics(result)

        item = result["results"][0]
        self.assertIsNone(item["metrics"]["answer_completeness"])
        self.assertEqual(
            item["metric_errors"]["answer_completeness"], "judge unavailable"
        )
        self.assertEqual(result["metric_status"]["status"], "failed")

    def test_missing_citation_anchors_fall_back_to_all_source_contexts(self):
        result = {
            "config_name": "no_reranking",
            "results": [
                {
                    "id": "A",
                    "mode": "quick_qa",
                    "question": "Question",
                    "ground_truth": "Reference answer",
                    "output": {
                        "answer": "The sources do not address the question.",
                        "sources": [{"citation_id": "[LAW-1]", "content": "Law"}],
                        "skipped": False,
                    },
                }
            ],
        }

        with (
            patch(
                "evaluation.ablation_runner.score_answer_completeness",
                return_value=MetricOutcome(value=0.0),
            ),
            patch(
                "evaluation.ablation_runner._run_ragas_evaluation",
                return_value=[
                    {
                        "faithfulness": 0.2,
                        "factual_correctness(mode=f1)": 0.1,
                        "context_recall": 0.3,
                        "llm_context_precision_with_reference": 0.4,
                    }
                ],
            ) as ragas,
        ):
            scored = add_quality_metrics(result)

        metrics = scored["results"][0]["metrics"]
        self.assertEqual(metrics["faithfulness"], 0.2)
        self.assertEqual(metrics["context_recall"], 0.3)
        self.assertEqual(metrics["context_precision"], 0.4)
        self.assertEqual(metrics["factual_correctness"], 0.1)
        self.assertEqual(scored["metric_status"]["status"], "complete")
        ragas.assert_called_once_with(
            [
                {
                    "user_input": "Question",
                    "retrieved_contexts": ["Law"],
                    "response": "The sources do not address the question.",
                    "reference": "Reference answer",
                }
            ]
        )

    def test_empty_source_text_is_scored_as_zero_cited_context_metrics(self):
        result = {
            "config_name": "no_reranking",
            "results": [
                {
                    "id": "A",
                    "mode": "quick_qa",
                    "question": "Question",
                    "ground_truth": "Reference answer",
                    "output": {
                        "answer": "The sources do not address the question.",
                        "sources": [{"citation_id": "[LAW-1]"}],
                        "skipped": False,
                    },
                }
            ],
        }

        with (
            patch(
                "evaluation.ablation_runner.score_answer_completeness",
                return_value=MetricOutcome(value=0.0),
            ),
            patch(
                "evaluation.ablation_runner._run_ragas_evaluation",
                return_value=[{"factual_correctness(mode=f1)": 0.1}],
            ) as ragas,
        ):
            scored = add_quality_metrics(result)

        metrics = scored["results"][0]["metrics"]
        self.assertEqual(metrics["faithfulness"], 0.0)
        self.assertEqual(metrics["context_recall"], 0.0)
        self.assertEqual(metrics["context_precision"], 0.0)
        self.assertEqual(metrics["factual_correctness"], 0.1)
        self.assertEqual(scored["metric_status"]["status"], "complete")
        ragas.assert_called_once_with(
            [
                {
                    "user_input": "Question",
                    "retrieved_contexts": [],
                    "response": "The sources do not address the question.",
                    "reference": "Reference answer",
                }
            ],
            metric_names=("factual_correctness",),
        )

    def test_ragas_setup_failure_marks_run_failed(self):
        result = {
            "config_name": "full_pipeline",
            "results": [
                {
                    "id": "A",
                    "mode": "quick_qa",
                    "question": "Question",
                    "ground_truth": "Reference",
                    "output": {
                        "answer": "Supported answer [LAW-1]",
                        "sources": [
                            {
                                "citation_id": "[LAW-1]",
                                "content": "Supporting law",
                            }
                        ],
                        "skipped": False,
                    },
                }
            ],
        }

        with (
            patch(
                "evaluation.ablation_runner.score_answer_completeness",
                return_value=MetricOutcome(value=0.8),
            ),
            patch(
                "evaluation.ablation_runner._run_ragas_evaluation",
                side_effect=RuntimeError("RAGAS unavailable"),
            ),
        ):
            with self.assertRaises(MetricEvaluationError):
                add_quality_metrics(result)

        self.assertEqual(result["metric_status"]["status"], "failed")
        self.assertEqual(
            result["results"][0]["metric_errors"]["ragas"], "RAGAS unavailable"
        )


if __name__ == "__main__":
    unittest.main()
