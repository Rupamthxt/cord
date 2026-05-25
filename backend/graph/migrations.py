"""
backend/graph/migrations.py
---------------------------
Database schema initialization script for the Cord PostgreSQL entity graph.

Run with:
    python -m backend.graph.migrations
"""

import asyncio
import logging
import sys

from backend.graph.db import DATABASE_URL, check_db_health, init_db

logger = logging.getLogger("backend.graph.migrations")


async def run_migrations() -> None:
    """Checks the database health and runs the schema initialization."""
    logger.info("Starting schema migration...")
    
    # 1. Check DB connection / reachability
    db_available = await check_db_health()
    if not db_available:
        logger.critical(
            "Database at %s is NOT reachable. Please ensure PostgreSQL is running and the credentials in GRAPH_DATABASE_URL are correct.",
            DATABASE_URL,
        )
        sys.exit(1)

    # 2. Run metadata create_all
    try:
        await init_db()
        logger.info("Database schema migrated successfully.")
    except Exception as exc:
        logger.critical("Migration failed with an exception: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    asyncio.run(run_migrations())
