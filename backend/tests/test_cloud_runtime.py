from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import patch

from app.core.config import Settings, settings
from app.core.logging_config import CloudRunJsonFormatter
from app.database.postgres_session import postgres_async_connect_args
from app.services.ingestion.document_storage import DocumentStorage


class InMemoryObjectStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def publish(self, local_path: Path, object_name: str) -> str:
        self.objects[object_name] = local_path.read_bytes()
        return f"gs://test-bucket/{object_name}"

    def materialize(self, uri: str, destination: Path) -> None:
        object_name = uri.removeprefix("gs://test-bucket/")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(self.objects[object_name])

    def delete(self, uri: str) -> None:
        object_name = uri.removeprefix("gs://test-bucket/")
        self.objects.pop(object_name, None)


def test_managed_database_url_is_normalized_for_both_drivers() -> None:
    config = Settings(
        _env_file=None,
        DATABASE_URL=(
            "postgresql://legal:p%40ss@db.example.test/law"
            "?sslmode=require&application_name=lankalawbot"
        ),
    )

    assert config.postgres_url.drivername == "postgresql+asyncpg"
    assert config.postgres_url.query["ssl"] == "require"
    assert "sslmode" not in config.postgres_url.query
    assert "application_name" not in config.postgres_url.query
    assert config.postgres_sync_url.drivername == "postgresql+psycopg"
    assert config.postgres_sync_url.query["sslmode"] == "require"
    assert config.postgres_sync_url.query["application_name"] == "lankalawbot"


def test_runtime_cors_origins_are_normalized_and_deduplicated() -> None:
    config = Settings(
        _env_file=None,
        CORS_ORIGINS=["http://localhost:3000"],
        CORS_ORIGINS_STR=("https://frontend.example.test/, http://localhost:3000"),
    )

    assert config.effective_cors_origins == [
        "http://localhost:3000",
        "https://frontend.example.test",
    ]


def test_production_cors_can_exclude_local_development_origins() -> None:
    config = Settings(
        _env_file=None,
        CORS_ORIGINS=["http://localhost:3000"],
        CORS_ORIGINS_STR="https://frontend.example.test",
        CORS_INCLUDE_LOCALHOST=False,
    )

    assert config.effective_cors_origins == ["https://frontend.example.test"]


def test_managed_postgres_uses_certificate_verifying_ssl_context() -> None:
    with (
        patch.object(settings, "POSTGRES_SSLMODE", "require"),
        patch("app.database.postgres_session.ssl.create_default_context") as context,
    ):
        ssl_context = object()
        context.return_value = ssl_context

        assert postgres_async_connect_args() == {"ssl": ssl_context}

    context.assert_called_once_with()


def test_cloud_logging_formatter_emits_structured_payload() -> None:
    record = logging.LogRecord(
        name="test.logger",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="capacity warning",
        args=(),
        exc_info=None,
    )

    payload = json.loads(CloudRunJsonFormatter().format(record))

    assert payload["severity"] == "WARNING"
    assert payload["message"] == "capacity warning"
    assert payload["logger"] == "test.logger"
    assert payload["timestamp"].endswith("+00:00")


def test_gcs_strategy_materializes_and_deletes_objects(tmp_path: Path) -> None:
    backend = InMemoryObjectStorage()
    source = tmp_path / "source.txt"
    source.write_text("Sri Lankan legal material", encoding="utf-8")

    with (
        patch.object(settings, "STORAGE_BACKEND", "gcs"),
        patch.object(settings, "EPHEMERAL_STORAGE_ROOT", str(tmp_path / "temp")),
        patch.object(settings, "GCS_OBJECT_PREFIX", "documents"),
    ):
        storage = DocumentStorage(backend=backend)
        uri = storage.persist_markdown(str(source), "tenant", "matter", "document-id")
        assert uri == (
            "gs://test-bucket/documents/tenant/matter/document-id/document.md"
        )
        assert not source.exists()

        with storage.materialize(uri) as local_path:
            assert Path(local_path).read_text(encoding="utf-8") == (
                "Sri Lankan legal material"
            )
            materialized_path = Path(local_path)
        assert not materialized_path.exists()

        storage.delete_document_files(uri, None)
        assert backend.objects == {}
