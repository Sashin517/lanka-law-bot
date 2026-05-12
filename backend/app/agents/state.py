"""Shared state schema for the LankaLawBot LangGraph multi-agent system.

Every graph node reads from and writes to ``AgentState``.  The supporting
models (``SourceChunk``, ``CitedClaim``, ``GroundingResult``) mirror the
existing ``app.schemas.responses`` types but are kept separate so the
agent layer can evolve independently of the API contract.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ── Supporting data models ────────────────────────────────────────


class SourceChunk(BaseModel):
    """A single retrieved source chunk with full metadata."""

    citation_id: str = ""  # "[LAW-1]", "[DOC-2]"
    content: str = ""
    title: str = ""
    section: str | None = None
    year: int = 0
    breadcrumb: str | None = None
    excerpt: str = ""  # First ~300 chars of child text
    relevance_score: float = 0.0
    source_type: str = "legal_authority"  # "legal_authority" | "user_document"
    document_id: str | None = None
    filename: str | None = None


class CitedClaim(BaseModel):
    """A factual statement with citation anchors."""

    statement: str
    citation_ids: list[str] = Field(default_factory=list)
    is_grounded: bool = True  # Set by grounding verifier


class GroundingResult(BaseModel):
    """Output produced by the Grounding Verifier node."""

    is_grounded: bool = False
    grounding_score: float = 0.0  # 0.0 – 1.0
    ungrounded_claims: list[str] = Field(default_factory=list)
    feedback: str = ""  # Correction hints for retry


# ── Main agent state ──────────────────────────────────────────────


class AgentState(BaseModel):
    """Shared state that flows through the entire LangGraph.

    Grouped into logical sections so each node only updates the fields
    it owns while reading whatever it needs from the rest.
    """

    # ── User input ──
    question: str = ""
    document_ids: list[str] = Field(default_factory=list)
    matter_id: str | None = None
    session_id: str = ""

    # ── Router output ──
    route: str = ""  # quick_qa, deep_research, …
    task_type: str = ""
    answer_mode: str = ""
    target_corpus: str = ""
    route_confidence: str = "medium"
    needs_clarification: bool = False
    clarification_question: str | None = None
    routing_reason: str = ""
    entities: dict = Field(default_factory=dict)

    # ── Retrieval plan (built by router, consumed by workers) ──
    use_legal_corpus: bool = True
    use_user_documents: bool = False
    legal_top_k: int = 5
    user_doc_top_k: int = 6
    year_filter: int | None = None
    act_name_filter: str | None = None

    # ── Retrieval results ──
    retrieved_sources: list[SourceChunk] = Field(default_factory=list)
    context_str: str = ""
    sub_queries: list[str] = Field(default_factory=list)

    # ── Generation output ──
    summary: str = ""                             # Plain-text fallback
    markdown_content: str = ""                    # Rich markdown for frontend rendering
    analysis: list[CitedClaim] = Field(default_factory=list)
    confidence: str = "medium"
    draft_content: str = ""

    # ── Grounding ──
    grounding: GroundingResult = Field(default_factory=GroundingResult)
    retry_count: int = 0
    max_retries: int = 2

    # ── Final output ──
    final_response: dict | None = None
    disclaimer: str = (
        "This information is for research purposes only and does not "
        "constitute legal advice. Please consult a qualified legal "
        "professional for specific legal matters."
    )

    # ── Control flow ──
    current_agent: str = ""
    error: str | None = None
