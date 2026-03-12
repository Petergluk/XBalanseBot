"""add_tag_rules_and_rewards_log

Revision ID: b4d2e3f5a6c7
Revises: a3f1c2d4e5b6
Create Date: 2026-03-11 21:00:00

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'b4d2e3f5a6c7'
down_revision: Union[str, Sequence[str], None] = 'a3f1c2d4e5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS tag_rules (
            id          SERIAL PRIMARY KEY,
            hashtag     VARCHAR(100) NOT NULL,
            min_chars   INTEGER NOT NULL DEFAULT 0,
            reward      NUMERIC(12,2) NOT NULL,
            daily_limit INTEGER NOT NULL DEFAULT 0,
            thread_id   BIGINT,
            group_msg   TEXT,
            bot_msg     TEXT,
            reaction    VARCHAR(10) DEFAULT '🏅',
            is_active   BOOLEAN NOT NULL DEFAULT TRUE
        );
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS tag_rewards_log (
            id               SERIAL PRIMARY KEY,
            user_telegram_id BIGINT NOT NULL,
            message_id       BIGINT NOT NULL UNIQUE,
            rule_id          INTEGER REFERENCES tag_rules(id) ON DELETE SET NULL,
            rewarded_at      TIMESTAMP NOT NULL DEFAULT NOW()
        );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tag_rewards_log;")
    op.execute("DROP TABLE IF EXISTS tag_rules;")
