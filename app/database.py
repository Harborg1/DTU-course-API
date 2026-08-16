from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql://"):
        return "postgresql+psycopg://" + database_url.removeprefix("postgresql://")
    if database_url.startswith("postgres://"):
        return "postgresql+psycopg://" + database_url.removeprefix("postgres://")
    return database_url


def engine_options(database_url: str) -> dict:
    options: dict = {"pool_pre_ping": True}
    if database_url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}
    elif ".pooler.supabase.com:6543/" in database_url:
        # Supabase's transaction pooler owns connection reuse. Keeping a
        # client-side pool in a serverless function can exhaust DB connections,
        # and transaction mode does not support session-scoped prepared queries.
        options["poolclass"] = NullPool
        options["connect_args"] = {"prepare_threshold": None}
    return options


def make_engine(database_url: str | None = None):
    url = normalize_database_url(database_url or get_settings().database_url)
    return create_engine(url, **engine_options(url))


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
