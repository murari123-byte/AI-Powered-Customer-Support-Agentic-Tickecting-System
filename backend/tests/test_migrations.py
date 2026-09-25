"""Migrations are code, so they are tested like code, against the real test database."""

import pytest
from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, text

from tests.conftest import alembic_config

pytestmark = pytest.mark.db


def _vector_extension_installed(engine: Engine) -> bool:
    with engine.connect() as connection:
        return bool(connection.execute(text("SELECT count(*) FROM pg_extension WHERE extname = 'vector'")).scalar())


def _current_revision(engine: Engine) -> str | None:
    with engine.connect() as connection:
        return connection.execute(text("SELECT version_num FROM alembic_version")).scalar()


def test_database_is_at_latest_revision(migrated_engine: Engine) -> None:
    head = ScriptDirectory.from_config(alembic_config(migrated_engine)).get_current_head()

    assert _current_revision(migrated_engine) == head


def test_pgvector_extension_is_enabled(migrated_engine: Engine) -> None:
    assert _vector_extension_installed(migrated_engine)


def test_full_downgrade_then_upgrade_round_trip(migrated_engine: Engine) -> None:
    """Every migration can be rolled back and re-applied cleanly."""
    config = alembic_config(migrated_engine)

    command.downgrade(config, "base")
    assert not _vector_extension_installed(migrated_engine)
    assert _current_revision(migrated_engine) is None

    command.upgrade(config, "head")
    assert _vector_extension_installed(migrated_engine)


def test_models_match_migrations(migrated_engine: Engine) -> None:
    """Fails if a model was changed without a migration (alembic check = autogenerate dry run)."""
    command.check(alembic_config(migrated_engine))


def test_migration_chain_is_linear(migrated_engine: Engine) -> None:
    """Exactly one head: two branches would mean two developers' migrations were not merged."""
    heads = ScriptDirectory.from_config(alembic_config(migrated_engine)).get_heads()

    assert len(heads) == 1
