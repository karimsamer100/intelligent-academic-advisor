from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def academic_data_root() -> Path:
    """Resolve the shared Academic Data package in each test environment."""

    docker_root = Path("/data/academic")
    repository_root = Path(__file__).resolve().parents[3]
    local_root = repository_root / "data" / "academic"

    for candidate in (docker_root, local_root):
        if candidate.is_dir():
            return candidate.resolve()

    searched = ", ".join(str(candidate) for candidate in (docker_root, local_root))
    raise pytest.UsageError(f"Academic Data package not found; searched: {searched}")
