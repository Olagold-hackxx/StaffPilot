"""add_ai_generated_document_type

Revision ID: a1b2c3d4e5f6
Revises: fc2b9fd16bc1
Create Date: 2026-01-04 23:54:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'fc2b9fd16bc1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new value to the documenttype enum
    # PostgreSQL requires special handling for adding enum values
    op.execute("ALTER TYPE documenttype ADD VALUE IF NOT EXISTS 'ai_generated'")


def downgrade() -> None:
    # Note: PostgreSQL doesn't support removing enum values directly
    # This would require recreating the enum type which is complex
    # For safety, we just pass here
    pass
