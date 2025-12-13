"""add campaign builder models

Revision ID: add_campaign_builder
Revises: 5e92c08a7daa
Create Date: 2025-01-XX XX:XX:XX.XXXXXX

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_campaign_builder'
down_revision: Union[str, None] = '5e92c08a7daa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create campaign_contexts table
    op.create_table(
        'campaign_contexts',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('campaign_id', sa.UUID(), nullable=False),
        sa.Column('context_data', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_campaign_contexts_campaign_id', 'campaign_contexts', ['campaign_id'], unique=False)
    
    # Create chat_transcripts table
    op.create_table(
        'chat_transcripts',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('campaign_id', sa.UUID(), nullable=False),
        sa.Column('role', sa.String(20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('embedding_id', sa.String(255), nullable=True),
        sa.Column('is_pinned', sa.Boolean(), nullable=True, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_chat_transcripts_campaign_id', 'chat_transcripts', ['campaign_id'], unique=False)
    
    # Create creative_requests table
    op.create_table(
        'creative_requests',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('campaign_id', sa.UUID(), nullable=False),
        sa.Column('creative_type', sa.String(20), nullable=False),
        sa.Column('parameters', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('status', sa.String(50), nullable=True, server_default='pending'),
        sa.Column('render_job_id', sa.String(255), nullable=True),
        sa.Column('output_files', sa.JSON(), nullable=True, server_default='[]'),
        sa.Column('storyboard', sa.JSON(), nullable=True),
        sa.Column('is_approved', sa.Boolean(), nullable=True, server_default='false'),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('meta_data', sa.JSON(), nullable=True, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_creative_requests_campaign_id', 'creative_requests', ['campaign_id'], unique=False)


def downgrade() -> None:
    op.drop_table('creative_requests')
    op.drop_table('chat_transcripts')
    op.drop_table('campaign_contexts')
