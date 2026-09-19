"""enable pgvector extension

No tables yet: the academic schema is not finalised. This migration only
guarantees that the ``vector`` extension exists, so ``alembic upgrade head``
is the single, repeatable way to prepare a database.

Revision ID: 0001
Revises:
Create Date: 2026-01-01
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS vector")
