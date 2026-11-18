"""add price_observations.note (source note on manual price entries)

Revision ID: 5a6223da9538
Revises: 0b194a30001e
Create Date: 2026-11-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5a6223da9538'
down_revision: Union[str, Sequence[str], None] = '0b194a30001e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Nullable: existing imported / synthetic rows have no note.
    op.add_column('price_observations',
                  sa.Column('note', sa.String(length=200), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('price_observations', 'note')
