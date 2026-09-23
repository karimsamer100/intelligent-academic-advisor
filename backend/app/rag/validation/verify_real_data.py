"""Audit prepared data and rerun full/fresh preparation when originals are installed."""
import argparse
import json
from collections import Counter
from pathlib import Path
import fitz
from app.rag.ingestion.cli import DEFAULT_SUBSET, _common_pipeline
from app.rag.ingestion.foundation_adapter import AcademicDataFoundationAdapter
from app.rag.ingestion.prepared_adapter import PreparedRagDatasetAdapter
from app.rag.embeddings.hash_test_provider import HashTestEmbeddingProvider
from app.rag.extractors.foundation_extractor import FoundationExtractedTextExtractor
from app.rag.extractors.pymupdf_extractor import PyMuPDFExtractor
from app.rag.metadata.enricher import MetadataEnricher
from app.rag.metadata.taxonomy import canonical_document_type
from app.rag.models.domain import ChunkDraft
from app.rag.repositories.memory_repository import MemoryChunkRepository
from app.rag.validation.validators import validate_chunks


def audit(rows):
    ids = []
    counts = Counter()
    for source, chunks in rows:
        validate_chunks(chunks, source)
        ids.extend(c.chunk_id for c in chunks)
        counts['sources'] += 1
        for c in chunks:
            counts['chunks'] += 1
            for field, applicability, supported in [
                ('regulation', 'applicable_regulations', source.regulations),
                ('program', 'applicable_programs', source.programs),
                ('document_type', 'applicable_document_types',
                 [canonical_document_type(t) for t in source.document_types if canonical_document_type(t)])]:
                specific = getattr(c, field)
                expected = [specific] if specific is not None else list(dict.fromkeys(supported))
                assert getattr(c, applicability) == expected, f'{c.chunk_id}: invalid {applicability}'
            for field, supported in [('regulation', source.regulations), ('program', source.programs),
                                     ('document_type', source.document_types)]:
                if len(supported) > 1:
                    counts[f'{field}_multi_source_narrowed' if getattr(c, field) is not None
                           else f'{field}_multi_source_shared'] += 1
    assert len(ids) == len(set(ids)), 'duplicate chunk IDs'
    return dict(status='PASS', **counts, unique_chunk_ids=len(set(ids)), duplicate_chunk_ids=0,
                empty_chunks=0, invalid_page_metadata=0, unexpected_applicability_expansion=0)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--foundation-path', type=Path, required=True)
    parser.add_argument('--prepared-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    adapter = PreparedRagDatasetAdapter(args.prepared_dir)
    rows = []
    for sid in adapter.source_ids():
        source, chunks = adapter.get(sid)
        rows.append((source, [MetadataEnricher().enrich(c, source) for c in chunks]))
    report = {'prepared_sample_reenrichment': audit(rows)}
    try:
        foundation = AcademicDataFoundationAdapter(args.foundation_path)
        pipeline = _common_pipeline(FoundationExtractedTextExtractor(), HashTestEmbeddingProvider(), MemoryChunkRepository())
        rows = []
        for item in foundation.list_sources(True):
            sid = item['source_id']
            source, chunks = pipeline.prepare_without_embeddings(foundation.metadata(sid), foundation.extracted_text_path(sid))
            rows.append((source, [ChunkDraft.model_validate(c) for c in chunks]))
        report['full_corpus_preparation'] = audit(rows)
    except Exception as exc:
        report['full_corpus_preparation'] = dict(status='BLOCKED', error=f'{type(exc).__name__}: {exc}')
    try:
        foundation = AcademicDataFoundationAdapter(args.foundation_path)
        pipeline = _common_pipeline(PyMuPDFExtractor(), HashTestEmbeddingProvider(), MemoryChunkRepository())
        pipeline.preserve_raw_extraction = True
        pages = []
        rows = []
        for sid in DEFAULT_SUBSET:
            path = foundation.document_path(sid)
            with fitz.open(path) as pdf:
                expected_pages = len(pdf)
            source, chunks = pipeline.prepare_without_embeddings(foundation.metadata(sid), path)
            debug = json.loads((pipeline.raw_extract_dir / f'{sid}.json').read_text(encoding='utf-8'))
            assert [p['page_number'] for p in debug['pages']] == list(range(1, expected_pages + 1))
            empty = [p['page_number'] for p in debug['pages'] if not p['text'].strip()]
            assert all(f'empty_page:{page}' in debug['extraction_warnings'] for page in empty)
            assert all(c['page_start'] == c['page_end'] for c in chunks)
            rows.append((source, [ChunkDraft.model_validate(c) for c in chunks]))
            pages.append(dict(source_id=sid, pages_traversed=expected_pages, empty_pages=empty, raw_debug_verified=True))
        report['fresh_pdf_extraction'] = dict(audit(rows), documents=pages)
    except Exception as exc:
        report['fresh_pdf_extraction'] = dict(status='BLOCKED', error=f'{type(exc).__name__}: {exc}')
    report['status'] = 'PASS' if all(v['status'] == 'PASS' for v in report.values()) else 'INCOMPLETE'
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
    return 0 if report['status'] == 'PASS' else 2


if __name__ == '__main__':
    raise SystemExit(main())
