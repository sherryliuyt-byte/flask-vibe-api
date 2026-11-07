import os
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import create_engine, pool
from sqlalchemy.engine import make_url

from extensions import db


config = context.config
project_dir = Path(__file__).resolve().parents[1]

if not os.environ.get("DATABASE_URL"):
    load_dotenv(project_dir / ".env")

database_url = os.environ.get("DATABASE_URL")
if not database_url:
    raise RuntimeError(
        "DATABASE_URL is not set. Set it in the environment or project .env file."
    )

database_uri = make_url(database_url)
if database_uri.drivername in {"postgres", "postgresql"}:
    database_url = database_uri.set(
        drivername="postgresql+psycopg2"
    ).render_as_string(hide_password=False)

config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = db.metadata


def run_migrations_offline():
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = create_engine(
        database_url,
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
