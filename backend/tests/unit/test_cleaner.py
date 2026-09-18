from app.rag.cleaners.academic_text_cleaner import AcademicTextCleaner
from app.rag.models.domain import ExtractedDocument, PageText


def test_cleaner_removes_only_repeated_page_edges_and_preserves_numbers():
    doc = ExtractedDocument(
        source_id="SRC",
        extraction_method="test",
        pages=[
            PageText(page_number=1, text="Ain Shams University\nRegistration Rules\nGPA >= 3.0: up to 21 credit hours\nPage footer"),
            PageText(page_number=2, text="Ain Shams University\nOther Rules\nMaximum duration is 8 years\nPage footer"),
            PageText(page_number=3, text="Ain Shams University\nGraduation\nComplete 170 credit hours\nPage footer"),
        ],
    )
    cleaned = AcademicTextCleaner(boilerplate_edge_lines=1, repeated_ratio=0.66).clean(doc)
    assert all("Ain Shams University" not in p.text for p in cleaned.pages)
    assert all("Page footer" not in p.text for p in cleaned.pages)
    assert "21 credit hours" in cleaned.pages[0].text
    assert "8 years" in cleaned.pages[1].text
    assert "170 credit hours" in cleaned.pages[2].text
