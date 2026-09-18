from pathlib import Path

from app.rag.ingestion.prepared_adapter import PreparedRagDatasetAdapter


def test_prepared_sample_loads():
    root = Path(__file__).resolve().parents[3] / "data" / "prepared_sample"
    adapter = PreparedRagDatasetAdapter(root)
    ids = adapter.source_ids()
    assert len(ids) == 3
    source, chunks = adapter.get(ids[0])
    assert source.source_id == ids[0]
    assert chunks
    assert all(chunk.page_start > 0 for chunk in chunks)
