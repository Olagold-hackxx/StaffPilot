"""add campaign builder fields

Revision ID: e2a7c91d8f3b
Revises: 0627fbe889eb, add_campaign_builder
Create Date: 2025-12-12 09:12:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e2a7c91d8f3b'
down_revision = ('0627fbe889eb', 'add_campaign_builder')
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new columns to campaigns table
    op.add_column('campaigns', sa.Column('objective_type', sa.String(50), nullable=True))
    op.add_column('campaigns', sa.Column('currency', sa.String(10), server_default='USD', nullable=True))
    op.add_column('campaigns', sa.Column('goal_metrics', sa.JSON(), nullable=True))
    op.add_column('campaigns', sa.Column('product_brief', sa.Text(), nullable=True))
    op.add_column('campaigns', sa.Column('creative_preference', sa.String(20), server_default='both', nullable=True))
    op.add_column('campaigns', sa.Column('target_audience', sa.JSON(), nullable=True))


def downgrade() -> None:
    # Remove the new columns
    op.drop_column('campaigns', 'target_audience')
    op.drop_column('campaigns', 'creative_preference')
    op.drop_column('campaigns', 'product_brief')
    op.drop_column('campaigns', 'goal_metrics')
    op.drop_column('campaigns', 'currency')
    op.drop_column('campaigns', 'objective_type')
