import pytest

from backend.app.planning.domain.version import DatasetVersion


def test_dataset_version_metadata_is_immutable_and_serializable() -> None:
    version = DatasetVersion(
        version="foundation-1.0.0-dev",
        source="academic-data-foundation",
        revision="abc123",
    )

    assert version.to_dict() == {
        "version": "foundation-1.0.0-dev",
        "source": "academic-data-foundation",
        "revision": "abc123",
    }
    with pytest.raises((AttributeError, TypeError)):
        version.version = "other"  # type: ignore[misc]


def test_dataset_version_requires_non_empty_version() -> None:
    with pytest.raises(ValueError):
        DatasetVersion("")
