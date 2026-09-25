"""Execute the configured production provider and write reproducible shape checks."""
import argparse
import json
from pathlib import Path
from app.core.config import get_settings
from app.rag.embeddings.sentence_transformer import SentenceTransformerEmbeddingProvider


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    s = get_settings()
    report = dict(provider="SentenceTransformerEmbeddingProvider", model=s.embedding_model,
                  device=s.embedding_device, configured_dimension=s.embedding_dimension)
    try:
        provider = SentenceTransformerEmbeddingProvider(s.embedding_model, s.embedding_device,
            s.embedding_dimension, s.embedding_cache_dir, s.embedding_batch_size)
        query = provider.embed_query("test")
        documents = provider.embed_documents(["first text", "second text"])
        assert len(query) == provider.dimension == s.embedding_dimension
        assert len(documents) == 2 and all(len(v) == provider.dimension for v in documents)
        report.update(actual_dimension=provider.dimension, embed_query="PASS",
                      embed_documents="PASS", query_length=len(query), document_lengths=[len(v) for v in documents])
        try:
            SentenceTransformerEmbeddingProvider(s.embedding_model, s.embedding_device,
                s.embedding_dimension + 1, s.embedding_cache_dir, s.embedding_batch_size)
        except ValueError as exc:
            assert "embedding_dimension_mismatch" in str(exc)
            report["dimension_mismatch"] = str(exc)
        else:
            raise AssertionError("dimension mismatch was silently accepted")
        report["status"] = "PASS"
    except Exception as exc:
        report.update(status="FAIL", error=f"{type(exc).__name__}: {exc}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
