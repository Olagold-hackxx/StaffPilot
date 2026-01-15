"""add_requires_approval_to_scheduled_posts

Revision ID: c1d2e3f4g5h6
Revises: b1c2d3e4f5g6
Create Date: 2026-01-08 23:28:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1d2e3f4g5h6'
down_revision: Union[str, None] = 'b1c2d3e4f5g6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add requires_approval column to scheduled_posts table
    op.add_column(
        'scheduled_posts',
        sa.Column('requires_approval', sa.Boolean(), nullable=False, server_default='false')
    )


def downgrade() -> None:
    op.drop_column('scheduled_posts', 'requires_approval')
