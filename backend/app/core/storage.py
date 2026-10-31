import re
import uuid
from pathlib import Path

from fastapi import UploadFile

from app.config import get_settings
from app.exceptions import ValidationFailedError

settings = get_settings()

ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "application/pdf",
}

# The client-supplied Content-Type header is just a hint - a request can
# claim anything regardless of the bytes actually sent. These magic-byte
# signatures are checked against the real file contents so a disguised
# executable/script can't pass the allowlist by sending a false header;
# no extra dependency (e.g. python-magic) needed for a 4-type allowlist.
_MAGIC_BYTES: dict[str, tuple[bytes, ...]] = {
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/webp": (b"RIFF",),  # full check (the "WEBP" tag at offset 8) below
    "application/pdf": (b"%PDF-",),
}

_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]")


def _matches_content_type(contents: bytes, content_type: str) -> bool:
    if content_type == "image/webp":
        return contents[:4] == b"RIFF" and contents[8:12] == b"WEBP"
    return contents.startswith(_MAGIC_BYTES[content_type])


def _sanitize_filename(filename: str) -> str:
    # Keep only the basename (no directory components a client could send
    # to escape the intended storage path) and strip anything that isn't a
    # safe filename character.
    base = Path(filename).name
    return _UNSAFE_FILENAME_CHARS.sub("_", base) or "file"


async def save_evidence_upload(
    file: UploadFile, *, organization_id: uuid.UUID, entity_type: str, entity_id: uuid.UUID
) -> tuple[str, int]:
    """
    Validates and saves one uploaded evidence file to local disk, returning
    (storage_key, size_bytes). Raises ValidationFailedError for anything that
    fails validation - never writes a partial/oversized/wrong-type file.
    """
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise ValidationFailedError(
            f"Unsupported file type '{file.content_type}'. Allowed: {', '.join(sorted(ALLOWED_CONTENT_TYPES))}."
        )

    # Read in chunks and abort as soon as the limit is crossed, rather than
    # buffering an arbitrarily large upload into memory first and only
    # then checking its size - the previous shape let a client force this
    # process to hold a multi-gigabyte body before rejecting it.
    chunks: list[bytes] = []
    total = 0
    chunk_size = 1024 * 1024
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        total += len(chunk)
        if total > settings.max_upload_size_bytes:
            raise ValidationFailedError(
                f"File exceeds the maximum allowed size of {settings.max_upload_size_bytes} bytes."
            )
        chunks.append(chunk)
    contents = b"".join(chunks)

    if len(contents) == 0:
        raise ValidationFailedError("Uploaded file is empty.")
    if not _matches_content_type(contents, file.content_type):
        raise ValidationFailedError(
            f"File contents do not match the declared type '{file.content_type}'."
        )

    safe_name = _sanitize_filename(file.filename or "file")
    relative_path = Path(str(organization_id)) / entity_type / str(entity_id) / f"{uuid.uuid4()}_{safe_name}"
    full_path = Path(settings.upload_dir) / relative_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_bytes(contents)

    return str(relative_path).replace("\\", "/"), len(contents)


def resolve_storage_path(storage_key: str) -> Path:
    return Path(settings.upload_dir) / storage_key
