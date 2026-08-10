from __future__ import annotations

from pathlib import Path
import sys

import pytest
from pydantic import ValidationError


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

import act_and_case_law_ingestion_process_neo4j as ingestion
from app.services.retrieval.neo4j_queries import CHUNK_PROJECTION, GRAPH_TRAVERSAL_QUERY
from app.services.retrieval.neo4j_graph_store import _as_of_value, _lucene_escape


def _source(tmp_path: Path, name: str = "Evidence-Consolidated-2024.pdf") -> Path:
    path = tmp_path / name
    path.write_bytes(b"synthetic test source")
    return path


def test_consolidated_base_instrument_wins_and_year_is_not_fabricated(tmp_path):
    path = _source(tmp_path)
    markdown = """# THE EVIDENCE ORDINANCE
    Ordinances,
    Nos. 14 of 1895
    Amended by the EVIDENCE (AMENDMENT) ACT No. 12 OF 2020
    1. This Ordinance may be cited as the Evidence Ordinance.
    """

    metadata = ingestion.extract_metadata(
        path, markdown, "a" * 64, None, {}
    )

    assert metadata.source_type == "ordinance"
    assert metadata.work_year == 1895
    assert metadata.instrument_number == "14"
    assert metadata.version_date is None
    assert metadata.version_year == 2024
    assert metadata.version_precision == "year"
    assert metadata.valid_from is None


def test_act_number_parser_tolerates_official_spacing_around_no(tmp_path):
    path = _source(tmp_path, "Money_Laundering_Act_2006-5_(English).pdf")
    metadata = ingestion.extract_metadata(
        path,
        "PREVENTION OF MONEY LAUNDERING ACT, No . 5 OF 2006",
        "e" * 64,
        None,
        {},
    )
    assert metadata.source_type == "act"
    assert metadata.work_year == 2006
    assert metadata.instrument_number == "5"
    assert metadata.title == "Prevention Of Money Laundering Act"


def test_constitution_identity_is_not_overridden_by_amending_act_citations(tmp_path):
    path = _source(tmp_path, "constitution.pdf")
    metadata = ingestion.extract_metadata(
        path,
        """The Constitution of the Democratic Socialist Republic of Sri Lanka
        (As amended up to 31st October 2022)
        Revised Edition - 2023
        TWENTY FIRST AMENDMENT ACT, NO. 1 OF 2022
        """,
        "1" * 64,
        None,
        {},
    )
    assert metadata.source_type == "constitution"
    assert metadata.title == (
        "The Constitution of the Democratic Socialist Republic of Sri Lanka"
    )
    assert metadata.work_id == "lk:constitution:lk"
    assert metadata.version_year == 2023
    assert metadata.identity_status == "resolved"


def test_partition_law_is_not_misidentified_as_first_amending_act(tmp_path):
    path = _source(tmp_path, "Partition-Consolidated-2024.pdf")
    metadata = ingestion.extract_metadata(
        path,
        """PARTITION
        A LAW TO PROVIDE FOR THE PARTITION AND SALE OF LAND HELD IN COMMON.
        Law Nos, 21 of 1977
        Act Nos, 5 of 1981
        1. This Law may be cited as the Partition Law.
        """,
        "2" * 64,
        None,
        {},
    )
    assert metadata.source_type == "law"
    assert metadata.work_year == 1977
    assert metadata.instrument_number == "21"
    assert metadata.title == "Partition Law"
    assert metadata.work_id == "lk:law:1977:21"


def test_short_title_citation_wins_over_consolidated_amendment_list(tmp_path):
    path = _source(tmp_path, "Electronic-Transactions-Consolidated-2024.pdf")
    metadata = ingestion.extract_metadata(
        path,
        """Electronic Transactions
        Act Nos, 25 of 2017
        1. (1) This Act may be cited as the Electronic Transactions Act,
        No. 19 of 2006.
        """,
        "7" * 64,
        None,
        {},
    )
    assert metadata.source_type == "act"
    assert metadata.title == "Electronic Transactions Act"
    assert metadata.work_year == 2006
    assert metadata.instrument_number == "19"
    assert metadata.work_id == "lk:act:2006:19"
    assert metadata.identity_status == "resolved"


def test_ordinance_short_title_and_ocr_year_are_recovered(tmp_path):
    path = _source(tmp_path, "sog93171.pdf")
    metadata = ingestion.extract_metadata(
        path,
        """SALE OF GOODS
        Ordinance No. 11 of ! 896.
        1. This Ordinanc e ma y be cited a s th e Sale of Goods Ordinance.
        """,
        "8" * 64,
        None,
        {},
    )
    assert metadata.source_type == "ordinance"
    assert metadata.title == "Sale of Goods Ordinance"
    assert metadata.work_year == 1896
    assert metadata.instrument_number == "11"
    assert metadata.work_id == "lk:ordinance:1896:11"
    assert metadata.identity_status == "resolved"


def test_publication_requires_authoritative_manifest_and_exact_current_version(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(ingestion, "REQUIRE_MANIFEST_FOR_PUBLICATION", True)
    monkeypatch.setattr(ingestion, "REQUIRE_AUTHORITATIVE_SOURCE", True)
    path = _source(tmp_path, "Act-No-1-of-2020.pdf")
    metadata = ingestion.extract_metadata(
        path,
        "CONTRACT ACT No. 1 OF 2020",
        "b" * 64,
        "act",
        {},
    )
    with pytest.raises(ingestion.IngestionError, match="metadata manifest entry"):
        ingestion.validate_publication_metadata(metadata, {}, publication=True)

    override = {
        "source_type": "act",
        "title": "Contract Act",
        "work_year": 2020,
        "instrument_number": "1",
        "version_date": "2025-03-10",
        "source_uri": "https://documents.gov.lk/example.pdf",
        "source_authority": "Government of Sri Lanka",
        "source_publisher": "Department of Government Printing",
        "source_license": "official-public-record",
        "authoritative": True,
    }
    metadata = ingestion.extract_metadata(
        path, "CONTRACT ACT No. 1 OF 2020", "b" * 64, "act", override
    )
    ingestion.validate_publication_metadata(metadata, override, publication=True)


def test_missing_manifest_dry_run_enters_non_publication_bootstrap(monkeypatch):
    monkeypatch.setattr(ingestion, "DRY_RUN", True)
    monkeypatch.setattr(ingestion, "WRITE_MANIFEST_REVIEW_TEMPLATE", True)
    assert ingestion.is_manifest_bootstrap({}) is True
    assert ingestion.is_manifest_bootstrap({"document.pdf": {}}) is False

    monkeypatch.setattr(ingestion, "DRY_RUN", False)
    assert ingestion.is_manifest_bootstrap({}) is False


def test_manifest_review_entry_exposes_missing_fields_without_claiming_authority(
    tmp_path,
):
    path = _source(tmp_path, "37-2005_E.pdf")
    metadata = ingestion.extract_metadata(
        path,
        "A v. B\nS.C. Appeal No. 37/2005",
        "f" * 64,
        "case_law",
        {},
    )
    entry = ingestion.manifest_review_entry(
        path, metadata, {}, ["publication metadata missing/invalid: court"]
    )
    assert entry["court"] is None
    assert entry["authoritative"] is False
    assert entry["_review_status"] == "needs_human_review"
    assert "court" in entry["_validation_errors"][0]


def test_legislation_discovery_does_not_force_every_pdf_to_act(
    tmp_path, monkeypatch
):
    acts = tmp_path / "Contract Law Acts"
    cases = tmp_path / "Contract Case Laws"
    acts.mkdir()
    cases.mkdir()
    (acts / "constitution.pdf").write_bytes(b"constitution")
    (cases / "appeal.pdf").write_bytes(b"case law")
    monkeypatch.setattr(ingestion, "ACTS_DIR", str(acts))
    monkeypatch.setattr(ingestion, "CASES_DIR", str(cases))

    hints = {path.name: hint for path, hint in ingestion.discover_sources()}

    assert hints == {"constitution.pdf": None, "appeal.pdf": "case_law"}


def test_low_page_coverage_waiver_is_narrow_audited_and_source_bound(tmp_path):
    path = _source(tmp_path, "intentional-blank-page.pdf")
    source_sha256 = ingestion.file_hash(path)
    quality = ingestion.quality_gate("operative words " * 80, 2)
    assert quality.passed is False

    accepted = ingestion.apply_quality_waiver(
        path,
        quality,
        {
            "accept_low_page_coverage": True,
            "quality_override_reason": "Page 2 was visually verified as blank.",
            "source_sha256": source_sha256,
        },
        source_sha256,
    )

    assert accepted.passed is True
    assert accepted.waived is True
    assert accepted.text_coverage == 0.5
    assert accepted.waiver_reason == "Page 2 was visually verified as blank."


@pytest.mark.parametrize(
    "override, expected_error",
    [
        (
            {
                "accept_low_page_coverage": True,
                "source_sha256": "a" * 64,
            },
            "quality_override_reason",
        ),
        (
            {
                "accept_low_page_coverage": True,
                "quality_override_reason": "Reviewed",
                "source_sha256": "a" * 64,
            },
            "source_sha256 changed",
        ),
    ],
)
def test_low_page_coverage_waiver_rejects_unsafe_manifest_entries(
    tmp_path, override, expected_error
):
    path = _source(tmp_path, "unreviewed.pdf")
    quality = ingestion.quality_gate("operative words " * 80, 2)
    with pytest.raises(ingestion.IngestionError, match=expected_error):
        ingestion.apply_quality_waiver(
            path, quality, override, ingestion.file_hash(path)
        )


def test_manifest_decisions_are_invalidated_when_source_bytes_change(tmp_path):
    path = _source(tmp_path, "reviewed.pdf")
    reviewed_sha256 = ingestion.file_hash(path)
    ingestion.validate_manifest_source_digest(
        path, {"source_sha256": reviewed_sha256}
    )

    path.write_bytes(b"replacement source")
    with pytest.raises(ingestion.IngestionError, match="does not match the PDF"):
        ingestion.validate_manifest_source_digest(
            path, {"source_sha256": reviewed_sha256}
        )


def test_inline_page_break_preserves_both_sides_and_child_page_spans(tmp_path):
    path = _source(tmp_path, "Act-No-2-of-2021.pdf")
    override = {
        "source_type": "act",
        "title": "Test Act",
        "work_year": 2021,
        "instrument_number": "2",
        "version_date": "2021-01-01",
    }
    metadata = ingestion.extract_metadata(
        path, "TEST ACT No. 2 OF 2021", "c" * 64, "act", override
    )
    markdown = (
        "1. First provision\nText before the marker "
        + ingestion.PAGE_BREAK
        + " text after the marker. "
        + "operative words " * 350
    )

    _, chunks = ingestion.split_and_chunk(markdown, metadata)
    combined = " ".join(chunk.text for chunk in chunks)
    assert "Text before the marker" in combined
    assert "text after the marker" in combined
    child_pages = {(c.page_start, c.page_end) for c in chunks if c.chunk_type == "child"}
    assert any(page_end >= 2 for _, page_end in child_pages)


def test_markdown_tables_are_separate_structural_provisions(tmp_path):
    path = _source(tmp_path, "Act-No-3-of-2022.pdf")
    metadata = ingestion.extract_metadata(
        path,
        "TEST ACT No. 3 OF 2022",
        "d" * 64,
        "act",
        {
            "source_type": "act",
            "title": "Test Act",
            "work_year": 2022,
            "instrument_number": "3",
            "version_date": "2022-01-01",
        },
    )
    provisions, _ = ingestion.split_and_chunk(
        "1. Fees\n| Class | Fee |\n| --- | --- |\n| A | 100 |\nText after table.",
        metadata,
    )
    assert [item.kind for item in provisions].count("table") == 1
    table = next(item for item in provisions if item.kind == "table")
    assert table.label == "Table 1"
    assert provisions[-1].kind == "section"


def test_low_coverage_parse_retries_with_full_page_ocr(tmp_path, monkeypatch):
    path = _source(tmp_path, "Retry-Act.pdf")

    class FakeParser:
        def __init__(self, full_page: bool):
            self.force_full_page_ocr = full_page
            self.config_hash = "full" if full_page else "selective"

    selective = FakeParser(False)
    full_page = FakeParser(True)
    body = "operative provision words " * 80

    def fake_convert(_path, _cache, parser):
        markdown = (
            f"RETRY ACT No. 2 OF 2020\n1. Rule\n{body}"
            if not parser.force_full_page_ocr
            else (
                f"RETRY ACT No. 2 OF 2020\n1. Rule\n{body}"
                + ingestion.PAGE_BREAK
                + body
            )
        )
        return markdown, 2, "3" * 64, None

    monkeypatch.setattr(ingestion, "convert_pdf", fake_convert)
    document = ingestion.parse_document(
        path,
        "act",
        {},
        tmp_path,
        selective,
        full_page,
        publication=False,
        allow_identity_candidate=True,
    )
    assert document.quality.text_coverage == 1.0
    assert document.metadata.parser_config_hash == "full"


def test_strictly_blank_pdf_page_is_not_counted_as_failed_ocr_coverage():
    quality = ingestion.quality_gate(
        "operative provision words " * 80,
        page_count=2,
        blank_pages=[2],
    )
    assert quality.page_count == 2
    assert quality.substantive_page_count == 1
    assert quality.blank_pages == [2]
    assert quality.text_coverage == 1.0
    assert quality.passed is True


def test_document_set_conflicts_identify_every_affected_source(tmp_path):
    first_path = _source(tmp_path, "first.pdf")
    second_path = _source(tmp_path, "second.pdf")
    common_override = {
        "source_type": "act",
        "title": "Conflict Act",
        "work_year": 2020,
        "instrument_number": "8",
        "version_year": 2020,
    }

    def document(path, sha):
        metadata = ingestion.extract_metadata(
            path, "CONFLICT ACT No. 8 OF 2020", sha, "act", common_override
        )
        provisions, chunks = ingestion.split_and_chunk(
            "1. Rule\n" + "operative words " * 80, metadata
        )
        return ingestion.ParsedDocument(
            metadata=metadata,
            quality=ingestion.quality_gate("operative words " * 80, 1),
            provisions=provisions,
            chunks=chunks,
        )

    conflicts = ingestion.collect_document_set_conflicts(
        [document(first_path, "4" * 64), document(second_path, "5" * 64)]
    )
    assert len(conflicts) == 2
    assert all("same legal work/version" in errors[0] for errors in conflicts.values())


def test_extraction_contract_rejects_invalid_legal_treatments_and_dates():
    with pytest.raises(ValidationError):
        ingestion.StatuteCitation(
            target_title="Evidence Ordinance",
            treatment="probably_applies",
            evidence_quote="Evidence Ordinance",
        )
    with pytest.raises(ValidationError):
        ingestion.Amendment(
            operation="amends",
            target_title="Evidence Ordinance",
            effective_date="not-a-date",
            evidence_quote="is amended",
        )


def test_backend_traverses_canonical_assertions_without_shipping_vectors():
    assert "GroundedAssertion" in GRAPH_TRAVERSAL_QUERY
    assert "TARGETS_PROVISION" in GRAPH_TRAVERSAL_QUERY
    assert "candidate_expression.publication_status = 'published'" in GRAPH_TRAVERSAL_QUERY
    assert "type(amendment_rel) IN $amendment_relationship_types" in GRAPH_TRAVERSAL_QUERY
    assert ".embedding," not in CHUNK_PROJECTION
    assert "embedding: null" not in CHUNK_PROJECTION


def test_retrieval_validates_historical_dates_and_escapes_lucene_syntax():
    assert _as_of_value("2024-02-29") == "2024-02-29"
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        _as_of_value("29/02/2024")
    assert _lucene_escape("section 12(1): duty") == r"section 12\(1\)\: duty"


def test_notebook_has_ambiguity_detection_safe_migration_and_source_aware_resume():
    source = (REPOSITORY_ROOT / "act_and_case_law_ingestion_process_neo4j.py").read_text(
        encoding="utf-8"
    )
    assert "head(collect(target))" not in source
    assert "resolution_status=CASE WHEN size(targets)=0" in source
    assert "BACKUP_REFERENCE" in source
    assert "MAX_DOCUMENT_EMBEDDING_BYTES" in source
    assert "(:SourceFile {source_id:$source_id})" in source


def test_legacy_launchers_contain_no_default_password_or_remote_tunnel():
    scripts = REPOSITORY_ROOT / "backend" / "scripts"
    paths = [scripts / "ingest_to_neo4j.py", scripts / "test_hybrid_search.py"]
    text = "\n".join(
        path.read_text(encoding="utf-8") for path in paths if path.exists()
    )
    assert "lankalawbot2026" not in text
    assert "tcp.in.ngrok.io" not in text
