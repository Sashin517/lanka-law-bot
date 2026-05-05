from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class IntentRoute(str, Enum):
    QUICK_QA = "quick_qa"
    DEEP_RESEARCH = "deep_research"
    DRAFTING = "drafting"
    REVIEW = "review"
    REASONING = "reasoning"
    UNSUPPORTED = "unsupported"


class LegalTaskType(str, Enum):
    QA = "qa"
    RESEARCH = "research"
    DRAFTING = "drafting"
    REVIEW = "review"
    REASONING = "reasoning"
    UNSUPPORTED = "unsupported"


class TargetCorpus(str, Enum):
    ACTS = "acts"
    CASE_LAW = "case_law"
    BOTH = "both"
    TEMPLATES = "templates"
    USER_DOCUMENT = "user_document"
    NONE = "none"


class AnswerMode(str, Enum):
    DIRECT_ANSWER = "direct_answer"
    RESEARCH_MEMO = "research_memo"
    DRAFT = "draft"
    CHECKLIST = "checklist"
    ISSUE_ANALYSIS = "issue_analysis"
    REVIEW_REPORT = "review_report"
    CLARIFICATION = "clarification"
    UNSUPPORTED = "unsupported"


class RetrievalDepth(str, Enum):
    NONE = "none"
    FAST = "fast"
    EXPANDED = "expanded"
    ITERATIVE = "iterative"


class RouteConfidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class LegalQueryEntities(BaseModel):
    act_names: list[str] = Field(default_factory=list)
    section_refs: list[str] = Field(default_factory=list)
    case_names: list[str] = Field(default_factory=list)
    court_names: list[str] = Field(default_factory=list)
    legal_domains: list[str] = Field(default_factory=list)
    document_types: list[str] = Field(default_factory=list)
    party_names: list[str] = Field(default_factory=list)
    dates: list[str] = Field(default_factory=list)
    jurisdiction: str | None = None


class IntentRoutePlan(BaseModel):
    raw_query: str = Field(min_length=1)
    normalized_query: str = Field(min_length=1)
    route: IntentRoute
    task_type: LegalTaskType
    target_corpus: TargetCorpus
    answer_mode: AnswerMode
    retrieval_depth: RetrievalDepth
    entities: LegalQueryEntities = Field(default_factory=LegalQueryEntities)
    requires_user_document: bool = False
    requires_template: bool = False
    needs_clarification: bool = False
    clarification_question: str | None = None
    confidence: RouteConfidence = RouteConfidence.MEDIUM
    routing_reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_route_consistency(self) -> "IntentRoutePlan":
        if self.needs_clarification and not self.clarification_question:
            raise ValueError("clarification_question is required when clarification is needed")

        if self.route == IntentRoute.REVIEW and not self.requires_user_document:
            raise ValueError("review route requires requires_user_document=true")

        if self.route == IntentRoute.UNSUPPORTED:
            if self.target_corpus != TargetCorpus.NONE:
                raise ValueError("unsupported route requires target_corpus=none")
            if self.retrieval_depth != RetrievalDepth.NONE:
                raise ValueError("unsupported route requires retrieval_depth=none")

        return self


class RouterResult(BaseModel):
    plan: IntentRoutePlan
    source: Literal["llm", "fallback_rules", "default_fallback"]
    raw_llm_output: dict | None = None
    parse_error: str | None = None
