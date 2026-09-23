"""Deterministic test fixture; never selected by runtime dependencies."""
import hashlib
import math
import re
from app.rag.embeddings.base import EmbeddingProvider


class HashTestEmbeddingProvider(EmbeddingProvider):
    def __init__(self, dimension: int = 64):
        if dimension <= 0:
            raise ValueError("dimension must be positive")
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def model_name(self) -> str:
        return f"hash-test-only-{self.dimension}"

    def embed_query(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for token in re.findall(r"\w+", text.casefold()):
            digest = hashlib.sha256(token.encode()).digest()
            vector[int.from_bytes(digest[:4], "big") % self.dimension] += 1.0
        norm = math.sqrt(sum(x * x for x in vector)) or 1.0
        return [x / norm for x in vector]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(text) for text in texts]
