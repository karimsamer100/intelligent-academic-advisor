import sys
from types import SimpleNamespace
import pytest
from app.rag.embeddings.sentence_transformer import SentenceTransformerEmbeddingProvider


class FakeModel:
    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs

    def get_sentence_embedding_dimension(self):
        return 3

    def encode(self, texts, **kwargs):
        return SimpleNamespace(tolist=lambda: [[1.0, 0.0, 0.0] for _ in texts])


@pytest.fixture
def model(monkeypatch):
    monkeypatch.setitem(sys.modules, 'sentence_transformers', SimpleNamespace(SentenceTransformer=FakeModel))


def test_provider_shapes_and_configuration(model):
    provider = SentenceTransformerEmbeddingProvider('local/model', 'cpu', 3)
    assert provider.model_name == 'local/model'
    assert provider.dimension == 3
    assert len(provider.embed_query('test')) == 3
    assert [len(v) for v in provider.embed_documents(['first text', 'second text'])] == [3, 3]
    assert provider.embed_documents([]) == []


def test_dimension_mismatch_fails_loudly(model):
    with pytest.raises(ValueError, match='embedding_dimension_mismatch'):
        SentenceTransformerEmbeddingProvider(expected_dimension=1024)


def test_runtime_dependency_only_constructs_production_provider(monkeypatch, model):
    from app.api import dependencies
    monkeypatch.setattr(dependencies, 'get_settings', lambda: SimpleNamespace(
        embedding_model='local/model', embedding_device='cpu', embedding_dimension=3,
        embedding_cache_dir=None, embedding_batch_size=2))
    dependencies.get_embedding_provider.cache_clear()
    try:
        assert isinstance(dependencies.get_embedding_provider(), SentenceTransformerEmbeddingProvider)
    finally:
        dependencies.get_embedding_provider.cache_clear()
