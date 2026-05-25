"""Shared helpers for handling FastAPI UploadFile inputs.

Streams uploads to a temp file in bounded chunks so a large request can't
balloon worker memory, and enforces a configurable per-file size cap.
"""
from __future__ import annotations

import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import HTTPException, UploadFile

CHUNK_BYTES = 1 << 20  # 1 MiB
MAX_UPLOAD_BYTES = 512 * 1024 * 1024  # 512 MiB hard cap per file


@asynccontextmanager
async def upload_to_tempfile(
    upload: UploadFile,
    *,
    default_suffix: str = "",
    max_bytes: int = MAX_UPLOAD_BYTES,
):
    """Stream `upload` to a NamedTemporaryFile and yield its Path.

    The file is unlinked on context exit even if the caller raises.
    """
    suffix = Path(upload.filename or "").suffix.lower() or default_suffix
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp_path = Path(tmp.name)
    total = 0
    try:
        try:
            while chunk := await upload.read(CHUNK_BYTES):
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Upload exceeds {max_bytes // (1024 * 1024)} MiB limit",
                    )
                tmp.write(chunk)
        finally:
            tmp.close()
        yield tmp_path
    finally:
        tmp_path.unlink(missing_ok=True)
