from pathlib import Path

from sqlalchemy import create_engine, inspect, text

from app.database.db import migrate_database_schema, normalize_database_url


def test_migrates_metric_readiness_columns_once(tmp_path: Path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'legacy.db').as_posix()}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE metric_records (id INTEGER PRIMARY KEY)"))

    applied = migrate_database_schema(engine)
    columns = {column["name"] for column in inspect(engine).get_columns("metric_records")}

    assert set(applied) == {
        "metric_records.blink_rate_ready",
        "metric_records.perclos_ready",
    }
    assert {"blink_rate_ready", "perclos_ready"}.issubset(columns)
    assert migrate_database_schema(engine) == ()
    engine.dispose()


def test_normalizes_railway_postgres_url():
    expected = "postgresql+psycopg2://user:pass@host:5432/db"
    assert normalize_database_url("postgres://user:pass@host:5432/db") == expected
    assert normalize_database_url("postgresql://user:pass@host:5432/db") == expected
