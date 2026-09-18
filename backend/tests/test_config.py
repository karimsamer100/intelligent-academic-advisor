from app.core.config import Settings


def test_config_defaults_and_short_regulation_are_independent():
    settings = Settings(_env_file=None)
    assert settings.api_v1_prefix == "/api/v1"
    assert settings.rag_top_k <= settings.rag_max_top_k
    settings.validate_chunking()


def test_blank_min_score_maps_to_none():
    settings = Settings(_env_file=None, rag_min_score="")
    assert settings.rag_min_score is None
