from app.rag.chunkers.section_chunker import SectionAwarePageChunker
from app.rag.models.domain import DocumentMetadata, ExtractedDocument, PageText


def metadata():
    return DocumentMetadata(
        source_id="SRC-2023",
        file_name="bylaw.pdf",
        document_title="Bylaw",
        document_types=["Full Academic Regulation"],
        regulations=[2023],
        programs=["CAIE"],
        official_status="OFFICIAL",
        file_hash="a" * 64,
    )


def test_chunker_never_crosses_page_boundaries():
    doc = ExtractedDocument(
        source_id="SRC-2023",
        extraction_method="test",
        pages=[
            PageText(page_number=8, text="Course Registration Rules\n" + "Credit rules text. " * 80),
            PageText(page_number=9, text="Graduation Requirements\n" + "Graduation text. " * 80),
        ],
    )
    chunks = SectionAwarePageChunker(max_chars=300, overlap_chars=40, min_chars=40).chunk(doc, metadata())
    assert chunks
    assert all(c.page_start == c.page_end for c in chunks)
    assert {c.page_start for c in chunks} == {8, 9}
    assert len({c.chunk_id for c in chunks}) == len(chunks)


def test_short_final_text_is_not_dropped():
    doc = ExtractedDocument(
        source_id="SRC-2023",
        extraction_method="test",
        pages=[PageText(page_number=1, text="Registration Rules\n" + "A" * 310 + "\nEND")],
    )
    chunks = SectionAwarePageChunker(max_chars=220, overlap_chars=30, min_chars=80).chunk(doc, metadata())
    assert any("END" in c.text for c in chunks)
