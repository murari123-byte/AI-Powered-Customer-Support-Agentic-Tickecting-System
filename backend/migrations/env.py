"""Alembic environment: tells Alembic which database to migrate and which models to compare.

The database URL comes from app settings (.env), never from alembic.ini, so no password is
stored in a config file. Choose the target database:

    alembic upgrade head               # development database (POSTGRES_DB)
    alembic -x db=test upgrade head    # test database (TEST_POSTGRES_DB)

Code (tests) can also pass a URL: config.attributes["url"] = <sqlalchemy URL>.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

import app.models  # noqa: F401  (imports every model so autogenerate can see its table)
from app.core.config import get_settings
from app.db.base import Base

config = context.config

# Set up logging from alembic.ini, but not when called from code (tests keep their own logging).
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url():
    if "url" in config.attributes:
        return config.attributes["url"]
    use_test_db = context.get_x_argument(as_dictionary=True).get("db") == "test"
    return get_settings().database_url(test=use_test_db)


def run_migrations_offline() -> None:
    """`alembic upgrade head --sql`: print the SQL instead of running it (useful for review)."""
    context.configure(
        # Offline mode never connects; the URL only selects the SQL dialect, so hide the password.
        url=_database_url().render_as_string(hide_password=True),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
