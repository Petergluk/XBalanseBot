"""Add performance indexes

Revision ID: e694a49f88ea
Revises: e6f7a8b9c0d1
Create Date: 2026-03-28 18:12:28.481307

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e694a49f88ea'
down_revision: Union[str, Sequence[str], None] = 'e6f7a8b9c0d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index('idx_transactions_from_user', 'transactions', ['from_user_id'])
    op.create_index('idx_transactions_to_user', 'transactions', ['to_user_id'])
    op.create_index('idx_transactions_created_at', 'transactions', ['created_at'])
    op.create_index('idx_users_balance', 'users', ['balance'])
    op.create_index('idx_user_subscriptions_user', 'user_subscriptions', ['user_id'])
    op.create_index('idx_events_activity_active', 'events', ['activity_id', 'is_active'])

def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('idx_events_activity_active', table_name='events')
    op.drop_index('idx_user_subscriptions_user', table_name='user_subscriptions')
    op.drop_index('idx_users_balance', table_name='users')
    op.drop_index('idx_transactions_created_at', table_name='transactions')
    op.drop_index('idx_transactions_to_user', table_name='transactions')
    op.drop_index('idx_transactions_from_user', table_name='transactions')
