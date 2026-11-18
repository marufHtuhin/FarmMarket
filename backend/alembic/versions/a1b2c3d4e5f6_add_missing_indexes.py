"""add missing indexes: chat_conversations.id + hot foreign keys

Revision ID: a1b2c3d4e5f6
Revises: 5a6223da9538
Create Date: 2026-11-17

Audit (Phase 3) findings F5 + F6:
- F5: models.py declares ChatConversation.id with index=True, but migration
  0b194a30001e never created ix_chat_conversations_id, so `alembic check`
  failed (models drifted from migrations). The codebase indexes PKs
  consistently (see the initial migration), so the index is added here
  rather than dropping index=True from the model.
- F6: orders.buyer_id / farmer_id / product_id / transporter_id,
  products.farmer_id and demand_requests.buyer_id had no index although
  every list/dashboard query filters on them; every other FK in the schema
  is indexed. Adds the six missing indexes.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '5a6223da9538'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index('ix_chat_conversations_id', 'chat_conversations', ['id'])
    op.create_index('ix_orders_buyer_id', 'orders', ['buyer_id'])
    op.create_index('ix_orders_farmer_id', 'orders', ['farmer_id'])
    op.create_index('ix_orders_product_id', 'orders', ['product_id'])
    op.create_index('ix_orders_transporter_id', 'orders', ['transporter_id'])
    op.create_index('ix_products_farmer_id', 'products', ['farmer_id'])
    op.create_index('ix_demand_requests_buyer_id', 'demand_requests', ['buyer_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_demand_requests_buyer_id', table_name='demand_requests')
    op.drop_index('ix_products_farmer_id', table_name='products')
    op.drop_index('ix_orders_transporter_id', table_name='orders')
    op.drop_index('ix_orders_product_id', table_name='orders')
    op.drop_index('ix_orders_farmer_id', table_name='orders')
    op.drop_index('ix_orders_buyer_id', table_name='orders')
    op.drop_index('ix_chat_conversations_id', table_name='chat_conversations')
