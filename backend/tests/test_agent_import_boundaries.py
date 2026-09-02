from __future__ import annotations

import subprocess
import sys
import textwrap
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.agents import shared


class AgentImportBoundaryTests(unittest.TestCase):
    def test_runtime_manifests_exclude_evaluation_only_pyarrow_stack(self) -> None:
        backend_root = Path(__file__).resolve().parents[1]
        runtime_text = "\n".join(
            (backend_root / filename).read_text(encoding="utf-8")
            for filename in (
                "requirements.txt",
                "requirements-chat.txt",
                "requirements-ingestion.txt",
            )
        ).casefold()
        evaluation_text = (
            backend_root / "requirements-evaluation.txt"
        ).read_text(encoding="utf-8").casefold()

        self.assertNotIn("pyarrow==", runtime_text)
        self.assertNotIn("datasets==", runtime_text)
        self.assertNotIn("ragas==", runtime_text)
        self.assertIn("pyarrow==", evaluation_text)
        self.assertIn("datasets==", evaluation_text)
        self.assertIn("ragas==", evaluation_text)

    def test_graph_import_does_not_load_ingestion_or_reranking_stacks(self) -> None:
        backend_root = Path(__file__).resolve().parents[1]
        script = textwrap.dedent(
            """
            import sys

            from app.agents import graph

            compiled = graph.build_graph()
            if compiled is None:
                raise AssertionError("graph compilation returned None")

            forbidden_roots = {
                "pandas",
                "pyarrow",
                "sentence_transformers",
                "sklearn",
            }
            loaded_roots = {name.partition(".")[0] for name in sys.modules}
            violations = sorted(forbidden_roots & loaded_roots)
            forbidden_services = {
                "app.services.retrieval.neo4j_retrieval_service",
                "app.services.retrieval.retrieval_service",
                "app.services.retrieval.user_document_retrieval_service",
            }
            violations.extend(sorted(forbidden_services & set(sys.modules)))
            if violations:
                raise AssertionError(f"eager graph imports detected: {violations}")
            """
        )

        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=backend_root,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )

        self.assertEqual(
            completed.returncode,
            0,
            completed.stdout + completed.stderr,
        )

    def test_backend_factory_imports_only_pinecone_when_configured(self) -> None:
        expected = object()
        pinecone_module = SimpleNamespace(RetrievalService=lambda: expected)

        with (
            patch.object(shared.settings, "RETRIEVAL_BACKEND", "pinecone"),
            patch.dict(
                sys.modules,
                {
                    "app.services.retrieval.retrieval_service": pinecone_module,
                },
            ),
        ):
            actual = shared._build_retrieval_service()

        self.assertIs(actual, expected)

    def test_backend_factory_imports_only_neo4j_when_configured(self) -> None:
        expected = object()
        neo4j_module = SimpleNamespace(get_neo4j_retrieval_service=lambda: expected)

        with (
            patch.object(shared.settings, "RETRIEVAL_BACKEND", "neo4j"),
            patch.dict(
                sys.modules,
                {
                    "app.services.retrieval.neo4j_retrieval_service": neo4j_module,
                },
            ),
        ):
            actual = shared._build_retrieval_service()

        self.assertIs(actual, expected)


if __name__ == "__main__":
    unittest.main()
