import os
import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration


def test_pgvector_extension_available():
    if os.getenv("RUN_PGVECTOR_TESTS") != "1":
        pytest.skip("Set RUN_PGVECTOR_TESTS=1 after starting PostgreSQL + pgvector")
    from app.db.session import session_scope
    with session_scope() as session:
        version = session.scalar(text("SELECT extversion FROM pg_extension WHERE extname = 'vector'"))
        assert version is not None
