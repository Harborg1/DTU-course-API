from sqlalchemy.pool import NullPool

from app.database import engine_options, normalize_database_url


def test_postgres_urls_use_the_installed_psycopg_driver():
    assert normalize_database_url("postgresql://user:password@host/database") == (
        "postgresql+psycopg://user:password@host/database"
    )
    assert normalize_database_url("postgres://user:password@host/database") == (
        "postgresql+psycopg://user:password@host/database"
    )


def test_sqlite_engine_options_allow_test_threads():
    assert engine_options("sqlite://") == {
        "pool_pre_ping": True,
        "connect_args": {"check_same_thread": False},
    }


def test_supabase_transaction_pooler_uses_no_client_pool_or_prepared_statements():
    options = engine_options(
        "postgresql+psycopg://user:password@aws-1-eu-west-3.pooler.supabase.com:6543/postgres"
    )

    assert options["poolclass"] is NullPool
    assert options["connect_args"] == {"prepare_threshold": None}


def test_regular_postgres_keeps_default_sqlalchemy_pool():
    assert engine_options("postgresql+psycopg://user:password@localhost:5432/database") == {
        "pool_pre_ping": True
    }
