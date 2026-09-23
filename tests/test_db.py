from pathlib import Path

import pytest
from sqlalchemy import text

from la_rp_peace.db import make_engine


def test_file_database_enforces_foreign_keys_and_uses_wal(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{(tmp_path / 'nested' / 'app.sqlite3').as_posix()}")

    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar() == 1
        assert connection.execute(text("PRAGMA journal_mode")).scalar() == "wal"
    assert (tmp_path / "nested" / "app.sqlite3").exists()
    engine.dispose()


def test_memory_database_enforces_foreign_keys() -> None:
    engine = make_engine("sqlite+pysqlite:///:memory:")

    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar() == 1


def test_other_databases_are_rejected() -> None:
    with pytest.raises(ValueError, match="Only SQLite"):
        make_engine("postgresql://user:pass@localhost/db")
