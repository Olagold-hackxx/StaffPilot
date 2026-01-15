"""add_email_tokens_table

Revision ID: b1c2d3e4f5g6
Revises: a1b2c3d4e5f6
Create Date: 2026-01-07 15:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b1c2d3e4f5g6'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create email token type enum (checkfirst=True prevents error if it exists)
    emailtokentype = postgresql.ENUM('verify_email', 'reset_password', name='emailtokentype')
    emailtokentype.create(op.get_bind(), checkfirst=True)
    
    # Create email_tokens table
    # Use create_type=False since we already created the enum above
    op.create_table(
        'email_tokens',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('token_type', postgresql.ENUM('verify_email', 'reset_password', name='emailtokentype', create_type=False), nullable=False),
        sa.Column('token', sa.String(length=255), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes
    op.create_index(op.f('ix_email_tokens_token'), 'email_tokens', ['token'], unique=True)
    op.create_index(op.f('ix_email_tokens_user_id'), 'email_tokens', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_email_tokens_user_id'), table_name='email_tokens')
    op.drop_index(op.f('ix_email_tokens_token'), table_name='email_tokens')
    op.drop_table('email_tokens')
    
    # Drop enum type
    emailtokentype = postgresql.ENUM('verify_email', 'reset_password', name='emailtokentype')
    emailtokentype.drop(op.get_bind(), checkfirst=True)
