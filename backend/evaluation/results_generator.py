"""Results Generator — produces thesis-ready tables from evaluation outputs.

Reads all evaluation JSON outputs (RAGAS, comparison, ablation) and
generates markdown tables formatted for direct inclusion in the thesis
Results chapter.

Usage
-----
  python -m evaluation.results_generator
  python -m evaluation.results_generator --format latex
"""

import argparse
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parent.parent
RESULTS_DIR = BACKEND_DIR / "benchmarks" / "results"


def _load_json(path: Path) -> dict | list | None:
    """Load JSON file, return None if not found."""
    if not path.exists():
        logger.warning("File not found: %s", path.name)
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _fmt(value, decimals: int = 4) -> str:
    """Format a numeric value for table display."""
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.{decimals}f}"
    return str(value)


# ── Table 5.1: Overall RAG Quality ───────────────────────────────


def generate_table_5_1(comparison: dict) -> str:
    """Table 5.1: Overall RAG Quality (RAGAS Metrics) — Pinecone vs Neo4j."""
    backends = comparison.get("backends", [])
    ragas = comparison.get("ragas_comparison", {})

    if not ragas:
        return "<!-- Table 5.1: No RAGAS comparison data available -->\n"

    # Get all metric names
    all_metrics: set[str] = set()
    for backend_data in ragas.values():
        all_metrics.update(backend_data.keys())
    metrics = sorted(all_metrics)

    lines = [
        "### Table 5.1: Overall RAG Quality (RAGAS Metrics)",
        "",
        "| Metric | " + " | ".join(b.title() for b in backends) + " | Δ |",
        "|--------|" + "|".join("--------" for _ in backends) + "|---|",
    ]

    for metric in metrics:
        vals = [ragas.get(b, {}).get(metric) for b in backends]
        row = f"| {metric} | " + " | ".join(_fmt(v) for v in vals) + " | "
        if len(vals) == 2 and all(isinstance(v, (int, float)) for v in vals if v is not None):
            if vals[0] is not None and vals[1] is not None:
                delta = vals[1] - vals[0]
                row += f"{delta:+.4f}"
            else:
                row += "—"
        else:
            row += "—"
        row += " |"
        lines.append(row)

    return "\n".join(lines) + "\n"


# ── Table 5.2: Per-Mode Quality Breakdown ────────────────────────


def generate_table_5_2(comparison: dict, backend: str = "neo4j") -> str:
    """Table 5.2: Per-Mode Quality Breakdown."""
    ragas = comparison.get("ragas_comparison", {})

    # We need per-mode data — check individual backend results
    backend_results_path = RESULTS_DIR / f"comparison_{backend}_results.json"
    backend_data = _load_json(backend_results_path)
    if not backend_data:
        return f"<!-- Table 5.2: No per-mode data for {backend} -->\n"

    per_mode = backend_data.get("ragas", {}).get("per_mode", {})
    if not per_mode:
        return f"<!-- Table 5.2: No per-mode RAGAS data for {backend} -->\n"

    # Get metric columns
    all_metrics: set[str] = set()
    for mode_data in per_mode.values():
        all_metrics.update(mode_data.keys())
    metrics = sorted(all_metrics)

    # Shorten metric names for readability
    short_names = {
        "faithfulness": "Faithful.",
        "factual_correctness(mode=f1)": "Fact. Corr.",
        "factual_correctness": "Fact. Corr.",
        "context_recall": "Ctx Recall",
        "llm_context_precision_with_reference": "Ctx Prec.",
    }

    header_names = [short_names.get(m, m[:15]) for m in metrics]

    lines = [
        f"### Table 5.2: Per-Mode Quality Breakdown ({backend.title()} Backend)",
        "",
        "| Mode | " + " | ".join(header_names) + " |",
        "|------|" + "|".join("--------" for _ in metrics) + "|",
    ]

    target_modes = ["quick_qa", "deep_research", "drafting", "reasoning", "review"]
    for mode in target_modes:
        mode_data = per_mode.get(mode, {})
        vals = [_fmt(mode_data.get(m), 3) for m in metrics]
        lines.append(f"| {mode} | " + " | ".join(vals) + " |")

    return "\n".join(lines) + "\n"


# ── Table 5.3: Multi-Hop vs Single-Hop ───────────────────────────


def generate_table_5_3(comparison: dict) -> str:
    """Table 5.3: Multi-Hop vs Single-Hop Analysis."""
    backends = comparison.get("backends", [])
    hop_data = comparison.get("hop_type_comparison", {})

    if not hop_data:
        return "<!-- Table 5.3: No hop-type comparison data -->\n"

    # Get metric columns
    all_metrics: set[str] = set()
    for backend_hops in hop_data.values():
        for hop_metrics in backend_hops.values():
            all_metrics.update(hop_metrics.keys())
    metrics = sorted(all_metrics)[:4]  # Top 4 metrics

    short_names = {
        "faithfulness": "Faithful.",
        "factual_correctness(mode=f1)": "Fact. Corr.",
        "factual_correctness": "Fact. Corr.",
        "context_recall": "Ctx Recall",
        "llm_context_precision_with_reference": "Ctx Prec.",
    }
    header_names = [short_names.get(m, m[:15]) for m in metrics]

    lines = [
        "### Table 5.3: Multi-Hop vs Single-Hop Analysis",
        "",
        "| Hop Type | Backend | " + " | ".join(header_names) + " |",
        "|----------|---------|" + "|".join("--------" for _ in metrics) + "|",
    ]

    for hop_type in ["single_hop", "multi_hop"]:
        for backend in backends:
            data = hop_data.get(backend, {}).get(hop_type, {})
            vals = [_fmt(data.get(m), 3) for m in metrics]
            lines.append(
                f"| {hop_type} | {backend.title()} | " + " | ".join(vals) + " |"
            )

    return "\n".join(lines) + "\n"


# ── Table 5.4: Multi-Agent Orchestration Metrics ─────────────────


def generate_table_5_4(comparison: dict) -> str:
    """Table 5.4: Multi-Agent Orchestration Metrics."""
    agent_data = comparison.get("agent_metrics_comparison", {})

    if not agent_data:
        return "<!-- Table 5.4: No agent metrics data -->\n"

    # Use the first available backend (or best backend)
    target_metrics = [
        ("Plan Accuracy", "plan_accuracy"),
        ("Plan Type Match Rate", "plan_type_match"),
        ("Agent Sequence F1", "agent_sequence_f1"),
        ("Agent Goal Accuracy", "goal_accuracy"),
        ("Grounding First-Pass Rate", "grounding_first_pass_rate"),
        ("Planning Appropriateness", "planning_appropriateness"),
        ("Mean E2E Latency (ms)", "mean_e2e_ms"),
        ("Mean Unique Acts Retrieved", "mean_unique_acts"),
    ]

    backends = list(agent_data.keys())

    lines = [
        "### Table 5.4: Multi-Agent Orchestration Metrics",
        "",
        "| Metric | " + " | ".join(b.title() for b in backends) + " |",
        "|--------|" + "|".join("--------" for _ in backends) + "|",
    ]

    for display_name, key in target_metrics:
        vals = [_fmt(agent_data.get(b, {}).get(key), 3) for b in backends]
        lines.append(f"| {display_name} | " + " | ".join(vals) + " |")

    return "\n".join(lines) + "\n"


# ── Table 5.5: Ablation Study Results ────────────────────────────


def generate_table_5_5() -> str:
    """Table 5.5: Ablation Study Results."""
    comparison_path = RESULTS_DIR / "ablation_comparison.json"
    comparison = _load_json(comparison_path)

    if not comparison:
        return "<!-- Table 5.5: No ablation comparison data -->\n"

    summary = comparison.get("summary", {})
    if not summary:
        return "<!-- Table 5.5: Empty ablation summary -->\n"

    target_metrics = [
        "faithfulness", "factual_correctness", "context_recall",
        "context_precision", "answer_completeness",
    ]
    short_names = {
        "faithfulness": "Faithful.",
        "factual_correctness": "Fact. Corr.",
        "context_recall": "Ctx Recall",
        "context_precision": "Ctx Prec.",
        "answer_completeness": "Complete.",
    }

    header_names = [short_names.get(m, m) for m in target_metrics]

    lines = [
        "### Table 5.5: Ablation Study Results",
        "",
        "| Configuration | " + " | ".join(header_names) + " |",
        "|--------------|" + "|".join("--------" for _ in target_metrics) + "|",
    ]

    config_order = [
        "full_pipeline", "dense_only", "sparse_only",
        "no_reranking", "no_parent_expansion", "no_citation_verify",
        "no_planning",
    ]

    baseline_metrics = summary.get("full_pipeline", {}).get("metrics", {})

    for config in config_order:
        data = summary.get(config, {})
        metrics = data.get("metrics", {})
        vals = [_fmt(metrics.get(m), 3) for m in target_metrics]
        lines.append(f"| {config} | " + " | ".join(vals) + " |")

    return "\n".join(lines) + "\n"


# ── Table 5.6: Latency Analysis ──────────────────────────────────


def generate_table_5_6(comparison: dict) -> str:
    """Table 5.6: Latency Analysis."""
    latency = comparison.get("latency_comparison", {})
    backends = comparison.get("backends", [])

    if not latency:
        return "<!-- Table 5.6: No latency data -->\n"

    lines = [
        "### Table 5.6: Latency Analysis",
        "",
        "| Component | " + " | ".join(f"{b.title()} (ms)" for b in backends) + " |",
        "|-----------|" + "|".join("--------" for _ in backends) + "|",
    ]

    for backend in backends:
        e2e = latency.get(backend, {}).get("mean_e2e_ms")
        if e2e is not None:
            lines.append(
                f"| Mean E2E | " +
                " | ".join(
                    _fmt(latency.get(b, {}).get("mean_e2e_ms"), 1)
                    for b in backends
                ) + " |"
            )
            break

    return "\n".join(lines) + "\n"


# ── Main ─────────────────────────────────────────────────────────


def generate_all_tables(output_path: Path | None = None) -> str:
    """Generate all thesis tables from available results data."""
    comparison_path = RESULTS_DIR / "backend_comparison.json"
    comparison = _load_json(comparison_path) or {}

    sections = [
        "# Thesis Results Tables\n",
        "> Auto-generated from evaluation results. "
        "Copy these tables into the Results chapter.\n",
        "---\n",
        generate_table_5_1(comparison),
        "\n---\n",
        generate_table_5_2(comparison, "neo4j"),
        "\n---\n",
        generate_table_5_3(comparison),
        "\n---\n",
        generate_table_5_4(comparison),
        "\n---\n",
        generate_table_5_5(),
        "\n---\n",
        generate_table_5_6(comparison),
    ]

    report = "\n".join(sections)

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"Results tables saved to: {output_path}")

    return report


def main():
    parser = argparse.ArgumentParser(description="Generate thesis results tables")
    parser.add_argument(
        "--output", type=str, default=None,
        help="Output path for results markdown",
    )
    args = parser.parse_args()

    output_path = (
        Path(args.output) if args.output
        else RESULTS_DIR / "thesis_results_tables.md"
    )

    report = generate_all_tables(output_path)
    print(report)


if __name__ == "__main__":
    main()
