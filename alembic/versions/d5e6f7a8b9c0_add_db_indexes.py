"""add db indexes

Revision ID: d5e6f7a8b9c0
Revises: b4d2e3f5a6c7
Create Date: 2026-03-25 01:21:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd5e6f7a8b9c0'
down_revision = 'c2d9f7a1b8e0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add indexes to frequently queried columns
    op.create_index('idx_users_telegram_id', 'users', ['telegram_id'])
    op.create_index('idx_events_activity_id', 'events', ['activity_id'])
    op.create_index('idx_transactions_users', 'transactions', ['from_user_id', 'to_user_id'])


def downgrade() -> None:
    op.drop_index('idx_transactions_users', table_name='transactions')
    op.drop_index('idx_events_activity_id', table_name='events')
    op.drop_index('idx_users_telegram_id', table_name='users')
