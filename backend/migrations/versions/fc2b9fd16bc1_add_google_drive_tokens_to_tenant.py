"""add_google_drive_tokens_to_tenant

Revision ID: fc2b9fd16bc1
Revises: 327e9191b6ef
Create Date: 2025-12-21 23:41:42.147805

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fc2b9fd16bc1'
down_revision: Union[str, None] = '327e9191b6ef'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('tenants', sa.Column('google_drive_tokens', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('tenants', 'google_drive_tokens')
