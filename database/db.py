from __future__ import annotations

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


def _build_database_url() -> str:
    if DATABASE_URL:
        url = DATABASE_URL

        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://"):]

        if url.startswith("postgresql://"):
            url = "postgresql+asyncpg://" + url[len("postgresql://"):]

        return url

    return (
        f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}"
        f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )


DATABASE_ASYNC_URL = _build_database_url()

engine_kwargs = {
    "echo": DB_ECHO,
    "pool_pre_ping": True,
}

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
