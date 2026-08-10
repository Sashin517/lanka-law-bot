from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "act_and_case_law_ingestion_process_pinecone.py"


def _load_ingestion():
    spec = importlib.util.spec_from_file_location("pinecone_ingestion_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ingestion = _load_ingestion()


def _metadata(**overrides):
    values = {
        "source_id": "sha256:" + "a" * 64,
        "work_id": "lk:act:2000:1",
        "expression_id": "expression:one",
        "identity_status": "resolved",
        "needs_review": False,
        "source_type": "act",
        "doc_type": "Act",
        "title": "Example Act",
        "normalized_title": "example act",
        "work_year": 2000,
        "instrument_number": "1",
        "source_filename": "example.pdf",
        "source_path": "example.pdf",
        "source_sha256": "a" * 64,
        "source_size_bytes": 100,
        "parser_version": "test",
        "parser_config_hash": "config",
    }
    values.update(overrides)
    return ingestion.LegalMetadata(**values)


def test_script_is_importable_and_contains_no_provider_key_literals():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "!pip install" not in source
    assert not re.search(r"pcsk_[A-Za-z0-9_-]{20,}", source)
    assert not re.search(r"jina_[A-Za-z0-9_-]{20,}", source)
    assert ingestion.INDEX_NAME == "lawdex-legal-documents-v1"


def test_content_classification_overrides_wrong_directory_hint():
    ordinance = "ORDINANCE Nos, 18 of 1995\nAN ORDINANCE TO CONSOLIDATE THE LAW"
    case = "SUPREME COURT\nA.B. PERERA\nv.\nATTORNEY-GENERAL\nSC FR 1/2020"
    assert ingestion.infer_source_type(ordinance, "case_law") == "ordinance"
    assert ingestion.infer_source_type(case, "act") == "case_law"


def test_docket_regex_does_not_treat_common_statutory_words_as_case_numbers():
    for value in ("Schedule", "case", "carrying", "cannot", "Cap"):
        assert ingestion.DOCKET_RE.search(value) is None
    for value in ("S.C. 85/83", "C.A. 503/95", "SC FR 228/2005"):
        assert ingestion.DOCKET_RE.search(value)


def test_case_header_outweighs_statutes_cited_inside_the_judgment():
    decision = """
    SUPREME COURT
    ABEYWICKREMA v. PATHIRANA
    S.C. 85/83
    The Companies Act No. 7 of 2007 was discussed by court.
    """
    assert ingestion.infer_source_type(decision, "case_law") == "case_law"


def test_consolidated_statutes_use_original_instrument_not_amendments():
    civil_procedure = """
    Ordinance Nos, 2 of 1889 12 of 1895
    Act Nos, 19 of 2006 43 of 2024
    CHAPTER 105 CIVIL PROCEDURE CODE
    AN ORDINANCE TO CONSOLIDATE AND AMEND THE LAW OF CIVIL COURTS.
    Short title. 1. This Ordinance may be cited as the Civil Procedure Code.
    """
    penal_code = """
    PENAL CODE
    AN ORDINANCE TO PROVIDE A GENERAL PENAL CODE FOR SRI LANKA.
    Ordinance Nos, 11 of 1887 2 of 1883 13 of 1888
    Act Nos, 6 of 1968 5 of 2021
    Short title. 1. This Ordinance may be cited as the Penal Code.
    """

    assert ingestion.infer_source_type(civil_procedure, "act") == "ordinance"
    assert ingestion.instrument_identity(civil_procedure)[1:3] == (1889, "2")
    assert ingestion.instrument_identity(penal_code)[1:3] == (1883, "2")


def test_lawnet_locator_recovers_chapter_without_treating_edition_as_work_year():
    partial_lawnet_export = """
    https://lankalaw.net/wp-content/uploads/2025/02/1981Y7V171C-1.html
    SERVICE CONTRACTS
    This Ordinance may be cited as the Service Contracts Ordinance.
    """

    title, year, number, chapter = ingestion.instrument_identity(
        partial_lawnet_export
    )

    assert title == "Service Contracts Ordinance"
    assert year is None
    assert number is None
    assert chapter == "171"


def test_law_and_constitution_are_distinct_canonical_work_types():
    partition = """
    PARTITION
    A LAW TO PROVIDE FOR THE PARTITION AND SALE OF LAND HELD IN COMMON.
    Law Nos, 21 of 1977
    Act Nos, 5 of 1981 27 of 2024
    Short title 1. This Law may be cited as the Partition Law.
    """
    constitution = (
        "The Constitution of the Democratic Socialist Republic of Sri Lanka\n"
        "As amended up to 31st October 2022"
    )

    assert ingestion.infer_source_type(partition, "act") == "law"
    assert ingestion.instrument_identity(partition)[1:3] == (1977, "21")
    assert ingestion.infer_source_type(constitution, "act") == "constitution"


def test_ocr_quality_gate_allows_one_blank_cover_only_after_forced_ocr():
    markdown = "Substantial official legal text. " * 30 + ingestion.PAGE_BREAK
    standard = ingestion.quality_gate(markdown, 2, "standard")
    forced = ingestion.quality_gate(markdown, 2, "forced_full_page_ocr")
    assert not standard.passed
    assert forced.passed
    assert forced.text_coverage == 0.5


def test_environment_boolean_parser_is_case_insensitive(monkeypatch):
    monkeypatch.setenv("LEGAL_TEST_FLAG", "False")
    assert ingestion.environment_flag("LEGAL_TEST_FLAG", True) is False
    monkeypatch.setenv("LEGAL_TEST_FLAG", "TRUE")
    assert ingestion.environment_flag("LEGAL_TEST_FLAG", False) is True


def test_strict_manifest_is_bound_to_exact_pdf_hash(monkeypatch):
    monkeypatch.setattr(ingestion, "STRICT_PUBLICATION", True)
    metadata = _metadata(
        source_uri="https://example.gov.lk/example.pdf",
        source_authority="Government of Sri Lanka",
        source_publisher="Department of Government Printing",
        source_license="public-law",
        authoritative=True,
        version_date="2026-01-01",
    )
    override = {
        "source_sha256": "b" * 64,
        "source_uri": metadata.source_uri,
        "source_authority": metadata.source_authority,
        "source_publisher": metadata.source_publisher,
        "source_license": metadata.source_license,
        "authoritative": True,
        "version_date": "2026-01-01",
    }

    with pytest.raises(ingestion.MetadataValidationError, match="does not match"):
        ingestion.validate_publication_metadata(metadata, override)


def test_non_strict_preflight_quarantines_expected_metadata_review(
    monkeypatch, tmp_path
):
    source = tmp_path / "lankalaw_net (1).pdf"
    candidate = _metadata(
        work_id="lk:source:" + "a" * 32,
        identity_status="candidate",
        needs_review=True,
        work_year=None,
        instrument_number=None,
        chapter_number=None,
        source_filename=source.name,
        source_path=str(source),
    )

    class DummyTokenizer:
        name = "dummy"

    def unresolved(*_args, **_kwargs):
        raise ingestion.MetadataValidationError("identity needs review", candidate)

    monkeypatch.setattr(ingestion, "WORK_DIR", str(tmp_path / "work"))
    monkeypatch.setattr(
        ingestion, "METADATA_MANIFEST", str(tmp_path / "missing-manifest.json")
    )
    monkeypatch.setattr(ingestion, "STRICT_PUBLICATION", False)
    monkeypatch.setattr(ingestion, "DRY_RUN", False)
    monkeypatch.setattr(ingestion, "discover_sources", lambda: [(source, "act")])
    monkeypatch.setattr(ingestion, "LegalPdfParser", lambda: object())
    monkeypatch.setattr(ingestion, "JinaModelTokenizer", DummyTokenizer)
    monkeypatch.setattr(ingestion, "parse_document", unresolved)

    assert ingestion.run() is None
    reports = sorted((tmp_path / "work" / "runs").glob("run-*.json"))
    report = ingestion.json.loads(
        next(path for path in reports if "manifest-draft" not in path.name).read_text()
    )
    assert report["status"] == "validated_with_quarantine"
    assert report["quarantined_count"] == 1
    assert report["failed_count"] == 0
    assert report["documents"][0]["status"] == "quarantined_metadata"


def test_revision_date_parser_preserves_work_version_separation():
    assert ingestion.revision_date_from_text(
        "The Constitution (As amended up to 31st October 2022) Revised Edition 2023"
    ).isoformat() == "2022-10-31"


def test_structure_chunks_include_parent_identity_and_page_provenance():
    metadata = _metadata()
    markdown = (
        "# PART I\n"
        "1. Short title\nThis Act may be cited as the Example Act.\n"
        + ingestion.PAGE_BREAK
        + "\n2. Application\nThis Act applies throughout Sri Lanka."
    )

    provisions, chunks = ingestion.split_and_chunk(
        markdown,
        metadata,
        ingestion.WhitespaceTokenizer(),
    )

    parents = [chunk for chunk in chunks if chunk.chunk_type == "parent"]
    children = [chunk for chunk in chunks if chunk.chunk_type == "child"]
    assert len(provisions) >= 2
    assert parents and children
    assert all(child.parent_id for child in children)
    assert {child.parent_id for child in children}.issubset(
        {parent.chunk_id for parent in parents}
    )
    assert max(chunk.page_end for chunk in chunks) == 2
    assert len({chunk.chunk_id for chunk in chunks}) == len(chunks)


def test_document_contract_has_one_set_of_ranking_fields_and_child_vector_only():
    metadata = _metadata()
    parent = ingestion.Chunk(
        chunk_id="parent-1",
        expression_id=metadata.expression_id,
        work_id=metadata.work_id,
        source_id=metadata.source_id,
        provision_id="provision-1",
        text="Parent legal context",
        text_hash="parent-hash",
        chunk_type="parent",
        sequence=0,
        token_count=3,
        page_start=1,
        page_end=1,
        source_char_start=0,
        source_char_end=20,
        source_locator_json="{}",
        provision_label="Section 1",
        provision_number="1",
        breadcrumb="Example Act > Section 1",
    )
    child = parent.model_copy(
        update={
            "chunk_id": "child-1",
            "chunk_type": "child",
            "parent_id": "parent-1",
            "embedding": [0.01] * ingestion.EMBEDDING_DIMENSION,
        }
    )

    parent_document = ingestion.chunk_to_document(parent, metadata, "run-1", "release-1")
    child_document = ingestion.chunk_to_document(child, metadata, "run-1", "release-1")

    assert set(ingestion.pinecone_schema()["fields"]) == {
        "title",
        "citation",
        "section_label",
        "body",
        "dense_vector",
    }
    assert "dense_vector" not in parent_document
    assert len(child_document["dense_vector"]) == ingestion.EMBEDDING_DIMENSION
    assert child_document["year"] == 2000
    assert child_document["source_filename"] == "example.pdf"
    assert child_document["corpus_version"] == "release-1"
    ingestion.validate_document_record(parent_document)
    ingestion.validate_document_record(child_document)


def test_quality_gate_rejects_empty_mult_page_extraction():
    quality = ingestion.quality_gate(
        ingestion.PAGE_BREAK.join(["", "", ""]),
        page_count=3,
    )
    assert not quality.passed
    assert quality.text_coverage == 0
    assert quality.warnings


def test_batcher_respects_configured_byte_and_count_limits():
    documents = [
        {
            "_id": f"id-{index}",
            "title": "Example Act",
            "citation": "Act No. 1 of 2000",
            "section_label": f"Section {index}",
            "body": "legal text " * 20,
            "chunk_type": "parent",
        }
        for index in range(ingestion.MAX_UPSERT_DOCUMENTS + 3)
    ]
    batches = list(ingestion.document_batches(documents))
    assert len(batches) == 2
    assert all(len(batch) <= ingestion.MAX_UPSERT_DOCUMENTS for batch in batches)
    assert all(ingestion.json_size(batch) < ingestion.MAX_UPSERT_BYTES for batch in batches)
