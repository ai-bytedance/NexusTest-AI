from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.db.base import Base

def get_database_url() -> str:
    """Get database URL directly from environment variables for Alembic.
    
    This avoids importing the full Settings class which may fail due to
    validation errors in unrelated configuration (e.g., CORS, AI providers).
    
    Priority order:
    1. DATABASE_URL environment variable
    2. Construct from POSTGRES_* variables (for Docker Compose compatibility)
    3. Fallback to default PostgreSQL URL
    """
    # First try DATABASE_URL
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        # Convert async driver to sync driver for Alembic
        if database_url.startswith("postgresql+asyncpg"):
            database_url = database_url.replace("postgresql+asyncpg", "postgresql+psycopg", 1)
        elif database_url.startswith("postgresql+psycopg2"):
            database_url = database_url.replace("postgresql+psycopg2", "postgresql+psycopg", 1)
        return database_url
    
    # Try to construct from POSTGRES_* variables (Docker Compose compatibility)
    postgres_user = os.getenv("POSTGRES_USER", "app")
    postgres_password = os.getenv("POSTGRES_PASSWORD", "app")
    postgres_db = os.getenv("POSTGRES_DB", "app")
    postgres_host = os.getenv("POSTGRES_HOST", "localhost")
    postgres_port = os.getenv("POSTGRES_PORT", "5432")
    
    return f"postgresql+psycopg://{postgres_user}:{postgres_password}@{postgres_host}:{postgres_port}/{postgres_db}"


# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set database URL directly from environment variables
database_url = get_database_url()
config.set_main_option("sqlalchemy.url", database_url)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
# target_metadata = None
# pylint: disable=invalid-name
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        future=True,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
