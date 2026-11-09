"""Verify the additive history migration on both upgrade and fresh-schema paths."""

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text


def test_version_table_migration_is_additive_and_idempotent(monkeypatch):
    path = Path(__file__).parents[1] / "alembic/versions/20261109_15_transcript_versions.py"
    spec = importlib.util.spec_from_file_location("transcript_versions_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE slide_transcripts (id CHAR(32) PRIMARY KEY)"))
        connection.execute(text("INSERT INTO slide_transcripts VALUES ('existing-script')"))
        monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(connection)))
        migration.upgrade()
        migration.upgrade()
        assert "transcript_versions" in inspect(connection).get_table_names()
        assert connection.scalar(text("SELECT count(*) FROM slide_transcripts")) == 1
        columns = {
            column["name"] for column in inspect(connection).get_columns("transcript_versions")
        }
        assert {"snapshot", "revision", "change_type", "restored_from_id"} <= columns
        migration.downgrade()
        assert "transcript_versions" not in inspect(connection).get_table_names()
        assert connection.scalar(text("SELECT count(*) FROM slide_transcripts")) == 1
    engine.dispose()
