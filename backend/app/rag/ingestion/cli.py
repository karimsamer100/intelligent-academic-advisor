from __future__ import annotations

import argparse
import json
from pathlib import Path
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.rag.chunkers.section_chunker import SectionAwarePageChunker
from app.rag.cleaners.academic_text_cleaner import AcademicTextCleaner
from app.rag.embeddings.hash_test_provider import HashTestEmbeddingProvider
from app.rag.embeddings.sentence_transformer import SentenceTransformerEmbeddingProvider
from app.rag.extractors.foundation_extractor import FoundationExtractedTextExtractor
from app.rag.extractors.pymupdf_extractor import PyMuPDFExtractor
from app.rag.ingestion.foundation_adapter import AcademicDataFoundationAdapter
from app.rag.ingestion.pipeline import RagIngestionPipeline
from app.rag.ingestion.prepared_adapter import PreparedRagDatasetAdapter
from app.rag.metadata.enricher import MetadataEnricher
from app.rag.repositories.memory_repository import MemoryChunkRepository
from app.rag.retrieval.service import DocumentSearchService

DEFAULT_SUBSET = [
    "SRC-CESS_NEW_BYLAW_2018_PDF",
    "SRC-BYLAW_2023_GENERAL_RULES_REGULATIONS_UEL_PDF",
    "SRC-STUDENT_S_GUIDLINE_BOOKLET_V1_5_PDF",
]


def _common_pipeline(extractor, embedder, repository):
    settings = get_settings()
    return RagIngestionPipeline(
        extractor=extractor,
        cleaner=AcademicTextCleaner(),
        chunker=SectionAwarePageChunker(settings.chunk_size, settings.chunk_overlap, settings.chunk_min_chars),
        enricher=MetadataEnricher(),
        embedder=embedder,
        repository=repository,
        pipeline_version=settings.pipeline_version,
        preserve_raw_extraction=settings.preserve_raw_extraction,
        raw_extract_dir=settings.raw_extract_dir,
    )


def _source_ids(args, adapter: AcademicDataFoundationAdapter) -> list[str]:
    if args.all_rag_sources:
        return [x["source_id"] for x in adapter.list_sources(True)]
    if args.source_id:
        return args.source_id
    return DEFAULT_SUBSET


def prepare_foundation(args) -> int:
    adapter = AcademicDataFoundationAdapter(Path(args.foundation_path))
    extractor = FoundationExtractedTextExtractor() if not args.fresh_extraction else PyMuPDFExtractor()
    pipeline = _common_pipeline(extractor, HashTestEmbeddingProvider(), MemoryChunkRepository())
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    source_rows = []
    for source_id in _source_ids(args, adapter):
        metadata = adapter.metadata(source_id)
        input_path = adapter.document_path(source_id) if args.fresh_extraction else adapter.extracted_text_path(source_id)
        metadata, chunks = pipeline.prepare_without_embeddings(metadata, input_path)
        source_rows.append(metadata.model_dump(mode="json"))
        manifest.extend(chunks)
    (out_dir / "source_registry.json").write_text(json.dumps(source_rows, indent=2, ensure_ascii=False), encoding="utf-8")
    with (out_dir / "chunks.jsonl").open("w", encoding="utf-8") as handle:
        for row in manifest:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    report = {
        "status": "PASS",
        "sources": len(source_rows),
        "chunks": len(manifest),
        "source_ids": [x["source_id"] for x in source_rows],
        "fresh_extraction": bool(args.fresh_extraction),
    }
    (out_dir / "prepare_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


def ingest_foundation(args) -> int:
    from app.db.session import session_scope
    from app.rag.repositories.pgvector_repository import PgVectorChunkRepository
    settings = get_settings()
    adapter = AcademicDataFoundationAdapter(Path(args.foundation_path))
    extractor = FoundationExtractedTextExtractor() if not args.fresh_extraction else PyMuPDFExtractor()
    embedder = SentenceTransformerEmbeddingProvider(
        settings.embedding_model,
        device=settings.embedding_device,
        expected_dimension=settings.embedding_dimension,
        cache_dir=settings.embedding_cache_dir,
        batch_size=settings.embedding_batch_size,
    )
    results = []
    with session_scope() as session:
        repository = PgVectorChunkRepository(session)
        pipeline = _common_pipeline(extractor, embedder, repository)
        for source_id in _source_ids(args, adapter):
            metadata = adapter.metadata(source_id)
            input_path = adapter.document_path(source_id) if args.fresh_extraction else adapter.extracted_text_path(source_id)
            results.append(pipeline.ingest(metadata, input_path).model_dump(mode="json"))
    print(json.dumps(results, indent=2, ensure_ascii=False))
    return 0


def ingest_prepared(args) -> int:
    from app.db.session import session_scope
    from app.rag.repositories.pgvector_repository import PgVectorChunkRepository

    settings = get_settings()
    adapter = PreparedRagDatasetAdapter(Path(args.prepared_dir))
    embedder = SentenceTransformerEmbeddingProvider(
        settings.embedding_model,
        device=settings.embedding_device,
        expected_dimension=settings.embedding_dimension,
        cache_dir=settings.embedding_cache_dir,
        batch_size=settings.embedding_batch_size,
    )
    selected = args.source_id or adapter.source_ids()
    results = []
    with session_scope() as session:
        pipeline = _common_pipeline(FoundationExtractedTextExtractor(), embedder, PgVectorChunkRepository(session))
        for source_id in selected:
            source, chunks = adapter.get(source_id)
            results.append(pipeline.ingest_prepared(source, chunks).model_dump(mode="json"))
    print(json.dumps(results, indent=2, ensure_ascii=False))
    return 0


def search(args) -> int:
    from app.db.session import session_scope
    from app.rag.repositories.pgvector_repository import PgVectorChunkRepository
    settings = get_settings()
    embedder = SentenceTransformerEmbeddingProvider(
        settings.embedding_model,
        device=settings.embedding_device,
        expected_dimension=settings.embedding_dimension,
        cache_dir=settings.embedding_cache_dir,
        batch_size=settings.embedding_batch_size,
    )
    with session_scope() as session:
        service = DocumentSearchService(
            embedder=embedder,
            repository=PgVectorChunkRepository(session),
            default_top_k=settings.rag_top_k,
            max_top_k=settings.rag_max_top_k,
            min_score=settings.rag_min_score,
        )
        results = service.search_documents(
            args.query,
            regulation=args.regulation,
            program=args.program,
            document_types=args.document_type,
            language=args.language,
            official_status=args.official_status,
            top_k=args.top_k,
        )
        print(json.dumps([r.model_dump(mode="json") for r in results], indent=2, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local Intelligent Academic Advisor - RAG v0 CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_source_args(p):
        p.add_argument("--foundation-path", required=True, help="Path to data-foundation-submission")
        p.add_argument("--source-id", action="append", help="Repeat to select multiple sources")
        p.add_argument("--all-rag-sources", action="store_true")
        p.add_argument("--fresh-extraction", action="store_true", help="Read original PDFs with PyMuPDF instead of reusing the foundation page extraction")

    prep = sub.add_parser("prepare-foundation", help="Build enriched chunks without embeddings/DB for inspection")
    add_source_args(prep)
    prep.add_argument("--output-dir", default="/data/prepared_rag")
    prep.set_defaults(func=prepare_foundation)

    ingest = sub.add_parser("ingest-foundation", help="Embed and ingest selected Academic Data Foundation sources")
    add_source_args(ingest)
    ingest.set_defaults(func=ingest_foundation)

    prepared = sub.add_parser("ingest-prepared", help="Embed and ingest an already prepared RAG dataset")
    prepared.add_argument("--prepared-dir", required=True, help="Directory containing source_registry.json and chunks.jsonl")
    prepared.add_argument("--source-id", action="append", help="Repeat to select specific prepared sources; default is all")
    prepared.set_defaults(func=ingest_prepared)

    search_cmd = sub.add_parser("search", help="Run evidence retrieval against PostgreSQL + pgvector")
    search_cmd.add_argument("query")
    search_cmd.add_argument("--regulation", type=int)
    search_cmd.add_argument("--program")
    search_cmd.add_argument("--document-type", action="append")
    search_cmd.add_argument("--language")
    search_cmd.add_argument("--official-status")
    search_cmd.add_argument("--top-k", type=int)
    search_cmd.set_defaults(func=search)
    return parser


def main() -> int:
    settings = get_settings()
    configure_logging(settings.log_level)
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
