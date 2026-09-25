"""Persisted-corpus, unchanged re-ingestion, real API, and score verification."""
import argparse
import json
import math
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.session import session_scope
from app.main import app
from app.rag.provider import get_embedding_provider
from app.rag.extractors.foundation_extractor import FoundationExtractedTextExtractor
from app.rag.ingestion.cli import _common_pipeline
from app.rag.ingestion.foundation_adapter import AcademicDataFoundationAdapter
from app.rag.models.domain import ChunkDraft
from app.rag.models.orm import RagChunk, RagSource
from app.rag.repositories.pgvector_repository import PgVectorChunkRepository
from app.rag.retrieval.service import DocumentSearchService
from app.rag.validation.validators import validate_chunks


def audit_corpus(session, foundation, provider):
    repository = PgVectorChunkRepository(session)
    pipeline = _common_pipeline(FoundationExtractedTextExtractor(), provider, repository)
    pipeline.preserve_raw_extraction = False
    report = []
    for item in foundation.list_sources(True):
        sid = item['source_id']
        source, expected_rows = pipeline.prepare_without_embeddings(
            foundation.metadata(sid), foundation.extracted_text_path(sid))
        expected = {row['chunk_id']: ChunkDraft.model_validate(row) for row in expected_rows}
        stored = session.scalars(select(RagChunk).where(RagChunk.source_id == sid)).all()
        state = repository.get_source_state(sid)
        assert state is not None and state.file_hash == source.file_hash, sid
        assert state.pipeline_version == pipeline.pipeline_version, sid
        assert state.embedding_model == provider.model_name, sid
        assert state.chunk_count == state.expected_chunk_count == len(expected) == len(stored), sid
        assert {c.chunk_id for c in stored} == set(expected), sid
        actual_drafts = []
        for chunk in stored:
            fields = expected[chunk.chunk_id].model_dump()
            # Provenance annotations are JSON; compare all draft fields including text and scope.
            actual = {key: chunk.chunk_metadata if key == 'metadata' else getattr(chunk, key) for key in fields}
            assert actual == fields, f'{sid}: persisted draft mismatch: {chunk.chunk_id}'
            assert chunk.embedding_model == provider.model_name
            assert chunk.pipeline_version == pipeline.pipeline_version
            assert len(chunk.embedding) == provider.dimension
            assert all(math.isfinite(float(x)) for x in chunk.embedding)
            assert any(float(x) != 0 for x in chunk.embedding)
            actual_drafts.append(ChunkDraft.model_validate(actual))
        validate_chunks(actual_drafts, source)
        report.append(dict(source_id=sid, status='PASS', chunks=len(stored),
                           file_hash=source.file_hash, pipeline_version=state.pipeline_version))
    return dict(status='PASS', sources=len(report), chunks=sum(r['chunks'] for r in report), rows=report)


def evaluate(service, cases):
    positives = [dict(c, label='supported', origin='existing_smoke') for c in cases if c.get('expected_source')]
    variants = [
        'With a GPA of 3.2, what is the maximum credit load in a fall semester?',
        'How many credit hours may I take in spring if my cumulative GPA is at least three?',
        'Under Regulation 2018, what is the maximum number of years allowed to finish my studies?',
        'Under Regulation 2023, how long may a student take to complete the program?',
        'Who is the next contact when the course instructor cannot resolve a portfolio issue?',
    ]
    for case, query in zip(positives[:], variants):
        positives.append(dict(case, case_id=case['case_id'] + '-VARIANT', query=query, origin='generated_paraphrase'))
    negative_queries = [
        ('unrelated', "What is today's cafeteria lunch menu?"),
        ('unrelated', 'What will the weather in Cairo be tomorrow?'),
        ('unrelated', 'What is the current Bitcoin price?'),
        ('unrelated', 'Who won the football match last night?'),
        ('unrelated', 'Where is my food delivery driver right now?'),
        ('unrelated', 'What is the password for my personal email account?'),
        ('student_specific', 'What is my current cumulative GPA?'),
        ('student_specific', 'Has my credit overload request been approved today?'),
        ('student_specific', 'What grade did I personally receive in my last examination?'),
        ('student_specific', 'How much tuition do I personally owe right now?'),
        ('live_institutional', 'What room is my exam in tomorrow morning?'),
        ('live_institutional', 'Which courses still have free registration seats right now?'),
        ('live_institutional', 'Was my portfolio submission accepted this morning?'),
        ('live_institutional', 'Is the student affairs office closed today because of an emergency?'),
    ]
    negatives = [dict(case_id=f'NEG-{i:02d}', query=query, label='unsupported', category=kind,
        origin='generated_diagnostic', filters={'regulation': 2023, 'language': 'en'})
        for i, (kind, query) in enumerate(negative_queries, 1)]
    rows = []
    for case in positives + negatives:
        results = service.search_documents(case['query'], top_k=5, **case.get('filters', {}))
        row = dict(case, top_results=[r.model_dump(mode='json') for r in results],
                   top_score=max((r.score for r in results), default=None))
        if case['label'] == 'supported':
            scores = [r.score for r in results if r.source_id == case['expected_source']
                      and r.page_start <= case['expected_page'] <= r.page_end]
            row['expected_citation_found'] = bool(scores)
            row['expected_citation_score'] = max(scores) if scores else None
        rows.append(row)
    positive_rows = [r for r in rows if r['label'] == 'supported']
    negative_rows = [r for r in rows if r['label'] == 'unsupported']
    gold_scores = [r['expected_citation_score'] for r in positive_rows if r['expected_citation_score'] is not None]
    negative_scores = [r['top_score'] for r in negative_rows if r['top_score'] is not None]
    curve = []
    for threshold in (0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8):
        curve.append(dict(threshold=threshold,
            supported_citations_retained=sum(score >= threshold for score in gold_scores),
            unsupported_queries_with_evidence=sum(score >= threshold for score in negative_scores)))
    return dict(status='DIAGNOSTIC_NOT_CALIBRATED', supported_queries=len(positive_rows),
        supported_citations_found=len(gold_scores), unsupported_queries=len(negative_rows),
        minimum_supported_citation_score=min(gold_scores) if gold_scores else None,
        maximum_unsupported_score=max(negative_scores) if negative_scores else None,
        observed_score_overlap=bool(gold_scores and negative_scores and max(negative_scores) >= min(gold_scores)),
        production_threshold_recommended=None,
        limitation='Generated English diagnostic set; not independently labeled or held-out calibration. '
                   'Student-specific/live facts cannot be answered by static policy documents.',
        threshold_sweep=curve, cases=rows)


def verify_idempotency(session, foundation, provider):
    def counts():
        return {name: session.scalar(select(func.count()).select_from(model))
                for name, model in [('sources', RagSource), ('chunks', RagChunk)]}

    before = counts()
    pipeline = _common_pipeline(FoundationExtractedTextExtractor(), provider, PgVectorChunkRepository(session))
    results = []
    for item in foundation.list_sources(True):
        sid = item['source_id']
        result = pipeline.ingest(foundation.metadata(sid), foundation.extracted_text_path(sid))
        assert result.status == 'SKIPPED_UNCHANGED', f'{sid}: {result.status}'
        results.append(result.model_dump(mode='json'))
    after = counts()
    assert before == after
    return dict(status='PASS', before=before, after=after, skipped=len(results), results=results)


def audit_api(cases):
    assert not app.dependency_overrides, 'API verification must use real dependencies'
    checks = []
    with TestClient(app) as client:
        ready = client.get('/api/v1/ready')
        assert ready.status_code == 200, ready.text
        checks.append(dict(case='readiness', status='PASS', response=ready.json()))
        for case in cases:
            if not case.get('expected_source'):
                continue
            response = client.post('/api/v1/rag/search', json=dict(query=case['query'], top_k=5, **case.get('filters', {})))
            assert response.status_code == 200, response.text
            evidence = response.json()['results']
            assert any(r['source_id'] == case['expected_source'] and
                       r['page_start'] <= case['expected_page'] <= r['page_end'] for r in evidence), case['case_id']
            assert all(r['regulation'] in (None, case['expected_regulation']) for r in evidence), case['case_id']
            checks.append(dict(case=case['case_id'], status='PASS', result_count=len(evidence)))
        invalid = client.post('/api/v1/rag/search', json={'query': ' '})
        assert invalid.status_code == 422
        checks.append(dict(case='blank_query_rejected', status='PASS'))
    return dict(status='PASS', passed=len(checks), dependency_overrides=False, checks=checks)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--foundation-path', required=True, type=Path)
    parser.add_argument('--smoke-cases', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    settings = get_settings()
    provider = get_embedding_provider()
    foundation = AcademicDataFoundationAdapter(args.foundation_path)
    cases = json.loads(args.smoke_cases.read_text(encoding='utf-8'))
    report = dict(model=provider.model_name, dimension=provider.dimension)
    try:
        with session_scope() as session:
            report['persisted_corpus'] = audit_corpus(session, foundation, provider)
            report['full_corpus_reingestion'] = verify_idempotency(session, foundation, provider)
            # Score collection deliberately runs without a threshold.
            service = DocumentSearchService(provider, PgVectorChunkRepository(session),
                settings.rag_top_k, settings.rag_max_top_k, min_score=None)
            report['score_evaluation'] = evaluate(service, cases)
        report['api'] = audit_api(cases)
        report['status'] = 'PASS_WITH_CALIBRATION_PENDING'
    except Exception as exc:
        report.update(status='FAIL', error=f'{type(exc).__name__}: {exc}')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k not in ('score_evaluation', 'persisted_corpus')}, indent=2))
    return 1 if report['status'] == 'FAIL' else 0


if __name__ == '__main__':
    raise SystemExit(main())
