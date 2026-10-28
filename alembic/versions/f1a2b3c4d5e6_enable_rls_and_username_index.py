"""Enable Row Level Security (RLS) on all public tables for Supabase and add username index

Revision ID: f1a2b3c4d5e6
Revises: a4541b05fb21
Create Date: 2026-10-27 12:15:00.000000
"""
from typing import Sequence, Union
from alembic import op

revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'a4541b05fb21'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    1. Добавляет функциональный индекс LOWER(username) для быстрого регистронезависимого поиска.
    2. Включает Row-Level Security (RLS) на всех таблицах схемы public (устраняет критическую
       уязвимость Supabase rls_disabled_in_public / PostgREST Data API).
       Бот подключается напрямую через роль владельца БД (postgres), которая обходит RLS (BYPASSRLS),
       тогда как публичный доступ через Supabase REST API (роли anon / authenticated) полностью блокируется.
    """
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_username_lower ON users (LOWER(username));")

    op.execute(
        """
        DO $$
        DECLARE
            r RECORD;
        BEGIN
            FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') LOOP
                EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY;', r.tablename);
            END LOOP;

            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
                EXECUTE 'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon;';
                EXECUTE 'REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon;';
            END IF;

            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                EXECUTE 'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM authenticated;';
                EXECUTE 'REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM authenticated;';
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_users_username_lower;")
    op.execute(
        """
        DO $$
        DECLARE
            r RECORD;
        BEGIN
            FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') LOOP
                EXECUTE format('ALTER TABLE public.%I DISABLE ROW LEVEL SECURITY;', r.tablename);
            END LOOP;
        END $$;
        """
    )
