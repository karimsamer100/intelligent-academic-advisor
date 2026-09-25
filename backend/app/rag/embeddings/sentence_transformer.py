from pathlib import Path
import math
from app.rag.embeddings.base import EmbeddingProvider


class SentenceTransformerEmbeddingProvider(EmbeddingProvider):
    def __init__(self, model_name: str = "BAAI/bge-m3", device: str = "cpu",
                 expected_dimension: int = 1024, cache_dir: Path | None = None,
                 batch_size: int = 16):
        from sentence_transformers import SentenceTransformer

        self._model_name = model_name
        self.batch_size = batch_size
        self.model = SentenceTransformer(model_name, device=device,
                                         cache_folder=str(cache_dir) if cache_dir else None)
        self._dimension = self.model.get_sentence_embedding_dimension()
        if self._dimension != expected_dimension:
            raise ValueError(f"embedding_dimension_mismatch:actual={self._dimension}:expected={expected_dimension}")

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self.model.encode(texts, batch_size=self.batch_size,
                                    normalize_embeddings=True, convert_to_numpy=True,
                                    show_progress_bar=False).tolist()
        if len(vectors) != len(texts):
            raise ValueError("embedding_count_mismatch")
        if any(len(v) != self.dimension or not all(math.isfinite(x) for x in v) for v in vectors):
            raise ValueError("embedding_dimension_mismatch_or_nonfinite_vector")
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]
