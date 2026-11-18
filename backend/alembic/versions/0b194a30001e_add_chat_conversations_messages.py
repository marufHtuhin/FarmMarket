"""add chat_conversations + chat_messages (farmer-buyer messaging)

Revision ID: 0b194a30001e
Revises: f6bbf6f95040
Create Date: 2026-11-17 11:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0b194a30001e'
down_revision: Union[str, Sequence[str], None] = 'f6bbf6f95040'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'chat_conversations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('farmer_id', sa.Integer(), nullable=False),
        sa.Column('buyer_id', sa.Integer(), nullable=False),
        sa.Column('listing_id', sa.Integer(), nullable=True),
        sa.Column('offer_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['farmer_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['buyer_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['listing_id'], ['products.id'], ),
        sa.ForeignKeyConstraint(['offer_id'], ['offers.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_chat_conversations_farmer_id', 'chat_conversations', ['farmer_id'])
    op.create_index('ix_chat_conversations_buyer_id', 'chat_conversations', ['buyer_id'])
    op.create_index('ix_chat_conversations_listing_id', 'chat_conversations', ['listing_id'])
    op.create_index('ix_chat_conversations_offer_id', 'chat_conversations', ['offer_id'])
    op.create_table(
        'chat_messages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('conversation_id', sa.Integer(), nullable=False),
        sa.Column('sender_id', sa.Integer(), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('read_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['conversation_id'], ['chat_conversations.id'], ),
        sa.ForeignKeyConstraint(['sender_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_chat_messages_conversation_id', 'chat_messages', ['conversation_id'])
    op.create_index('ix_chat_messages_sender_id', 'chat_messages', ['sender_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_chat_messages_sender_id', table_name='chat_messages')
    op.drop_index('ix_chat_messages_conversation_id', table_name='chat_messages')
    op.drop_table('chat_messages')
    op.drop_index('ix_chat_conversations_offer_id', table_name='chat_conversations')
    op.drop_index('ix_chat_conversations_listing_id', table_name='chat_conversations')
    op.drop_index('ix_chat_conversations_buyer_id', table_name='chat_conversations')
    op.drop_index('ix_chat_conversations_farmer_id', table_name='chat_conversations')
    op.drop_table('chat_conversations')
