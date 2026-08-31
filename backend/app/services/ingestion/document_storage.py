from __future__ import annotations

import asyncio
import hashlib
import os
import re
import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import aiofiles
from fastapi import HTTPException, UploadFile, status

from app.core.config import settings

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True)
class StoredFile:
    document_id: str
    original_filename: str
    stored_path: str
    mime_type: str | None
    file_hash: str
    size_bytes: int


class ObjectStorage(Protocol):
    """Strategy interface for local and durable object persistence."""

    def publish(self, local_path: Path, object_name: str) -> str: ...
    def materialize(self, uri: str, destination: Path) -> None: ...
    def delete(self, uri: str) -> None: ...


class LocalObjectStorage:
    def publish(self, local_path: Path, object_name: str) -> str:
        del object_name
        return str(local_path)

    def materialize(self, uri: str, destination: Path) -> None:
        del destination
        if not Path(uri).is_file():
            raise FileNotFoundError(f"Stored document does not exist: {uri}")

    def delete(self, uri: str) -> None:
        Path(uri).unlink(missing_ok=True)


class GcsObjectStorage:
    """Google Cloud Storage adapter using Application Default Credentials."""

    def __init__(self, bucket_name: str) -> None:
        if not bucket_name.strip():
            raise ValueError("GCS_BUCKET_NAME is required when STORAGE_BACKEND=gcs")
        from google.cloud import storage

        self._bucket_name = bucket_name.strip()
        self._bucket = storage.Client().bucket(self._bucket_name)

    def publish(self, local_path: Path, object_name: str) -> str:
        blob = self._bucket.blob(object_name)
        blob.upload_from_filename(str(local_path))
        return f"gs://{self._bucket_name}/{object_name}"

    def materialize(self, uri: str, destination: Path) -> None:
        blob = self._blob_for_uri(uri)
        destination.parent.mkdir(parents=True, exist_ok=True)
        blob.download_to_filename(str(destination))

    def delete(self, uri: str) -> None:
        from google.api_core.exceptions import NotFound

        try:
            self._blob_for_uri(uri).delete()
        except NotFound:
            return

    def _blob_for_uri(self, uri: str):
        prefix = f"gs://{self._bucket_name}/"
        if not uri.startswith(prefix):
            raise ValueError("Object URI does not belong to the configured bucket")
        return self._bucket.blob(uri.removeprefix(prefix))


class DocumentStorage:
    """Facade that keeps ingestion independent of the storage provider."""

    def __init__(self, backend: ObjectStorage | None = None) -> None:
        storage_kind = settings.STORAGE_BACKEND.strip().lower()
        if storage_kind not in {"local", "gcs"}:
            raise ValueError("STORAGE_BACKEND must be 'local' or 'gcs'")

        if storage_kind == "gcs":
            root = Path(settings.EPHEMERAL_STORAGE_ROOT)
            self._backend = backend or GcsObjectStorage(settings.GCS_BUCKET_NAME)
        else:
            root = None
            self._backend = backend or LocalObjectStorage()

        self._is_local = storage_kind == "local" and isinstance(
            self._backend, LocalObjectStorage
        )
        self.upload_root = (
            Path(settings.USER_UPLOAD_DIR) if root is None else root / "uploads"
        )
        self.markdown_root = (
            Path(settings.USER_MARKDOWN_DIR) if root is None else root / "markdown"
        )

    async def save_upload(
        self,
        file: UploadFile,
        tenant_id: str,
        matter_id: str | None,
        document_id: str,
    ) -> StoredFile:
        filename = self.safe_filename(file.filename or "uploaded_document")
        extension = Path(filename).suffix.lower()
        if extension not in settings.ALLOWED_UPLOAD_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file type: {extension or 'none'}",
            )

        matter_part = self.safe_path_part(matter_id or "general")
        target_dir = (
            self.upload_root
            / self.safe_path_part(tenant_id)
            / matter_part
            / document_id
        )
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"original{extension}"

        max_bytes = settings.UPLOAD_MAX_MB * 1024 * 1024
        digest = hashlib.sha256()
        size = 0

        async with aiofiles.open(target_path, "wb") as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    try:
                        target_path.unlink(missing_ok=True)
                    finally:
                        raise HTTPException(
                            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail=f"Upload exceeds {settings.UPLOAD_MAX_MB} MB limit.",
                        )
                digest.update(chunk)
                await out.write(chunk)

        object_name = self._object_name(
            tenant_id, matter_id, document_id, f"original{extension}"
        )
        stored_path = await asyncio.to_thread(
            self._backend.publish, target_path, object_name
        )
        if not self._is_local:
            target_path.unlink(missing_ok=True)

        return StoredFile(
            document_id=document_id,
            original_filename=filename,
            stored_path=stored_path,
            mime_type=file.content_type,
            file_hash=digest.hexdigest(),
            size_bytes=size,
        )

    def markdown_path(
        self, tenant_id: str, matter_id: str | None, document_id: str
    ) -> Path:
        matter_part = self.safe_path_part(matter_id or "general")
        target_dir = (
            self.markdown_root
            / self.safe_path_part(tenant_id)
            / matter_part
            / document_id
        )
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir / "document.md"

    def persist_markdown(
        self,
        markdown_path: str,
        tenant_id: str,
        matter_id: str | None,
        document_id: str,
    ) -> str:
        path = Path(markdown_path)
        object_name = self._object_name(
            tenant_id, matter_id, document_id, "document.md"
        )
        uri = self._backend.publish(path, object_name)
        if not self._is_local:
            path.unlink(missing_ok=True)
        return uri

    @contextmanager
    def materialize(self, stored_path: str) -> Iterator[str]:
        """Yield a local path for either a local file or a GCS object."""

        if self._is_local:
            self._backend.materialize(stored_path, Path(stored_path))
            yield stored_path
            return

        suffix = Path(stored_path).suffix
        temp_dir = Path(tempfile.mkdtemp(prefix="ingestion-", dir="/tmp"))
        destination = temp_dir / f"source{suffix}"
        try:
            self._backend.materialize(stored_path, destination)
            yield str(destination)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def delete_document_files(
        self, stored_path: str | None, markdown_path: str | None
    ) -> None:
        for path_str in (stored_path, markdown_path):
            if not path_str:
                continue
            self._backend.delete(path_str)
            if self._is_local:
                self._remove_empty_parents(Path(path_str).parent)

    @staticmethod
    def safe_filename(filename: str) -> str:
        base = os.path.basename(filename).strip() or "uploaded_document"
        return _SAFE_NAME_RE.sub("_", base)[:180]

    @staticmethod
    def safe_path_part(value: str) -> str:
        return _SAFE_NAME_RE.sub("_", value.strip() or "unknown")[:120]

    def _object_name(
        self,
        tenant_id: str,
        matter_id: str | None,
        document_id: str,
        filename: str,
    ) -> str:
        parts = (
            settings.GCS_OBJECT_PREFIX.strip("/"),
            self.safe_path_part(tenant_id),
            self.safe_path_part(matter_id or "general"),
            self.safe_path_part(document_id),
            filename,
        )
        return "/".join(part for part in parts if part)

    def _remove_empty_parents(self, start: Path) -> None:
        roots = {self.upload_root.resolve(), self.markdown_root.resolve()}
        current = start
        while current.exists() and current.resolve() not in roots:
            try:
                current.rmdir()
            except OSError:
                break
            current = current.parent
