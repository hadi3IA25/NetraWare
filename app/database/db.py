from __future__ import annotations

import logging
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from importlib import import_module
from pathlib import Path
from typing import Generator

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

LOGGER = logging.getLogger(__name__)
ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")
SCHEMA_VERSION = 4


class DatabaseSchemaError(RuntimeError):
    pass


@dataclass
class DatabaseStatus:
    ready: bool = False
    backend: str = "unknown"
    schema_version: int = 0
    migrated_columns: tuple[str, ...] = ()
    message: str = "Database belum diinisialisasi."

    def to_dict(self) -> dict:
        return asdict(self)


_database_status = DatabaseStatus()


def normalize_database_url(raw_url: str | None) -> str:
    value = (raw_url or "").strip()
    if not value:
        raise RuntimeError(
            "DATABASE_URL belum diatur. Salin .env.example menjadi .env dan isi koneksi PostgreSQL."
        )
    if value.startswith("postgres://"):
        return value.replace("postgres://", "postgresql+psycopg2://", 1)
    if value.startswith("postgresql://"):
        return value.replace("postgresql://", "postgresql+psycopg2://", 1)
    if value.startswith("sqlite:///./"):
        relative = value.removeprefix("sqlite:///./")
        return f"sqlite:///{(ROOT_DIR / relative).resolve().as_posix()}"
    return value


DATABASE_URL = normalize_database_url(os.getenv("DATABASE_URL"))


def build_engine(database_url: str = DATABASE_URL) -> Engine:
    is_sqlite = database_url.startswith("sqlite")
    kwargs: dict = {"pool_pre_ping": True}
    if is_sqlite:
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
        if database_url.endswith(":memory:"):
            kwargs["poolclass"] = StaticPool
    else:
        kwargs.update(
            connect_args={"connect_timeout": 8},
            pool_recycle=300,
            pool_size=5,
            max_overflow=10,
        )
    return create_engine(database_url, **kwargs)


engine = build_engine()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)
Base = declarative_base()


def _write_schema_version(target_engine: Engine) -> None:
    with target_engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS app_schema_meta (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                schema_version INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            )
        """))
        connection.execute(
            text("""
                INSERT INTO app_schema_meta (id, schema_version, updated_at)
                VALUES (1, :version, :updated_at)
                ON CONFLICT(id) DO UPDATE SET
                    schema_version = excluded.schema_version,
                    updated_at = excluded.updated_at
            """),
            {"version": SCHEMA_VERSION, "updated_at": datetime.now(timezone.utc).isoformat()},
        )


def migrate_database_schema(target_engine: Engine) -> tuple[str, ...]:
    inspector = inspect(target_engine)
    if "metric_records" not in inspector.get_table_names():
        _write_schema_version(target_engine)
        return ()

    existing = {column["name"] for column in inspector.get_columns("metric_records")}
    default = "FALSE" if target_engine.dialect.name == "postgresql" else "0"
    applied: list[str] = []
    with target_engine.begin() as connection:
        for column in ("blink_rate_ready", "perclos_ready"):
            if column not in existing:
                connection.execute(text(
                    f"ALTER TABLE metric_records ADD COLUMN {column} BOOLEAN NOT NULL DEFAULT {default}"
                ))
                applied.append(f"metric_records.{column}")
    _write_schema_version(target_engine)
    return tuple(applied)


def validate_database_schema(target_engine: Engine) -> None:
    import_module("app.database.models")
    inspector = inspect(target_engine)
    existing_tables = set(inspector.get_table_names())
    missing: list[str] = []
    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            missing.append(f"table:{table.name}")
            continue
        columns = {column["name"] for column in inspector.get_columns(table.name)}
        missing.extend(f"{table.name}.{column.name}" for column in table.columns if column.name not in columns)
    if missing:
        raise DatabaseSchemaError("Schema database tidak sesuai: " + ", ".join(missing))


def init_db() -> DatabaseStatus:
    global _database_status
    try:
        import_module("app.database.models")
        Base.metadata.create_all(bind=engine)
        migrated = migrate_database_schema(engine)
        validate_database_schema(engine)
    except (SQLAlchemyError, DatabaseSchemaError) as exc:
        LOGGER.exception("Inisialisasi database gagal.")
        raise RuntimeError(
            "PostgreSQL gagal diinisialisasi. Periksa DATABASE_URL, service PostgreSQL, dan log aplikasi."
        ) from exc

    _database_status = DatabaseStatus(
        ready=True,
        backend=engine.dialect.name,
        schema_version=SCHEMA_VERSION,
        migrated_columns=migrated,
        message="Database siap; migrasi otomatis diterapkan." if migrated else "Database siap.",
    )
    return _database_status


def get_database_status() -> DatabaseStatus:
    return _database_status


def verify_database_connection() -> bool:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError:
        LOGGER.exception("Pemeriksaan koneksi database gagal.")
        return False


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
