from __future__ import annotations

import asyncio
import sys
from urllib.parse import urlsplit

from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings


def masked_url_parts(url: str) -> dict[str, str | int | None]:
    parsed = urlsplit(url)
    return {
        "engine": parsed.scheme,
        "host": parsed.hostname or "",
        "port": parsed.port,
        "database": (parsed.path or "").lstrip("/"),
        "username": mask_value(parsed.username or ""),
    }


def mask_value(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 2:
        return "*" * len(value)
    return f"{value[0]}{'*' * (len(value) - 2)}{value[-1]}"


def print_config(label: str, url: str) -> None:
    parts = masked_url_parts(url)
    print(f"{label}:")
    print(f"  engine: {parts['engine']}")
    print(f"  host: {parts['host']}")
    print(f"  port: {parts['port']}")
    print(f"  database: {parts['database']}")
    print(f"  username: {parts['username']}")


async def check_async_connection() -> None:
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(text("SELECT 1"))
            assert result.scalar_one() == 1
    finally:
        await engine.dispose()


def check_sync_connection() -> None:
    engine = create_engine(settings.alembic_database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1"))
            assert result.scalar_one() == 1
    finally:
        engine.dispose()


def sanitize_error(error: Exception) -> str:
    message = str(error)
    for candidate in (urlsplit(settings.database_url).password, urlsplit(settings.alembic_database_url).password):
        if candidate:
            message = message.replace(candidate, "****")
    return message


def main() -> int:
    print_config("Application database URL", settings.database_url)
    print_config("Alembic database URL", settings.alembic_database_url)
    try:
        asyncio.run(check_async_connection())
        print("Application connection: OK")
        check_sync_connection()
        print("Alembic connection: OK")
    except Exception as error:
        print("Database check failed:")
        print(sanitize_error(error))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
