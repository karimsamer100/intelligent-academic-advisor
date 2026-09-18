# Data Directory

This repository keeps only small development/evaluation assets in Git.

- `prepared_sample/` — 3-source RAG proof set generated from the Academic Data Foundation (80 validated chunks).
- `smoke_tests/` — retrieval smoke-test cases.
- `academic_foundation/` — **not committed**; place/extract the full Academic Data Foundation here when you want to ingest the official source package.
- `rag_debug/` — generated extraction diagnostics; not committed.

To install the Academic Data Foundation ZIP:

```bash
python scripts/unpack_academic_foundation.py /path/to/Academic_Data_Foundation_SUBMISSION_READY.zip
```

After that, `data/academic_foundation/rag/source_registry.json` should exist.
