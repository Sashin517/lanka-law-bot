from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path

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


class DocumentStorage:
    def __init__(self) -> None:
        self.upload_root = Path(settings.USER_UPLOAD_DIR)
        self.markdown_root = Path(settings.USER_MARKDOWN_DIR)

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
        target_dir = self.upload_root / self.safe_path_part(tenant_id) / matter_part / document_id
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

        return StoredFile(
            document_id=document_id,
            original_filename=filename,
            stored_path=str(target_path),
            mime_type=file.content_type,
            file_hash=digest.hexdigest(),
            size_bytes=size,
        )

    def markdown_path(self, tenant_id: str, matter_id: str | None, document_id: str) -> Path:
        matter_part = self.safe_path_part(matter_id or "general")
        target_dir = self.markdown_root / self.safe_path_part(tenant_id) / matter_part / document_id
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir / "document.md"

    def delete_document_files(self, stored_path: str | None, markdown_path: str | None) -> None:
        for path_str in (stored_path, markdown_path):
            if not path_str:
                continue
            path = Path(path_str)
            if path.exists():
                path.unlink()
            self._remove_empty_parents(path.parent)

    @staticmethod
    def safe_filename(filename: str) -> str:
        base = os.path.basename(filename).strip() or "uploaded_document"
        return _SAFE_NAME_RE.sub("_", base)[:180]

    @staticmethod
    def safe_path_part(value: str) -> str:
        return _SAFE_NAME_RE.sub("_", value.strip() or "unknown")[:120]

    def _remove_empty_parents(self, start: Path) -> None:
        roots = {self.upload_root.resolve(), self.markdown_root.resolve()}
        current = start
        while current.exists() and current.resolve() not in roots:
            try:
                current.rmdir()
            except OSError:
                break
            current = current.parent
