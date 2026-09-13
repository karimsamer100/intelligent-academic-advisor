# RAG Pipeline v0 Task

**Project:** Local Intelligent Academic Advisor  
**Task:** RAG Pipeline v0  
**Goal:** Build the first reliable local retrieval pipeline over official academic documents and return relevant evidence with correct metadata and page citations.

---

## 1. Scope

Build:

```text
Official PDF
    ↓
Text extraction
    ↓
Cleaning
    ↓
Chunking
    ↓
Metadata
    ↓
Local embeddings
    ↓
PostgreSQL + pgvector
    ↓
Filtered retrieval
    ↓
Evidence + citation metadata
```

RAG v0 retrieves evidence.

It does **not** generate the final student-facing answer.

---

## 2. Locked Decisions

- Use official PDFs / approved documents.
- PostgreSQL is the main DB.
- Vector search uses pgvector.
- Preserve source/page provenance.
- Regulation 18 and 23 must not be mixed when trusted regulation context is available.
- One document may contain multiple document types, regulations, programs, languages, or topics.
- Chunk metadata should be more specific than document metadata where possible.
- The current Excel workbook is not the final academic runtime source.
- RAG v0 is independent of the unfinished Planning Engine.
- Final LLM answer generation is outside this task.

---

## 3. Initial Dataset

Start with a small subset of official documents.

Do not ingest everything first.

Use enough documents to prove multiple cases, ideally:

- one Regulation 2023 document
- one Regulation 2018 document
- one textual procedure / Student Affairs or policy document if available

---

## 4. Document Metadata

Each source document should contain:

```text
source_id
file_name
document_title
document_types[]
regulations[]
programs[]
languages[]
effective_year
version
official_status
file_hash
```

Example:

```json
{
  "source_id": "SRC-BYLAW-2023",
  "file_name": "Bylaw 2023.pdf",
  "document_title": "CAIE Bylaw 2023",
  "document_types": ["REGULATION", "COURSES", "RULES"],
  "regulations": [23],
  "programs": ["CAIE"],
  "languages": ["en"],
  "effective_year": 2023,
  "version": "1",
  "official_status": "OFFICIAL",
  "file_hash": "..."
}
```

Do not force one category when the document genuinely contains several.

---

## 5. Chunk Metadata

Each chunk:

```text
chunk_id
source_id
text
page_start
page_end
section
document_type
regulation
program
language
topic
chunk_index
```

Example:

```json
{
  "chunk_id": "SRC-BYLAW-2023-P42-C03",
  "source_id": "SRC-BYLAW-2023",
  "text": "...",
  "page_start": 42,
  "page_end": 42,
  "section": "Registration Rules",
  "document_type": "REGULATION",
  "regulation": 23,
  "program": "CAIE",
  "language": "en",
  "topic": "credit_load",
  "chunk_index": 3
}
```

A document can cover Regulations 18 and 23 while a particular chunk belongs only to one.

---

## 6. PDF Extraction

Keep extraction behind a replaceable interface, e.g.:

```python
class DocumentExtractor:
    def extract(path):
        ...
```

The exact library is not locked.

Requirements:

- preserve page boundaries
- keep text-to-page mapping
- report extraction failures
- avoid silently dropping whole pages
- handle repeated headers/footers
- treat tables carefully

For RAG v0, prioritize readable text + correct page provenance.

Structured academic table extraction belongs mainly to the Academic Data Foundation.

---

## 7. Cleaning

Allowed:

- whitespace normalization
- repeated header/footer cleanup
- broken-line merging
- obvious encoding cleanup

Do not:

- summarize regulations before indexing
- rewrite official text
- alter numeric values
- replace original text with translation
- remove text just because it looks repetitive without confirming it is boilerplate

Keep the extracted original available for debugging.

---

## 8. Chunking

Preferred boundary order:

1. page/section boundaries
2. headings/subheadings
3. paragraphs
4. token/character fallback

Exact chunk size and overlap are not locked.

Keep them configurable.

Every chunk must preserve page information.

Avoid mixing unrelated Regulation 18 and 23 content in one chunk.

---

## 9. Embeddings

Use a **local** embedding model.

Exact model is not locked.

Requirements:

- Arabic + English capable
- local inference
- model name configurable
- embedding dimension known
- embedding provider replaceable

Do not couple the entire pipeline to one model implementation.

---

## 10. pgvector Storage

Store chunks and embeddings in PostgreSQL + pgvector.

Minimum chunk storage:

```text
chunk_id
source_id
text
embedding
page_start
page_end
section
document_type
regulation
program
language
topic
chunk_index
```

Useful ingestion metadata:

```text
embedding_model
ingested_at
pipeline_version
```

Add the appropriate pgvector index for the chosen search method.

Do not over-optimize before retrieval works correctly.

---

## 11. Idempotent Ingestion

Re-ingesting the same unchanged document must not create uncontrolled duplicate chunks.

Use:

```text
source_id
file_hash
pipeline_version / chunk identity
```

If a document changes, support clean replacement or versioning.

---

## 12. RAG Access Context

Retrieval request:

```json
{
  "query": "What is the maximum credit load?",
  "student_id": null,
  "regulation": 23,
  "program": "CAIE",
  "document_types": ["REGULATION"],
  "language": "en",
  "top_k": 5
}
```

Trusted backend context should override assumptions inferred from query text.

Example:

```text
trusted regulation = 23
```

means Regulation 18-only chunks must not be returned just because they are semantically similar.

---

## 13. Retrieval Contract

Implement a clean service/function such as:

```python
search_documents(
    query: str,
    regulation: int | None = None,
    program: str | None = None,
    document_types: list[str] | None = None,
    language: str | None = None,
    top_k: int = 5,
) -> list[RetrievedEvidence]
```

Keep retrieval logic isolated from API routing.

---

## 14. Retrieval Response

Return evidence, not generated answers.

```json
{
  "results": [
    {
      "chunk_id": "SRC-BYLAW-2023-P42-C03",
      "text": "...",
      "score": 0.88,
      "source_id": "SRC-BYLAW-2023",
      "file_name": "Bylaw 2023.pdf",
      "page_start": 42,
      "page_end": 42,
      "section": "Registration Rules",
      "document_type": "REGULATION",
      "regulation": 23,
      "program": "CAIE",
      "language": "en"
    }
  ]
}
```

The response must be citation-ready.

---

## 15. Filtering Rules

Support metadata filtering for:

```text
regulation
program
document_type
language
official_status
```

Critical rule:

If trusted context says `regulation = 23`, do not return Regulation 18-only chunks.

Shared/general chunks may be returned only when metadata explicitly says they are applicable.

---

## 16. Citation Contract

At minimum preserve:

```text
source_id
file_name
page_start
page_end
section
```

The system should later be able to show:

```text
Bylaw 2023 — page 42 — Registration Rules
```

If a chunk spans multiple pages, report the range.

---

## 17. Basic Retrieval Test Set

Create a small manual smoke-test set covering:

- exact policy lookup
- paraphrased semantic query
- Regulation 18 query
- Regulation 23 query
- similar wording across both regulations
- Student Affairs / procedure question
- unsupported query

Each case should record:

```text
query
expected_source
expected_page/page range
expected_regulation
```

This is not the final project evaluation framework.

---

## 18. Minimum Quality Checks

Detect/report:

- PDF extraction failure
- empty document
- empty page
- empty chunk
- duplicate chunk ID
- missing source ID
- missing page metadata
- missing regulation on regulation-specific chunk
- embedding failure
- DB insertion failure

Never silently treat failed ingestion as success.

---

## 19. Configuration

Keep configurable:

```text
DOCUMENTS_PATH
EMBEDDING_MODEL
EMBEDDING_DEVICE
CHUNK_SIZE
CHUNK_OVERLAP
RAG_TOP_K
DATABASE_URL
```

Do not hard-code machine-specific paths.

---

## 20. Logging

Log:

- source loaded
- pages extracted
- chunks created
- embeddings generated
- chunks inserted
- retrieval query
- filters applied
- result count
- failures

Do not log secrets or sensitive student data.

---

## 21. Suggested Internal Structure

```text
backend/app/rag/
│
├── extractors/
├── cleaners/
├── chunkers/
├── embeddings/
├── ingestion/
├── retrieval/
├── models/
└── config/
```

Conceptual interfaces:

```text
DocumentExtractor
TextCleaner
Chunker
EmbeddingProvider
ChunkRepository
Retriever
```

Keep implementations replaceable.

---

## 22. Do Not Implement

Do not implement in RAG v0:

- final LLM answer generation
- agent/orchestrator
- eligibility logic
- prerequisite computation
- semester planning
- track recommendation
- advisor escalation
- frontend
- voice
- automatic academic conflict resolution
- conversion of unverified text into executable academic rules

---

## 23. Definition of Done

RAG v0 is complete when:

1. A small official PDF set can be ingested.
2. Extracted text remains traceable to pages.
3. Chunks contain agreed metadata.
4. Local embeddings are generated.
5. Chunks/vectors are stored in PostgreSQL + pgvector.
6. Top-k semantic retrieval works.
7. Metadata filters work.
8. Regulation 18/23 cross-contamination is prevented when regulation is known.
9. Results contain citation-ready metadata.
10. Re-ingestion does not create uncontrolled duplicates.
11. Basic retrieval tests exist.
12. No final answer generation or academic computation is hidden inside RAG.

---

## 24. Deliverable

Deliver:

```text
RAG pipeline code
PDF extraction module
cleaning module
chunking module
local embedding provider
pgvector persistence
retrieval service/function
metadata models
configuration
ingestion command/script
small retrieval test set
README / run instructions
```

First target:

> Reliable official evidence retrieval with correct academic scope and citations.
