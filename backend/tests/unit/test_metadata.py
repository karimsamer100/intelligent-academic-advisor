from app.rag.metadata.enricher import MetadataEnricher
from app.rag.models.domain import ChunkDraft, DocumentMetadata


def source(regs, programs):
    return DocumentMetadata(
        source_id="SRC",
        file_name="x.pdf",
        document_title="X",
        document_types=["Training Handbook"],
        regulations=regs,
        programs=programs,
        official_status="COLLECTED_INSTITUTIONAL_SOURCE",
        file_hash="b" * 64,
    )


def draft(text):
    return ChunkDraft(
        chunk_id="C1",
        source_id="SRC",
        text=text,
        page_start=1,
        page_end=1,
        chunk_index=1,
        text_hash="c" * 64,
    )


def test_metadata_narrows_multi_regulation_only_when_text_supports_it():
    enricher = MetadataEnricher()
    narrowed = enricher.enrich(draft("Bylaw 2023 field training requirements"), source([2018, 2023], []))
    assert narrowed.regulation == 2023
    assert narrowed.applicable_regulations == [2018, 2023]

    ambiguous = enricher.enrich(draft("Field training requirements"), source([2018, 2023], []))
    assert ambiguous.regulation is None
    assert ambiguous.applicable_regulations == [2018, 2023]


def test_language_detection_supports_arabic_english_and_mixed():
    e = MetadataEnricher()
    assert e.detect_language("Course registration rules") == "en"
    assert e.detect_language("قواعد تسجيل المقررات") == "ar"
    assert e.detect_language("Course تسجيل rules المقررات") == "mixed"


def test_multi_document_type_source_keeps_explicit_applicability_without_forcing_ambiguity():
    e = MetadataEnricher()
    src = DocumentMetadata(
        source_id="SRC-MULTI",
        file_name="multi.pdf",
        document_title="Multi",
        document_types=["Full Academic Regulation", "Training Handbook"],
        regulations=[2023],
        programs=[],
        official_status="OFFICIAL",
        file_hash="d" * 64,
    )
    chunk = ChunkDraft(
        chunk_id="C2", source_id="SRC-MULTI", text="General introductory material",
        page_start=1, page_end=1, chunk_index=1, text_hash="e" * 64,
    )
    out = e.enrich(chunk, src)
    assert out.document_type is None
    assert set(out.applicable_document_types) == {"REGULATION", "TRAINING_HANDBOOK"}
