"""
Neo4j Graph Builder.
Handles construction of the legal knowledge graph by running batched Cypher operations
on a Neo4j instance. Uses MERGE for idempotency and handles alphanumeric section IDs.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional
from neo4j import Driver, GraphDatabase

from app.core.config import settings
from app.services.ingestion.neo4j_llm_entity_extractor import DeepLegalExtractionResult

logger = logging.getLogger(__name__)


def slugify(text: str) -> str:
    """Normalize text into lowercase alphanumeric words joined by underscores."""
    if not text:
        return "unknown"
    s = text.lower().strip()
    s = re.sub(r"[^a-z0-9_]", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "unknown"


def slugify_section(raw_label: str) -> str:
    """Normalize alphanumeric section IDs for stable MERGE keys.
    '4A' -> '4a', '4(1)(b)' -> '4_1_b', 'Schedule II' -> 'schedule_ii'
    """
    if not raw_label:
        return "general"
    s = raw_label.lower().strip()
    s = re.sub(r"[()\[\]]", "_", s)  # Brackets -> underscores
    s = re.sub(r"[^a-z0-9_]", "_", s)  # Non-alphanum -> underscores
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "general"


class Neo4jGraphBuilder:
    """Orchestrates insertion of legal metadata, chunks, and relationships into Neo4j."""

    def __init__(self, driver: Driver) -> None:
        self._driver = driver
        self._db = settings.NEO4J_DATABASE

    def build_document_graph(
        self,
        doc_metadata: Dict[str, Any],
        chunks: List[Dict[str, Any]],
        llm_result: DeepLegalExtractionResult,
    ) -> None:
        """Constructs the complete sub-graph for a single legal document."""
        source_type = doc_metadata.get("source_type", "act")

        with self._driver.session(database=self._db) as session:
            # 1. Create root document node
            if source_type == "case_law":
                self._create_caselaw_root(session, doc_metadata, llm_result)
            else:
                self._create_act_root(session, doc_metadata, llm_result)

            # 2. Process and create Sections and Chunks
            self._create_sections_and_chunks(session, doc_metadata, chunks, llm_result)

            # 3. Create Rich LLM Entities & Relationships
            self._create_concepts_and_citations(session, doc_metadata, llm_result)

    def _create_act_root(
        self, session: Any, meta: Dict[str, Any], llm: DeepLegalExtractionResult
    ) -> None:
        """Create or update Act/Ordinance root node."""
        year = int(meta.get("year", 0))
        act_num = meta.get("act_number")
        act_num_val = int(act_num) if act_num is not None else 0
        act_id = f"act_{year}_{act_num_val}"

        query = """
        MERGE (a:Act {act_id: $act_id})
        SET a.title = $title,
            a.short_title = $short_title,
            a.act_number = $act_number,
            a.year = $year,
            a.date_certified = $date_certified,
            a.date_enacted = $date_enacted,
            a.jurisdiction = $jurisdiction,
            a.source_type = $source_type,
            a.doc_type = $doc_type,
            a.subject_area = $subject_area,
            a.source_filename = $source_filename,
            a.keywords = $keywords,
            a.parent_act = $parent_act,
            a.is_current = $is_current,
            a.repealed_by = $repealed_by
        """
        session.run(
            query,
            act_id=act_id,
            title=meta.get("title") or meta.get("short_title"),
            short_title=meta.get("short_title"),
            act_number=act_num_val,
            year=year,
            date_certified=meta.get("date_certified"),
            date_enacted=meta.get("date_enacted"),
            jurisdiction=meta.get("jurisdiction", "Sri Lanka"),
            source_type=meta.get("source_type"),
            doc_type=meta.get("doc_type"),
            subject_area=meta.get("subject_area"),
            source_filename=meta.get("source_filename"),
            keywords=meta.get("keywords", []),
            parent_act=meta.get("parent_act"),
            is_current=llm.is_current,
            repealed_by=llm.repealed_by,
        )
        logger.info("Created root Act node: %s", act_id)

    def _create_caselaw_root(
        self, session: Any, meta: Dict[str, Any], llm: DeepLegalExtractionResult
    ) -> None:
        """Create or update CaseLaw root node."""
        case_name = meta.get("case_name", "unknown")
        year = int(meta.get("year", 0))
        case_id = f"case_{slugify(case_name)}_{year}"

        query = """
        MERGE (cl:CaseLaw {case_id: $case_id})
        SET cl.case_name = $case_name,
            cl.plaintiff = $plaintiff,
            cl.defendant = $defendant,
            cl.court = $court,
            cl.case_number = $case_number,
            cl.lower_court_number = $lower_court_number,
            cl.date_decided = $date_decided,
            cl.date_heard = $date_heard,
            cl.reporter_citation = $reporter_citation,
            cl.reporter_volume = $reporter_volume,
            cl.reporter_page = $reporter_page,
            cl.year = $year,
            cl.judges = $judges,
            cl.cases_cited = $cases_cited,
            cl.statutes_cited = $statutes_cited,
            cl.legal_principles = $legal_principles,
            cl.jurisdiction = $jurisdiction,
            cl.source_type = $source_type,
            cl.source_filename = $source_filename,
            cl.subject_area = $subject_area
        """
        session.run(
            query,
            case_id=case_id,
            case_name=case_name,
            plaintiff=meta.get("plaintiff"),
            defendant=meta.get("defendant"),
            court=meta.get("court"),
            case_number=meta.get("case_number"),
            lower_court_number=meta.get("lower_court_number"),
            date_decided=meta.get("date_decided"),
            date_heard=meta.get("date_heard", []),
            reporter_citation=meta.get("reporter_citation"),
            reporter_volume=meta.get("reporter_volume"),
            reporter_page=meta.get("reporter_page"),
            year=year,
            judges=meta.get("judges", []),
            cases_cited=meta.get("cases_cited", []),
            statutes_cited=meta.get("statutes_cited", []),
            legal_principles=meta.get("legal_principles", []),
            jurisdiction=meta.get("jurisdiction", "Sri Lanka"),
            source_type=meta.get("source_type"),
            source_filename=meta.get("source_filename"),
            subject_area=meta.get("subject_area"),
        )
        logger.info("Created root CaseLaw node: %s", case_id)

        # Connect Court
        if meta.get("court"):
            court_name = meta["court"]
            court_id = slugify(court_name)
            session.run(
                """
                MERGE (ct:Court {name: $court_name})
                ON CREATE SET ct.court_id = $court_id
                WITH ct
                MATCH (cl:CaseLaw {case_id: $case_id})
                MERGE (cl)-[:DECIDED_BY]->(ct)
                """,
                court_name=court_name,
                court_id=court_id,
                case_id=case_id,
            )

        # Connect Judges
        for judge in meta.get("judges", []):
            session.run(
                """
                MERGE (j:Judge {name: $judge_name})
                WITH j
                MATCH (cl:CaseLaw {case_id: $case_id})
                MERGE (cl)-[:PRESIDED_BY]->(j)
                """,
                judge_name=judge,
                case_id=case_id,
            )

    def _create_sections_and_chunks(
        self,
        session: Any,
        meta: Dict[str, Any],
        chunks: List[Dict[str, Any]],
        llm: DeepLegalExtractionResult,
    ) -> None:
        """Create Sections, Chunk nodes, parent-child links, and root-to-child links."""
        source_type = meta.get("source_type", "act")
        year = int(meta.get("year", 0))

        # Root doc ID references
        if source_type == "case_law":
            root_label = "CaseLaw"
            root_id_prop = "case_id"
            root_id_val = f"case_{slugify(meta.get('case_name', 'unknown'))}_{year}"
        else:
            root_label = "Act"
            root_id_prop = "act_id"
            act_num = meta.get("act_number")
            root_id_val = f"act_{year}_{int(act_num) if act_num is not None else 0}"

        # 1. First, create Section nodes if we are dealing with an Act/Ordinance
        if source_type != "case_law":
            unique_sections = set(
                c["metadata"].get("section")
                for c in chunks
                if c["metadata"].get("section")
            )
            for raw_sec in unique_sections:
                sec_id = f"{root_id_val}_s_{slugify_section(raw_sec)}"
                session.run(
                    f"""
                    MATCH (root:Act {{{root_id_prop}: $root_id}})
                    MERGE (s:Section {{section_id: $sec_id}})
                    SET s.section_number = $sec_num,
                        s.heading = $heading,
                        s.breadcrumb = $breadcrumb,
                        s.act_id = $root_id
                    MERGE (root)-[:HAS_SECTION]->(s)
                    """,
                    root_id=root_id_val,
                    sec_id=sec_id,
                    sec_num=raw_sec,
                    heading=raw_sec,
                    breadcrumb=f"{meta.get('title')} > {raw_sec}",
                )

        # 2. Prepare chunks for bulk UNWIND operations
        prepared_chunks = []
        parent_child_links = []

        for chunk in chunks:
            chunk_id = chunk["id"]
            text = chunk["text"]
            chunk_meta = chunk["metadata"]
            chunk_type = chunk_meta.get("chunk_type", "child")

            sec_label = chunk_meta.get("section") or "general"
            sec_id = f"{root_id_val}_s_{slugify_section(sec_label)}"

            prepared_chunks.append({
                "chunk_id": chunk_id,
                "text": text,
                "embedding": chunk.get("embedding"),
                "chunk_type": chunk_type,
                "chunk_strategy": chunk_meta.get("chunk_strategy", "legal_clause"),
                "parent_chunk_id": chunk_meta.get("parent_id"),
                "text_hash": chunk_meta.get("text_hash"),
                "year": year,
                "title": meta.get("title") or meta.get("case_name"),
                "source_type": source_type,
                "doc_type": meta.get("doc_type"),
                "subject_area": meta.get("subject_area"),
                "source_filename": meta.get("source_filename"),
                "breadcrumb": chunk_meta.get("breadcrumb"),
                "is_current": llm.is_current,
                "section_id": sec_id,
                "root_id": root_id_val,
            })

            parent_id = chunk_meta.get("parent_id")
            if parent_id:
                parent_child_links.append({
                    "parent_id": parent_id,
                    "child_id": chunk_id,
                })

        # 3. Unwind Chunks creation
        chunk_query = f"""
        UNWIND $chunks AS chunk
        MERGE (c:Chunk {{chunk_id: chunk.chunk_id}})
        SET c.text = chunk.text,
            c.embedding = chunk.embedding,
            c.chunk_type = chunk.chunk_type,
            c.chunk_strategy = chunk.chunk_strategy,
            c.parent_chunk_id = chunk.parent_chunk_id,
            c.text_hash = chunk.text_hash,
            c.year = chunk.year,
            c.title = chunk.title,
            c.source_type = chunk.source_type,
            c.doc_type = chunk.doc_type,
            c.subject_area = chunk.subject_area,
            c.source_filename = chunk.source_filename,
            c.breadcrumb = chunk.breadcrumb,
            c.is_current = chunk.is_current,
            c.section_id = chunk.section_id,
            c.act_id = chunk.root_id
        """
        session.run(chunk_query, chunks=prepared_chunks)

        # 4. Create Section-to-Chunk relationship (for Acts) or Case-to-Chunk (for Case Law)
        if source_type != "case_law":
            session.run(
                """
                UNWIND $chunks AS chunk
                MATCH (s:Section {section_id: chunk.section_id})
                MATCH (c:Chunk {chunk_id: chunk.chunk_id})
                MERGE (s)-[:HAS_CHUNK]->(c)
                """             ,
                chunks=prepared_chunks,
            )
        else:
            session.run(
                f"""
                UNWIND $chunks AS chunk
                MATCH (cl:CaseLaw {{{root_id_prop}: chunk.root_id}})
                MATCH (c:Chunk {{chunk_id: chunk.chunk_id}})
                MERGE (cl)-[:HAS_CHUNK]->(c)
                """             ,
                chunks=prepared_chunks,
            )

        # 5. Connect parent-child chunks
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
        logger.info(
            "Created %d chunk nodes & relationships under root doc.", len(chunks)
        )

    def _create_concepts_and_citations(
        self, session: Any, meta: Dict[str, Any], llm: DeepLegalExtractionResult
    ) -> None:
        """Connect the document node to legal concepts, statute section nodes, and case laws."""
        source_type = meta.get("source_type", "act")
        year = int(meta.get("year", 0))

        # Root doc lookup properties
        if source_type == "case_law":
            root_label = "CaseLaw"
            root_id_prop = "case_id"
            root_id_val = f"case_{slugify(meta.get('case_name', 'unknown'))}_{year}"
        else:
            root_label = "Act"
            root_id_prop = "act_id"
            act_num = meta.get("act_number")
            root_id_val = f"act_{year}_{int(act_num) if act_num is not None else 0}"

        # 1. Create LegalConcepts and link RELATES_TO / ESTABLISHES_PRINCIPLE
        for concept in llm.legal_concepts:
            concept_id = f"concept_{slugify(concept.name)}"
            session.run(
                """
                MERGE (lc:LegalConcept {concept_id: $concept_id})
                SET lc.name = $name,
                    lc.description = $description,
                    lc.aliases = $aliases
                """,
                concept_id=concept_id,
                name=concept.name,
                description=concept.description,
                aliases=concept.aliases,
            )

            # Connect root doc to concept
            rel_type = (
                "ESTABLISHES_PRINCIPLE" if source_type == "case_law" else "RELATES_TO"
            )
            session.run(
                f"""
                MATCH (root:{root_label} {{{root_id_prop}: $root_id}})
                MATCH (lc:LegalConcept {{concept_id: $concept_id}})
                MERGE (root)-[:{rel_type}]->(lc)
                """,
                root_id=root_id_val,
                concept_id=concept_id,
            )

        # 2. Process Amendments (for Acts/Ordinances)
        if source_type != "case_law":
            for amendment in llm.amendments:
                # We extract target act details
                amended_title = amendment.amended_act
                # We attempt to find the year/act number of the amended act to link
                # If target act exists or can be matched, link them.
                # In low-resource environment, we do a text match on title or MERGE a partial target
                target_year = 0
                target_num = 0
                yr_match = re.search(r"\d{4}", amended_title)
                if yr_match:
                    target_year = int(yr_match.group(0))
                num_match = re.search(r"No\.\s*(\d+)", amended_title, re.IGNORECASE)
                if num_match:
                    target_num = int(num_match.group(1))

                target_act_id = f"act_{target_year}_{target_num}"
                rel_type = (
                    "REPEALS" if amendment.type.lower() == "repeals" else "AMENDS"
                )

                session.run(
                    f"""
                    MATCH (root:Act {{act_id: $root_id}})
                    MERGE (target:Act {{act_id: $target_id}})
                    ON CREATE SET target.title = $target_title, target.is_current = false
                    MERGE (root)-[r:{rel_type}]->(target)
                    SET r.sections_affected = $sections_affected
                    """,
                    root_id=root_id_val,
                    target_id=target_act_id,
                    target_title=amended_title,
                    sections_affected=amendment.sections_affected,
                )

        # 3. Process Statute Citations (mostly from CaseLaw)
        for citation in llm.statute_citations:
            # Locate or create the section being interpreted/cited
            # Target act ID matching
            target_year = 0
            target_num = 0
            yr_match = re.search(r"\d{4}", citation.act_name)
            if yr_match:
                target_year = int(yr_match.group(0))
            # Create a deterministic Act target
            act_slug = slugify(citation.act_name)
            target_act_id = f"act_{target_year}_{act_slug}"
            target_sec_id = f"{target_act_id}_s_{slugify_section(citation.section_ref)}"

            rel_type = (
                "INTERPRETS"
                if citation.context.lower() == "interpreted"
                else "CITES_STATUTE"
            )

            session.run(
                f"""
                MATCH (root:{root_label} {{{root_id_prop}: $root_id}})
                MERGE (a:Act {{act_id: $target_act_id}})
                ON CREATE SET a.title = $act_name
                MERGE (s:Section {{section_id: $target_sec_id}})
                SET s.section_number = $section_ref, s.act_id = $target_act_id
                MERGE (a)-[:HAS_SECTION]->(s)
                MERGE (root)-[r:{rel_type}]->(s)
                SET r.context = $context
                """,
                root_id=root_id_val,
                target_act_id=target_act_id,
                target_sec_id=target_sec_id,
                act_name=citation.act_name,
                section_ref=citation.section_ref,
                context=citation.context,
            )

        # 4. Process Case Citations
        for case_cit in llm.case_citations:
            target_year = 0
            yr_match = re.search(r"\d{4}", case_cit.citation or "")
            if yr_match:
                target_year = int(yr_match.group(0))
            elif case_cit.citation:
                yr_match = re.search(r"\d{4}", case_cit.citation)
                if yr_match:
                    target_year = int(yr_match.group(0))

            target_case_id = f"case_{slugify(case_cit.case_name)}_{target_year}"

            session.run(
                f"""
                MATCH (root:{root_label} {{{root_id_prop}: $root_id}})
                MERGE (target:CaseLaw {{case_id: $target_case_id}})
                ON CREATE SET target.case_name = $case_name, target.reporter_citation = $citation
                MERGE (root)-[r:CITES_CASE]->(target)
                SET r.treatment = $treatment
                """,
                root_id=root_id_val,
                target_case_id=target_case_id,
                case_name=case_cit.case_name,
                citation=case_cit.citation,
                treatment=case_cit.treatment,
            )
