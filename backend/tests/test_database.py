"""Needs PostgreSQL + `alembic upgrade head`. Skipped when the DB is unreachable."""

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration


def test_database_connectivity(db_engine):
    with db_engine.connect() as connection:
        assert connection.execute(text("SELECT 1")).scalar_one() == 1


def test_pgvector_extension_is_enabled(db_engine):
    with db_engine.connect() as connection:
        version = connection.execute(text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")).scalar_one_or_none()
    assert version is not None, "pgvector is not enabled - run `alembic upgrade head`"


def test_pgvector_can_store_and_compare_vectors(db_engine):
    with db_engine.connect() as connection:
        distance = connection.execute(text("SELECT '[1,2,3]'::vector <-> '[1,2,4]'::vector")).scalar_one()
    assert distance == pytest.approx(1.0)
