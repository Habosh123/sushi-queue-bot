from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from config.settings import (
    DATABASE_URL,
    DB_ECHO,
    DB_HOST,
    DB_NAME,
    DB_PASSWORD,
    DB_PORT,
    DB_USE_NULLPOOL,
    DB_USER,
)


def _normalize_asyncpg_url(url: str) -> tuple[str, dict]:
    """Convert external PostgreSQL URLs to a SQLAlchemy asyncpg URL.

    Supabase/Neon often provide URLs like:
    postgresql://user:pass@host:5432/db?sslmode=require

    asyncpg does not accept `sslmode` as a connection argument, so we remove it
    from the URL query and pass `ssl=True` through connect_args instead.
    """
    connect_args: dict = {}

    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]

    parts = urlsplit(url)
    query_items = []

    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        key_lower = key.lower()

        if key_lower in {"sslmode", "ssl"}:
            if value.lower() not in {"", "disable", "false", "0", "off"}:
                connect_args["ssl"] = True
            continue

        query_items.append((key, value))

    cleaned_query = urlencode(query_items)
    cleaned_url = urlunsplit((
        parts.scheme,
        parts.netloc,
        parts.path,
        cleaned_query,
        parts.fragment,
    ))

    if cleaned_url.startswith("postgresql://"):
        cleaned_url = "postgresql+asyncpg://" + cleaned_url[len("postgresql://"):]

    return cleaned_url, connect_args


def _build_database_url() -> tuple[str, dict]:
    if DATABASE_URL:
        return _normalize_asyncpg_url(DATABASE_URL)

    return (
        f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}"
        f"@{DB_HOST}:{DB_PORT}/{DB_NAME}",
        {},
    )


DATABASE_ASYNC_URL, connect_args = _build_database_url()

engine_kwargs = {
    "echo": DB_ECHO,
    "pool_pre_ping": True,
}

if connect_args:
    engine_kwargs["connect_args"] = connect_args

# Для Vercel/serverless не держим долгоживущий пул соединений между вызовами.
if DB_USE_NULLPOOL:
    engine_kwargs["poolclass"] = NullPool
    engine_kwargs.pop("pool_pre_ping", None)

engine = create_async_engine(
    DATABASE_ASYNC_URL,
    **engine_kwargs,
)

SessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
)
