"""
LankaLawBot Neo4j Ingestion Script.

Parses PDFs (Acts and Case Laws) using Docling, converts them to Markdown, extracts
regex metadata, chunks them hierarchically, generates gemini-embedding-2 vectors,
runs Gemini LLM deep relationship extraction, and builds the Neo4j Graph.

This script is designed to run either:
1. Locally within the lanka-law-bot backend repo.
2. In Google Colab (standalone mode) by falling back to inline implementations if the app module is missing.

Usage (Local):
    python scripts/ingest_to_neo4j.py --acts-dir "/path/to/acts" --cases-dir "/path/to/cases"

Usage (Colab/Remote):
    python ingest_to_neo4j.py --acts-dir "/content/acts" --cases-dir "/content/cases" --neo4j-uri "bolt://your-ngrok-or-aura-url:port" --neo4j-password "your-password" --google-api-key "AIzaSy..."
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sys
import time
import httpx
from collections import Counter
from pathlib import Path
from uuid import uuid5, NAMESPACE_URL
from typing import Any, Dict, List, Optional, Tuple

# Reset existing Jupyter/Colab logging configuration to ensure INFO logs print
root_logger = logging.getLogger()
for h in list(root_logger.handlers):
    root_logger.removeHandler(h)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("ingest_to_neo4j")
logger.setLevel(logging.INFO)
logger.info("Logging configured successfully for notebook execution.")


# Try to load docling for PDF parsing
try:
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.pipeline_options import (
        PdfPipelineOptions,
        AcceleratorOptions,
    )
    from docling.datamodel.base_models import InputFormat

    HAS_DOCLING = True
except ImportError:
    HAS_DOCLING = False

try:
    if "__file__" in globals():
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    else:
        sys.path.insert(0, os.path.abspath("."))
    from app.core.config import settings
    from app.services.ingestion.neo4j_llm_entity_extractor import (
        DeepLegalExtractionResult,
    )

    HAS_APP = True
except (ImportError, NameError):
    HAS_APP = False

    # Define fallback class matching the interface
    class DeepLegalExtractionResult:
        def __init__(
            self,
            legal_concepts: list,
            amendments: list,
            statute_citations: list,
            case_citations: list,
            is_current: bool = True,
            repealed_by: str = None,
        ):
            self.legal_concepts = legal_concepts
            self.amendments = amendments
            self.statute_citations = statute_citations
            self.case_citations = case_citations
            self.is_current = is_current
            self.repealed_by = repealed_by


# Try to load google-genai SDK
try:
    from google import genai
    from google.genai import types

    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False

# Try to load neo4j driver
try:
    from neo4j import GraphDatabase, Driver

    HAS_NEO4J = True
except ImportError:
    HAS_NEO4J = False


# ---------------------------------------------------------------------------
# Fallback Gemini Extractor (Used if HAS_APP is False or running in Colab)
# ---------------------------------------------------------------------------
class FallbackLLMEntityExtractor:
    """Fallback extractor using raw google-genai SDK directly for Colab compatibility."""

    def __init__(self, api_key: str):
        if not HAS_GENAI:
            raise ImportError(
                "The 'google-genai' package is required for LLM extraction."
            )
        self.client = genai.Client(api_key=api_key)

    def extract(self, text: str) -> DeepLegalExtractionResult:
        max_chars = 30000
        cropped_text = text
        if len(text) > max_chars:
            cropped_text = text[:20000] + "\n... [TRUNCATED] ...\n" + text[-10000:]

        prompt = f"""Analyze this Sri Lankan legal document and extract the following as a structured JSON object:
        1. "legal_concepts": List of canonical legal concepts.
           Each concept: {{"name": "...", "aliases": ["..."], "description": "..."}}
        2. "amendments": List of amendment relationships.
           Each: {{"amending_act": "...", "amended_act": "...", "sections_affected": [...], "type": "amends|repeals|partially_repeals"}}
        3. "statute_citations": List of statute sections cited.
           Each: {{"section_ref": "...", "act_name": "...", "context": "cited|interpreted|applied|distinguished"}}
        4. "case_citations": List of case citations.
           Each: {{"case_name": "...", "citation": "...", "treatment": "followed|applied|distinguished|overruled|cited"}}
        5. "is_current": boolean (false if the document is explicitly repealed/superseded).
        6. "repealed_by": string or null.

        Return ONLY raw, parseable JSON matching this schema. No markdown wrappers.
        
        Document:
        {cropped_text}
        """

        max_retries = 3
        backoff = 2.0
        for attempt in range(max_retries):
            try:
                response = self.client.models.generate_content(
                    model="gemini-3.1-flash-lite",
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json"
                    ),
                )
                data = json.loads(response.text.strip())

                # Map JSON to helper classes
                concepts = []
                for c in data.get("legal_concepts", []):
                    concepts.append(type("Concept", (), c))
                amendments = []
                for a in data.get("amendments", []):
                    amendments.append(type("Amendment", (), a))
                statutes = []
                for s in data.get("statute_citations", []):
                    statutes.append(type("Statute", (), s))
                cases = []
                for c in data.get("case_citations", []):
                    cases.append(type("Case", (), c))

                return DeepLegalExtractionResult(
                    legal_concepts=concepts,
                    amendments=amendments,
                    statute_citations=statutes,
                    case_citations=cases,
                    is_current=data.get("is_current", True),
                    repealed_by=data.get("repealed_by"),
                )
            except Exception as e:
                err_str = str(e)
                is_rate_limit = (
                    "429" in err_str
                    or "RESOURCE_EXHAUSTED" in err_str
                    or "Quota exceeded" in err_str
                )
                if attempt < max_retries - 1 and is_rate_limit:
                    logger.warning(
                        "LLM extraction rate limit hit! Retrying in %.2f seconds...",
                        backoff,
                    )
                    time.sleep(backoff)
                    backoff *= 2.0
                else:
                    logger.warning("Fallback LLM extraction failed: %s", e)
                    return DeepLegalExtractionResult([], [], [], [], True, None)
        return DeepLegalExtractionResult([], [], [], [], True, None)


# ---------------------------------------------------------------------------
# Fallback Neo4j Graph Builder (Used if HAS_APP is False or running in Colab)
# ---------------------------------------------------------------------------
def slugify(text: str) -> str:
    if not text:
        return "unknown"
    s = text.lower().strip()
    s = re.sub(r"[^a-z0-9_]", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "unknown"


def slugify_section(raw_label: str) -> str:
    if not raw_label:
        return "general"
    s = raw_label.lower().strip()
    s = re.sub(r"[()\[\]]", "_", s)
    s = re.sub(r"[^a-z0-9_]", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "general"


class FallbackGraphBuilder:
    """Constructs the Graph in Neo4j (direct Cypher execution)."""

    def __init__(self, driver: Driver, database: str = "neo4j"):
        self.driver = driver
        self.db = database

    def build_document_graph(
        self, meta: dict, chunks: list, llm: DeepLegalExtractionResult
    ):
        source_type = meta.get("source_type", "act")
        year = int(meta.get("year", 0))

        with self.driver.session(database=self.db) as session:
            # 1. Create root node
            if source_type == "case_law":
                case_name = meta.get("case_name", "unknown")
                root_id = f"case_{slugify(case_name)}_{year}"
                session.run(
                    """
                    MERGE (cl:CaseLaw {case_id: $case_id})
                    SET cl.case_name = $case_name, cl.court = $court, cl.date_decided = $date_decided,
                        cl.reporter_citation = $reporter_citation, cl.year = $year, cl.judges = $judges,
                        cl.statutes_cited = $statutes_cited, cl.source_filename = $source_filename,
                        cl.source_type = $source_type, cl.subject_area = $subject_area
                    """,
                    case_id=root_id,
                    case_name=case_name,
                    court=meta.get("court"),
                    date_decided=meta.get("date_decided"),
                    reporter_citation=meta.get("reporter_citation"),
                    year=year,
                    judges=meta.get("judges", []),
                    statutes_cited=meta.get("statutes_cited", []),
                    source_filename=meta.get("source_filename"),
                    source_type=source_type,
                    subject_area=meta.get("subject_area"),
                )
            else:
                act_num = meta.get("act_number")
                root_id = f"act_{year}_{int(act_num) if act_num is not None else 0}"
                session.run(
                    """
                    MERGE (a:Act {act_id: $act_id})
                    SET a.title = $title, a.short_title = $short_title, a.act_number = $act_number,
                        a.year = $year, a.date_certified = $date_certified, a.is_current = $is_current,
                        a.source_filename = $source_filename, a.source_type = $source_type, a.subject_area = $subject_area
                    """,
                    act_id=root_id,
                    title=meta.get("title"),
                    short_title=meta.get("short_title"),
                    act_number=meta.get("act_number"),
                    year=year,
                    date_certified=meta.get("date_certified"),
                    is_current=llm.is_current,
                    source_filename=meta.get("source_filename"),
                    source_type=source_type,
                    subject_area=meta.get("subject_area"),
                )

            # 2. Create Sections (for Acts)
            if source_type != "case_law":
                unique_sections = set(
                    c["metadata"].get("section")
                    for c in chunks
                    if c["metadata"].get("section")
                )
                for raw_sec in unique_sections:
                    sec_id = f"{root_id}_s_{slugify_section(raw_sec)}"
                    session.run(
                        """
                        MATCH (a:Act {act_id: $root_id})
                        MERGE (s:Section {section_id: $sec_id})
                        SET s.section_number = $sec_num, s.heading = $sec_num, s.act_id = $root_id
                        MERGE (a)-[:HAS_SECTION]->(s)
                        """,
                        root_id=root_id,
                        sec_id=sec_id,
                        sec_num=raw_sec,
                    )

            # 3. Create Chunks
            prepared_chunks = []
            parent_child_links = []
            for chunk in chunks:
                chunk_meta = chunk["metadata"]
                sec_label = chunk_meta.get("section") or "general"
                sec_id = f"{root_id}_s_{slugify_section(sec_label)}"
                prepared_chunks.append(
                    {
                        "chunk_id": chunk["id"],
                        "text": chunk["text"],
                        "embedding": chunk.get("embedding"),
                        "chunk_type": chunk_meta.get("chunk_type"),
                        "parent_chunk_id": chunk_meta.get("parent_id"),
                        "text_hash": chunk_meta.get("text_hash"),
                        "year": year,
                        "title": meta.get("title") or meta.get("case_name"),
                        "source_type": source_type,
                        "source_filename": meta.get("source_filename"),
                        "breadcrumb": chunk_meta.get("breadcrumb"),
                        "is_current": llm.is_current,
                        "section_id": sec_id,
                        "root_id": root_id,
                    }
                )
                if chunk_meta.get("parent_id"):
                    parent_child_links.append(
                        {"parent_id": chunk_meta["parent_id"], "child_id": chunk["id"]}
                    )

            session.run(
                """
                UNWIND $chunks AS chunk
                MERGE (c:Chunk {chunk_id: chunk.chunk_id})
                SET c.text = chunk.text, c.embedding = chunk.embedding, c.chunk_type = chunk.chunk_type,
                    c.parent_chunk_id = chunk.parent_chunk_id, c.text_hash = chunk.text_hash,
                    c.year = chunk.year, c.title = chunk.title, c.source_type = chunk.source_type,
                    c.source_filename = chunk.source_filename, c.breadcrumb = chunk.breadcrumb,
                    c.is_current = chunk.is_current, c.section_id = chunk.section_id, c.act_id = chunk.root_id
                """,
                chunks=prepared_chunks,
            )

            # Link Chunks to parent Act Section or CaseLaw node
            if source_type != "case_law":
                session.run(
                    """
                    UNWIND $chunks AS chunk
                    MATCH (s:Section {section_id: chunk.section_id})
                    MATCH (c:Chunk {chunk_id: chunk.chunk_id})
                    MERGE (s)-[:HAS_CHUNK]->(c)
                    """,
                    chunks=prepared_chunks,
                )
            else:
                session.run(
                    """
                    UNWIND $chunks AS chunk
                    MATCH (cl:CaseLaw {case_id: chunk.root_id})
                    MATCH (c:Chunk {chunk_id: chunk.chunk_id})
                    MERGE (cl)-[:HAS_CHUNK]->(c)
                    """,
                    chunks=prepared_chunks,
                )

            # Link parent/child chunks
            if parent_child_links:
                session.run(
                    """
                    UNWIND $pairs AS pair
                    MATCH (parent:Chunk {chunk_id: pair.parent_id})
                    MATCH (child:Chunk {chunk_id: pair.child_id})
                    MERGE (parent)-[:HAS_CHILD_CHUNK]->(child)
                    """,
                    pairs=parent_child_links,
                )

            # 4. Link Legal Concepts
            for concept in llm.legal_concepts:
                concept_id = f"concept_{slugify(concept.name)}"
                session.run(
                    """
                    MERGE (lc:LegalConcept {concept_id: $concept_id})
                    SET lc.name = $name, lc.description = $description, lc.aliases = $aliases
                    """,
                    concept_id=concept_id,
                    name=concept.name,
                    description=concept.description,
                    aliases=concept.aliases,
                )
                rel_type = (
                    "ESTABLISHES_PRINCIPLE"
                    if source_type == "case_law"
                    else "RELATES_TO"
                )
                session.run(
                    f"""
                    MATCH (root:{'CaseLaw' if source_type == 'case_law' else 'Act'} {{{'case_id' if source_type == 'case_law' else 'act_id'}: $root_id}})
                    MATCH (lc:LegalConcept {{concept_id: $concept_id}})
                    MERGE (root)-[:{rel_type}]->(lc)
                    """,
                    root_id=root_id,
                    concept_id=concept_id,
                )

            # 5. Link Citations & Amendments
            for citation in llm.statute_citations:
                target_year = 0
                yr_match = re.search(r"\d{4}", citation.act_name)
                if yr_match:
                    target_year = int(yr_match.group(0))
                target_act_id = f"act_{target_year}_{slugify(citation.act_name)}"
                target_sec_id = (
                    f"{target_act_id}_s_{slugify_section(citation.section_ref)}"
                )
                rel_type = (
                    "INTERPRETS"
                    if citation.context.lower() == "interpreted"
                    else "CITES_STATUTE"
                )
                session.run(
                    f"""
                    MATCH (root:{'CaseLaw' if source_type == 'case_law' else 'Act'} {{{'case_id' if source_type == 'case_law' else 'act_id'}: $root_id}})
                    MERGE (a:Act {{act_id: $target_act_id}})
                    ON CREATE SET a.title = $act_name
                    MERGE (s:Section {{section_id: $target_sec_id}})
                    SET s.section_number = $section_ref, s.act_id = $target_act_id
                    MERGE (a)-[:HAS_SECTION]->(s)
                    MERGE (root)-[r:{rel_type}]->(s)
                    SET r.context = $context
                    """,
                    root_id=root_id,
                    target_act_id=target_act_id,
                    target_sec_id=target_sec_id,
                    act_name=citation.act_name,
                    section_ref=citation.section_ref,
                    context=citation.context,
                )

            for case_cit in llm.case_citations:
                target_year = 0
                yr_match = re.search(r"\d{4}", case_cit.citation or "")
                if yr_match:
                    target_year = int(yr_match.group(0))
                target_case_id = f"case_{slugify(case_cit.case_name)}_{target_year}"
                session.run(
                    f"""
                    MATCH (root:{'CaseLaw' if source_type == 'case_law' else 'Act'} {{{'case_id' if source_type == 'case_law' else 'act_id'}: $root_id}})
                    MERGE (target:CaseLaw {{case_id: $target_case_id}})
                    ON CREATE SET target.case_name = $case_name, target.reporter_citation = $citation
                    MERGE (root)-[r:CITES_CASE]->(target)
                    SET r.treatment = $treatment
                    """,
                    root_id=root_id,
                    target_case_id=target_case_id,
                    case_name=case_cit.case_name,
                    citation=case_cit.citation,
                    treatment=case_cit.treatment,
                )


# ---------------------------------------------------------------------------
# Regex patterns & text cleaners (Matching Pinecone pipeline)
# ---------------------------------------------------------------------------
ACT_TITLE_RE = re.compile(r"^(.+?)(?:,?\s*No\.)", re.MULTILINE)
SHORT_TITLE_RE = re.compile(
    r"1\.\s+This\s+(?:Act|Ordinance)\s+may\s+be\s+cited\s+as\s+the\s+([^.]+)",
    re.IGNORECASE,
)
ACT_NUMBER_RE = re.compile(r"No\.\s*(\d+)\s+of", re.IGNORECASE)
YEAR_RE = re.compile(r"of\s+(\d{4})")
ORDINANCE_NUMBERS_RE = re.compile(
    r"Ordinance Nos?\s*[,:]?\s*([\d,\s]+of\s+\d{4})", re.IGNORECASE
)
ACT_NUMBERS_RE = re.compile(r"Act Nos?\s*[,:]?\s*([\d,\s]+of\s+\d{4})", re.IGNORECASE)
CERTIFIED_DATE_RE = re.compile(r"Certified on\s+(.+?\d{4})", re.IGNORECASE)
PARENT_ACT_RE = re.compile(
    r"amend the\s+(.+?\s+(?:Act|Ordinance),?\s*No\.\s*\d+\s+of\s+\d{4})", re.IGNORECASE
)

CASE_NAME_RE = re.compile(r"^(.+?)\s+v\.?\s+(.+)$", re.MULTILINE)
COURT_RE = re.compile(
    r"(COURT OF APPEAL|SUPREME COURT|HIGH COURT|DISTRICT COURT)", re.IGNORECASE
)
JUDGE_RE = re.compile(r"([A-Za-z\s\.,]+(?:J\.|C\.J\.))")
CASE_NUMBER_RE = re.compile(
    r"(?:C\.\s*A\.\s*No\.\s*[\d/]+|S\.\s*C\.\s*No\.\s*[\d/]+)", re.IGNORECASE
)
LOWER_COURT_NO_RE = re.compile(r"(D\.\s*C\.\s*\w+\s*No\.\s*[\d/]+)", re.IGNORECASE)
DATE_DECIDED_RE = re.compile(
    r"(?:Decided on|Judgment on|Date of Judgment):\s+(.+?\d{4})", re.IGNORECASE
)
DATE_HEARD_RE = re.compile(
    r"(?:Argued on|Heard on|Dates of Hearing):\s+(.+)", re.IGNORECASE
)
REPORTER_CITATION_RE = re.compile(
    r"\(\d{4}\)\s*\d+\s*Sri\s*L\.?R\.?\s*\d+", re.IGNORECASE
)
STATUTES_CITED_RE = re.compile(r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+(?:Ordinance|Act))")

STOPWORDS = {
    "the",
    "and",
    "of",
    "to",
    "a",
    "in",
    "for",
    "is",
    "on",
    "that",
    "by",
    "this",
    "or",
    "be",
    "are",
    "from",
    "at",
    "as",
    "court",
    "appeal",
    "supreme",
    "judge",
    "act",
    "ordinance",
}


def extract_keywords(text: str, top_n: int = 5) -> List[str]:
    words = re.findall(r"\b[a-z]{4,}\b", text.lower())
    words = [w for w in words if w not in STOPWORDS]
    return [word for word, count in Counter(words).most_common(top_n)]


def extract_act_metadata(markdown_text: str, filename: str) -> Dict[str, Any]:
    is_ordinance = "ordinance" in markdown_text[:1000].lower()
    meta = {
        "source_type": "ordinance" if is_ordinance else "act",
        "doc_type": "Ordinance" if is_ordinance else "Act",
        "jurisdiction": "Sri Lanka",
        "subject_area": "Contract Law",
        "source_filename": filename,
        "keywords": extract_keywords(markdown_text[:5000]),
        "title": filename.replace(".md", ""),
        "short_title": filename.replace(".md", ""),
        "act_number": None,
        "year": 0,
        "ordinance_numbers": [],
        "act_numbers": [],
        "date_certified": None,
        "parent_act": None,
    }

    title_match = ACT_TITLE_RE.search(markdown_text[:1000])
    if title_match:
        meta["title"] = title_match.group(1).strip()

    st_match = SHORT_TITLE_RE.search(markdown_text[:3000])
    if st_match:
        meta["short_title"] = st_match.group(1).strip()

    act_num_match = ACT_NUMBER_RE.search(markdown_text[:1000])
    if act_num_match:
        meta["act_number"] = int(act_num_match.group(1))

    all_years = YEAR_RE.findall(markdown_text[:2000])
    if all_years:
        meta["year"] = int(all_years[-1])

    cert_match = CERTIFIED_DATE_RE.search(markdown_text[:2000])
    if cert_match:
        meta["date_certified"] = cert_match.group(1).strip()

    return meta


def extract_caselaw_metadata(markdown_text: str, filename: str) -> Dict[str, Any]:
    meta = {
        "source_type": "case_law",
        "doc_type": "CaseLaw",
        "jurisdiction": "Sri Lanka",
        "subject_area": "Contract Law",
        "source_filename": filename,
        "keywords": extract_keywords(markdown_text[:5000]),
        "case_name": filename.replace(".md", ""),
        "plaintiff": None,
        "defendant": None,
        "court": None,
        "case_number": None,
        "lower_court_number": None,
        "date_decided": None,
        "date_heard": [],
        "reporter_citation": None,
        "reporter_volume": None,
        "reporter_page": None,
        "year": 0,
        "judges": [],
        "cases_cited": [],
        "statutes_cited": [],
    }

    case_match = CASE_NAME_RE.search(markdown_text[:1000])
    if case_match:
        meta["case_name"] = case_match.group(0).strip()
        meta["plaintiff"] = case_match.group(1).strip()
        meta["defendant"] = case_match.group(2).strip()

    court_match = COURT_RE.search(markdown_text[:1000])
    if court_match:
        meta["court"] = court_match.group(1).title()

    cn_match = CASE_NUMBER_RE.search(markdown_text[:1000])
    if cn_match:
        meta["case_number"] = cn_match.group(0).strip()

    dd_match = DATE_DECIDED_RE.search(markdown_text[:2000])
    if dd_match:
        meta["date_decided"] = dd_match.group(1).strip()
        yr_match = re.search(r"\d{4}", meta["date_decided"])
        if yr_match:
            meta["year"] = int(yr_match.group(0))

    rep_match = REPORTER_CITATION_RE.search(markdown_text[:1000])
    if rep_match:
        meta["reporter_citation"] = rep_match.group(0)

    lines = markdown_text.split("\n")
    for line in lines[:200]:
        j_matches = JUDGE_RE.findall(line)
        if j_matches:
            for j in j_matches:
                meta["judges"].append(j.strip())

    stat_matches = STATUTES_CITED_RE.findall(markdown_text)
    meta["statutes_cited"] = list(set(stat_matches))

    return meta


# ---------------------------------------------------------------------------
# Chunker & Windower logic
# ---------------------------------------------------------------------------
def window_text(text: str, size: int, overlap: int) -> List[str]:
    clean = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(clean) <= size:
        return [clean]
    parts, start = [], 0
    while start < len(clean):
        end = min(start + size, len(clean))
        if end < len(clean):
            boundary = max(
                clean.rfind("\n\n", start, end), clean.rfind(". ", start, end)
            )
            if boundary > start + int(size * 0.55):
                end = boundary + 1
        parts.append(clean[start:end].strip())
        if end >= len(clean):
            break
        start = max(end - overlap, start + 1)
    return [p for p in parts if p]


def chunk_document(markdown: str, base_meta: Dict[str, Any]) -> List[Dict[str, Any]]:
    blocks = re.split(r"(?:^|\n)(#{1,6}\s+.*)\n", markdown)
    sections = []
    current_heading = "General"
    heading_path = ["General"]

    for i in range(0, len(blocks)):
        if blocks[i].startswith("#"):
            level = len(blocks[i]) - len(blocks[i].lstrip("#"))
            title = blocks[i].strip("# ").strip()
            current_heading = title
            heading_path = heading_path[: level - 1] + [title]
        elif blocks[i].strip():
            sections.append(
                {
                    "text": blocks[i],
                    "heading": current_heading,
                    "heading_path": list(heading_path),
                }
            )

    chunks = []
    doc_id = str(uuid5(NAMESPACE_URL, base_meta["source_filename"]))

    for s_idx, sec in enumerate(sections):
        parent_text = sec["text"].strip()
        if not parent_text:
            continue

        parent_parts = window_text(parent_text, 2000, 200)
        for p_idx, p_text in enumerate(parent_parts):
            p_hash = hashlib.sha256(p_text.encode("utf-8")).hexdigest()
            p_id = str(
                uuid5(NAMESPACE_URL, f"{doc_id}:parent:{s_idx}:{p_idx}:{p_hash[:16]}")
            )

            p_meta = base_meta.copy()
            p_meta.update(
                {
                    "chunk_id": p_id,
                    "parent_id": None,
                    "chunk_type": "parent",
                    "section": sec["heading"],
                    "breadcrumb": " > ".join(sec["heading_path"]),
                    "heading_path": sec["heading_path"],
                    "text_hash": p_hash,
                }
            )
            chunks.append({"id": p_id, "text": p_text, "metadata": p_meta})

            # Create summary
            summary_sentences = [
                s for s in re.split(r"(?<=[.!?])\s+", p_text.strip()) if s
            ][:2]
            summary_text = f"{' > '.join(sec['heading_path'])}\n" + " ".join(
                summary_sentences
            )
            summary_hash = hashlib.sha256(summary_text.encode("utf-8")).hexdigest()
            summary_id = str(
                uuid5(
                    NAMESPACE_URL,
                    f"{doc_id}:summary:{s_idx}:{p_idx}:{summary_hash[:16]}",
                )
            )

            summary_meta = base_meta.copy()
            summary_meta.update(
                {
                    "chunk_id": summary_id,
                    "parent_id": p_id,
                    "chunk_type": "section_summary",
                    "section": sec["heading"],
                    "breadcrumb": " > ".join(sec["heading_path"]),
                    "heading_path": sec["heading_path"],
                    "text_hash": summary_hash,
                }
            )
            chunks.append(
                {"id": summary_id, "text": summary_text, "metadata": summary_meta}
            )

            # Create children
            child_parts = window_text(p_text, 500, 100)
            for c_idx, c_text in enumerate(child_parts):
                c_hash = hashlib.sha256(c_text.encode("utf-8")).hexdigest()
                c_id = str(
                    uuid5(
                        NAMESPACE_URL, f"{doc_id}:child:{s_idx}:{c_idx}:{c_hash[:16]}"
                    )
                )

                c_meta = base_meta.copy()
                c_meta.update(
                    {
                        "chunk_id": c_id,
                        "parent_id": p_id,
                        "chunk_type": "child",
                        "section": sec["heading"],
                        "breadcrumb": " > ".join(sec["heading_path"]),
                        "heading_path": sec["heading_path"],
                        "text_hash": c_hash,
                    }
                )
                chunks.append({"id": c_id, "text": c_text, "metadata": c_meta})

    return chunks


# ---------------------------------------------------------------------------
# Direct docling PDF parsing function
# ---------------------------------------------------------------------------
def parse_pdfs_to_markdown(acts_dir: str, cases_dir: str, output_md_dir: str) -> None:
    """Uses Docling to convert raw PDFs to Markdown layout files in structured directories."""
    if not HAS_DOCLING:
        logger.error(
            "Docling is not installed! Run `pip install docling` to parse PDFs."
        )
        sys.exit(1)

    try:
        import torch

        device_type = "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        device_type = "cpu"

    logger.info("Initializing Docling Document Converter on %s...", device_type)
    pipeline_options = PdfPipelineOptions(
        do_table_structure=False,
        accelerator_options=AcceleratorOptions(num_threads=4, device=device_type),
    )
    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
        }
    )

    pdf_folders = [("acts", acts_dir), ("case_laws", cases_dir)]
    for subfolder, folder_path in pdf_folders:
        if not folder_path:
            continue
        p_path = Path(folder_path)
        if not p_path.exists():
            logger.warning("Folder does not exist: %s", folder_path)
            continue

        pdf_files = list(p_path.glob("*.pdf"))
        logger.info(
            "Found %d PDF files to process in %s (%s)",
            len(pdf_files),
            subfolder,
            folder_path,
        )

        out_sub_dir = Path(output_md_dir) / subfolder
        out_sub_dir.mkdir(parents=True, exist_ok=True)

        for pdf_path in pdf_files:
            out_md_path = out_sub_dir / f"{pdf_path.stem}.md"
            if out_md_path.exists():
                logger.info("  Markdown file already exists: %s", out_md_path.name)
                continue

            logger.info("  Converting PDF: %s -> %s", pdf_path.name, out_md_path.name)
            try:
                result = converter.convert(str(pdf_path))
                md_content = result.document.export_to_markdown()
                out_md_path.write_text(md_content, encoding="utf-8")
            except Exception as e:
                logger.error("  Failed to parse PDF '%s': %s", pdf_path.name, e)


def embed_with_retry(
    jina_api_key: str,
    model_name: str,
    contents: list,
    embedding_dim: int,
    max_retries: int = 5,
) -> list:
    """Generates embeddings using Jina AI embeddings API with backoff retry support."""
    # Get your Jina AI API key for free: https://jina.ai/?sui=apikey
    if not jina_api_key:
        logger.error("Jina AI API key is missing.")
        return [[0.0] * embedding_dim] * len(contents)

    # Extract plain text from types.Content or pass string through
    plain_texts = []
    for c in contents:
        if hasattr(c, "parts") and c.parts:
            part_text = getattr(c.parts[0], "text", "")
            plain_texts.append(part_text)
        elif isinstance(c, str):
            plain_texts.append(c)
        else:
            plain_texts.append(str(c))

    headers = {
        "Authorization": f"Bearer {jina_api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    data = {
        "model": model_name,
        "input": plain_texts,
        "task": "retrieval.passage",
        "dimensions": embedding_dim,
    }

    retries = 0
    backoff = 2.0
    while retries < max_retries:
        try:
            response = httpx.post(
                "https://api.jina.ai/v1/embeddings",
                json=data,
                headers=headers,
                timeout=60.0,
            )
            if response.status_code == 200:
                res_json = response.json()
                sorted_data = sorted(res_json["data"], key=lambda x: x["index"])
                return [item["embedding"] for item in sorted_data]
            elif response.status_code in [401, 403]:
                logger.error(
                    "Jina AI authentication failed (status %d): %s. Please check your JINA_API_KEY.",
                    response.status_code,
                    response.text,
                )
                raise ValueError("Invalid Jina AI API key or unauthorized access.")
            elif response.status_code == 429:
                retries += 1
                logger.warning(
                    "Jina AI rate limit hit (429)! Retrying in %.2f seconds (attempt %d/%d)...",
                    backoff,
                    retries,
                    max_retries,
                )
                time.sleep(backoff)
                backoff *= 2.0
            else:
                retries += 1
                logger.warning(
                    "Jina AI API returned error status %d: %s. Retrying in %.2f seconds...",
                    response.status_code,
                    response.text,
                    backoff,
                )
                time.sleep(backoff)
                backoff *= 2.0
        except Exception as e:
            retries += 1
            logger.warning(
                "Jina AI request failed: %s. Retrying in %.2f seconds...", e, backoff
            )
            time.sleep(backoff)
            backoff *= 2.0

    raise RuntimeError(
        f"Failed to generate Jina embeddings after {max_retries} attempts due to rate limits."
    )



# ---------------------------------------------------------------------------
# Core Ingestion Coordinator
# ---------------------------------------------------------------------------
def ingest_pipeline(
    acts_dir: Optional[str],
    cases_dir: Optional[str],
    output_md_dir: str,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str,
    neo4j_database: str,
    google_api_key: str,
    jina_api_key: str,
    embedding_dim: int,
) -> None:
    if not HAS_NEO4J:
        logger.error("neo4j python package not installed! Run `pip install neo4j`")
        sys.exit(1)

    # 1. Parse PDFs to Markdown using Docling if raw directories are provided
    if (acts_dir and Path(acts_dir).exists()) or (
        cases_dir and Path(cases_dir).exists()
    ):
        logger.info("=== Stage 1: Converting raw PDFs to Markdown via Docling ===")
        parse_pdfs_to_markdown(acts_dir, cases_dir, output_md_dir)
    else:
        logger.info(
            "=== Skipping Stage 1 (No PDF folders provided or they do not exist) ==="
        )

    # 2. Establish Neo4j connection
    logger.info("Connecting to Neo4j database at %s ...", neo4j_uri)
    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
    try:
        driver.verify_connectivity()
        logger.info("Connected to Neo4j successfully.")
    except Exception as e:
        logger.error("Could not connect to Neo4j. Check settings: %s", e)
        sys.exit(1)

    # 3. Setup embedding services
    if not HAS_GENAI:
        logger.error(
            "google-genai package is not installed! Run `pip install google-genai`"
        )
        sys.exit(1)

    logger.info("Initializing Google Gemini API Client...")
    genai_client = genai.Client(api_key=google_api_key)

    # 4. Resolve components (Local import or Fallbacks)
    if HAS_APP:
        logger.info("Running in backend package mode (Local imports verified).")
        extractor = Neo4jLLMEntityExtractor()
        builder = Neo4jGraphBuilder(driver)
    else:
        logger.info(
            "Running in standalone / Google Colab mode (Standalone fallback enabled)."
        )
        extractor = FallbackLLMEntityExtractor(api_key=google_api_key)
        builder = FallbackGraphBuilder(driver, database=neo4j_database)

    # 5. Read converted Markdown files
    md_files = list(Path(output_md_dir).rglob("*.md"))
    logger.info(
        "=== Stage 2: Processing %d Markdown documents for GraphRAG ===", len(md_files)
    )

    for idx, file_path in enumerate(md_files, 1):
        logger.info("[%d/%d] Ingesting: %s", idx, len(md_files), file_path.name)
        text = file_path.read_text(encoding="utf-8")

        # Regex metadata
        is_act = (
            "acts" in str(file_path.parent).lower() or "act" in file_path.name.lower()
        )
        if is_act:
            meta = extract_act_metadata(text, file_path.name)
        else:
            meta = extract_caselaw_metadata(text, file_path.name)

        logger.info(
            "  Regex title: %s, year: %s",
            meta.get("title") or meta.get("case_name"),
            meta.get("year"),
        )

        # Gemini deep extraction (concepts, amendments, citations)
        llm_result = extractor.extract(text)
        logger.info(
            "  LLM concepts: %d, citations: %d, current: %s",
            len(llm_result.legal_concepts),
            len(llm_result.statute_citations),
            llm_result.is_current,
        )

        # Build chunks
        chunks = chunk_document(text, meta)
        chunks_to_embed = [
            c
            for c in chunks
            if c["metadata"]["chunk_type"] in ["child", "section_summary"]
        ]
        logger.info(
            "  Hierarchical split: %d total chunks (%d to embed)",
            len(chunks),
            len(chunks_to_embed),
        )

        # Generate Jina AI jina-embeddings-v4 vectors in batches
        if chunks_to_embed:
            logger.info("  Generating cloud-hosted jina-embeddings-v4 vectors...")
            docs_to_embed = [
                {
                    "text": c["text"],
                    "title": meta.get("title") or meta.get("case_name") or "none",
                }
                for c in chunks_to_embed
            ]

            # Format according to doc structure prefixing
            formatted_contents = [
                f"title: {d['title']} | text: {d['text']}"
                for d in docs_to_embed
            ]

            # Batch calls (100 at a time for quota efficiency)
            batch_size = 100
            embeddings = []
            for i in range(0, len(formatted_contents), batch_size):
                batch_contents = formatted_contents[i : i + batch_size]
                try:
                    batch_embs = embed_with_retry(
                        jina_api_key=jina_api_key,
                        model_name="jina-embeddings-v4",
                        contents=batch_contents,
                        embedding_dim=embedding_dim,
                    )
                    embeddings.extend(batch_embs)
                except Exception as e:
                    logger.error("  Batch embedding failed completely: %s", e)
                    embeddings.extend([[0.0] * embedding_dim] * len(batch_contents))
                time.sleep(1.0)  # Safe rate throttle between batches

            for chunk, emb in zip(chunks_to_embed, embeddings):
                chunk["embedding"] = emb

        # Load to Graph database
        logger.info("  Pumping data to Neo4j graph database...")
        builder.build_document_graph(meta, chunks, llm_result)
        logger.info("  Document successfully saved in graph.")
        time.sleep(2)

    driver.close()
    logger.info("=== GraphRAG Ingestion Complete! ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LankaLawBot Neo4j Ingestion Pipeline")
    parser.add_argument(
        "--acts-dir",
        default=os.environ.get("ACTS_DIR", None),
        help="Path to folder containing raw PDF acts (optional).",
    )
    parser.add_argument(
        "--cases-dir",
        default=os.environ.get("CASES_DIR", None),
        help="Path to folder containing raw PDF case laws (optional).",
    )

    parser.add_argument(
        "--output-md-dir",
        default="./parsed_markdown",
        help="Directory where converted markdown is read or stored.",
    )
    # Neo4j Settings
    parser.add_argument(
        "--neo4j-uri", default=os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    )
    parser.add_argument("--neo4j-user", default=os.environ.get("NEO4J_USER", "neo4j"))
    parser.add_argument(
        "--neo4j-password", default=os.environ.get("NEO4J_PASSWORD", "lankalawbot2026")
    )
    parser.add_argument(
        "--neo4j-database", default=os.environ.get("NEO4J_DATABASE", "neo4j")
    )
    # Keys & dimensions
    parser.add_argument(
        "--google-api-key", default=os.environ.get("GOOGLE_API_KEY", "")
    )
    parser.add_argument(
        "--jina-api-key", default=os.environ.get("JINA_API_KEY", "")
    )
    parser.add_argument(
        "--embedding-dim",
        type=int,
        default=2048,
        help="Embedding size (default: 2048).",
    )

    args, unknown = parser.parse_known_args()

    # Resolve settings from local config if running in-repo and args are default/empty
    if HAS_APP:
        google_key = args.google_api_key or settings.GOOGLE_API_KEY
        jina_key = args.jina_api_key or settings.JINA_API_KEY
        uri = (
            args.neo4j_uri
            if args.neo4j_uri != "bolt://localhost:7687"
            else settings.NEO4J_URI
        )
        user = args.neo4j_user if args.neo4j_user != "neo4j" else settings.NEO4J_USER
        password = (
            args.neo4j_password
            if args.neo4j_password != "lankalawbot2026"
            else settings.NEO4J_PASSWORD
        )
        database = (
            args.neo4j_database
            if args.neo4j_database != "neo4j"
            else settings.NEO4J_DATABASE
        )
        dim = (
            args.embedding_dim
            if args.embedding_dim != 2048
            else settings.NEO4J_EMBEDDING_DIMENSION
        )
    else:
        google_key = args.google_api_key
        jina_key = args.jina_api_key
        uri = args.neo4j_uri
        user = args.neo4j_user
        password = args.neo4j_password
        database = args.neo4j_database
        dim = args.embedding_dim

    if not google_key:
        logger.error(
            "Missing Google API key! Provide via --google-api-key or environment variable GOOGLE_API_KEY."
        )
        sys.exit(1)

    if not jina_key:
        logger.error(
            "Missing Jina API key! Provide via --jina-api-key or environment variable JINA_API_KEY."
        )
        sys.exit(1)

    ingest_pipeline(
        acts_dir=args.acts_dir,
        cases_dir=args.cases_dir,
        output_md_dir=args.output_md_dir,
        neo4j_uri=uri,
        neo4j_user=user,
        neo4j_password=password,
        neo4j_database=database,
        google_api_key=google_key,
        jina_api_key=jina_key,
        embedding_dim=dim,
    )

