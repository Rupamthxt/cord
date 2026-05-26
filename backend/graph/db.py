"""
backend/graph/db.py
-------------------
PostgreSQL async database engine, session factory, and lifecycle utilities
for the Cord entity-graph layer.

Uses SQLAlchemy 2.0 async with asyncpg driver.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DATABASE_URL: str = os.getenv(
    "GRAPH_DATABASE_URL",
    "postgresql+asyncpg://cord:cord@localhost:5432/cord_graph",
)

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# ---------------------------------------------------------------------------
# Declarative base (shared by all ORM models in this package)
# ---------------------------------------------------------------------------

Base = declarative_base()

# ---------------------------------------------------------------------------
# Dependency / context manager
# ---------------------------------------------------------------------------


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Async context manager that yields a transactional database session.

    Commits on clean exit, rolls back on any exception, and always closes
    the session.

    Example::

        async with get_db_session() as session:
            result = await session.execute(select(Entity))
    """
    session: AsyncSession = AsyncSessionLocal()
    try:
        yield session
        await session.commit()
    except SQLAlchemyError as exc:
        await session.rollback()
        logger.error(
            "Database session error — rolled back transaction: %s",
            exc,
            exc_info=True,
        )
        raise
    except Exception as exc:
        await session.rollback()
        logger.error(
            "Unexpected error in DB session — rolled back: %s",
            exc,
            exc_info=True,
        )
        raise
    finally:
        await session.close()


# ---------------------------------------------------------------------------
# Lifecycle helpers
# ---------------------------------------------------------------------------


async def init_db() -> None:
    """Create all tables defined by ORM models.

    Models are imported *inside* this function to prevent circular imports
    at module load time (models import Base from this module).
    """
    # Lazy import — entities.models registers tables against Base
    import backend.graph.entities.models  # noqa: F401  # registers metadata
    import backend.graph.events.models  # noqa: F401  # registers event metadata
    import backend.intelligence.insights.models  # noqa: F401  # registers insights metadata
    import backend.intelligence.workflows.models  # noqa: F401  # registers workflows metadata


    logger.info("Initialising database schema on %s …", DATABASE_URL)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database schema initialisation complete.")
    except OperationalError as exc:
        logger.critical(
            "Could not connect to the database at %s during init_db: %s",
            DATABASE_URL,
            exc,
            exc_info=True,
        )
        raise
    except SQLAlchemyError as exc:
        logger.error("Schema creation failed: %s", exc, exc_info=True)
        raise


async def check_db_health() -> bool:
    """Probe the database with a lightweight SELECT 1.

    Returns:
        ``True`` if the database is reachable, ``False`` otherwise.
    """
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        logger.debug("Database health check passed.")
        return True
    except OperationalError as exc:
        logger.error(
            "Database health check failed (OperationalError): %s",
            exc,
            exc_info=True,
        )
        return False
    except SQLAlchemyError as exc:
        logger.error(
            "Database health check failed (SQLAlchemyError): %s",
            exc,
            exc_info=True,
        )
        return False
    except Exception as exc:  # pylint: disable=broad-except
        logger.error(
            "Database health check failed (unexpected): %s",
            exc,
            exc_info=True,
        )
        return False
