"""add email verification: users.email_verified + email_verification_tokens

Revision ID: f07c52b75221
Revises: a1b2c3d4e5f6
Create Date: 2026-11-18

Email verification on registration (distinct from the admin-set seller
badge users.is_verified — that column is NOT reused):
- users.email_verified (Boolean, server default false): existing rows
  backfill to False, so every pre-existing account starts unverified.
- email_verification_tokens: one-time tokens, SHA-256 hash only, mirrors
  password_reset_tokens (same columns, indexes and constraints).

Additive only: no column/table is dropped or altered in a destructive way.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f07c52b75221'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # server_default=false backfills existing rows to unverified; the
    # default stays on the column (harmless — new rows are unverified
    # until confirmed). NOT NULL mirrors users.is_verified.
    op.add_column('users',
                  sa.Column('email_verified', sa.Boolean(),
                            server_default=sa.false(), nullable=False))
    op.create_table('email_verification_tokens',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.Column('used', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_email_verification_tokens_token_hash'), 'email_verification_tokens', ['token_hash'], unique=True)
    op.create_index(op.f('ix_email_verification_tokens_user_id'), 'email_verification_tokens', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_email_verification_tokens_user_id'), table_name='email_verification_tokens')
    op.drop_index(op.f('ix_email_verification_tokens_token_hash'), table_name='email_verification_tokens')
    op.drop_table('email_verification_tokens')
    op.drop_column('users', 'email_verified')
