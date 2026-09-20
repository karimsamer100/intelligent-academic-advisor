# Project Decisions

> This file contains only project-wide decisions.  
> Any developer or AI working on the project should follow these decisions and should not invent alternatives unless the team explicitly changes them.

## Product
- Project name: **Local Intelligent Academic Advisor**
- Primary scope: **Academic Advising**
- Secondary scope: **Selected Student Affairs informational Q&A**
- Initial academic scope: **Regulations 2018 and 2023**
- Interface: **Web application**
- Languages: **Arabic and English**
- LLM deployment: **Local / self-hosted only**
- Human advisor escalation: **Planned for exceptional or unresolved cases**

## Core Architecture
- The LLM handles conversation, intent understanding, missing-information questions, tool selection, and explanation.
- The LLM is **not** the authority for academic decisions.
- The Academic Planning Engine is responsible for eligibility, prerequisites/corequisites, academic rules, dependencies, and planning.
- RAG is responsible for official textual knowledge, retrieval, evidence, and citations.
- Original official documents remain the **source of truth**.
- Structured verified data is used for **computation**.
- RAG data is used for **retrieval/evidence**.

## Data
- The current Excel workbook is **not** the final runtime data source.
- The Academic Data Foundation is being finalized separately.
- Planning Engine implementation waits for the verified machine-readable data package.
- Critical academic facts must never be guessed.
- Unresolved/unapproved academic rules must not drive decisions.
- Regulation 2018 and Regulation 2023 must remain explicitly separated.

## Backend / Database
- Backend: **Python + FastAPI**
- Database: **PostgreSQL**
- Vector search: **pgvector inside PostgreSQL**
- ORM: **SQLAlchemy**
- Migrations: **Alembic**
- Local development: **Docker Compose**
- Configuration/secrets: **environment variables / `.env`**
- Secrets must never be committed to Git.

## RAG
- RAG uses official PDFs / approved documents.
- Retrieval must preserve source and page provenance.
- A single document may belong to multiple document types, programs, regulations, languages, or topics.
- Document-level metadata may contain multiple values.
- Chunk-level metadata should be as specific as possible.
- Regulation filtering must prevent Regulation 18/23 cross-contamination when regulation is known.
- RAG v0 includes ingestion, extraction, cleaning, chunking, metadata, local embeddings, pgvector storage, retrieval, and citation-ready results.
- Final LLM answer generation is **not** part of RAG v0.

## Shared Document Metadata

### Document-level
- `source_id`
- `file_name`
- `document_title`
- `document_types[]`
- `regulations[]`
- `programs[]`
- `languages[]`
- `effective_year`
- `version`
- `official_status`
- `file_hash`

### Chunk-level
- `chunk_id`
- `source_id`
- `text`
- `page_start`
- `page_end`
- `section`
- `document_type`
- `regulation`
- `program`
- `language`
- `topic`
- `chunk_index`

## RAG Access Context

### Request
- `query`
- `student_id` (optional)
- `regulation` (optional)
- `program` (optional)
- `document_types[]` (optional)
- `language` (optional)
- `top_k`

### Response
- `chunk_id`
- `text`
- `score`
- `source_id`
- `file_name`
- `page_start`
- `page_end`
- `section`
- `document_type`
- `regulation`
- `program`
- `language`

## Current Development Order

### Start now
1. Repository / general project foundation
2. Backend Foundation
3. RAG Pipeline v0

### Wait for Academic Data Foundation
- Planning Engine implementation

### Later
- Local LLM integration
- Orchestration
- Frontend
- Evaluation expansion
- Voice
- Advisor workflow

## Not Locked Yet
The following are not final decisions and should not be invented by an AI:
- exact local LLM model/version
- exact embedding model
- exact PDF extraction library
- exact chunk size / overlap
- exact retrieval/reranking strategy
- frontend framework details
- authentication implementation
- final Planning Engine algorithm
