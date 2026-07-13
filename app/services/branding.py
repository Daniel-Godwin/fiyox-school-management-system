"""School branding assets — logo, principal's signature, school stamp.

Images are stored as data URIs on the school row. That keeps deployment free
and simple (no S3 bucket, no disk that Render's free tier would wipe on every
restart), and these are small assets: we cap them and reject anything larger.
When the platform grows, swapping to object storage means changing only this
module — the report card just reads `school.logo_url`.

Format is decided by the file's *magic bytes*, not the browser's label:
Windows browsers frequently send a valid PNG as 'application/octet-stream',
and rejecting those would be wrong.
"""
import base64
from fastapi import HTTPException, UploadFile

MAX_BYTES = 300_000  # ~300 KB is generous for a logo/signature/stamp

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"
WEBP_HEAD = b"RIFF"


def _sniff(raw: bytes) -> str | None:
    """The real image type, from the bytes themselves."""
    if raw.startswith(PNG_MAGIC):
        return "image/png"
    if raw.startswith(JPEG_MAGIC):
        return "image/jpeg"
    if raw[:4] == WEBP_HEAD and raw[8:12] == b"WEBP":
        return "image/webp"
    return None


async def to_data_uri(file: UploadFile) -> str:
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="The file is empty")
    if len(raw) > MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Image is too large ({len(raw)//1024} KB). Please use one under 300 KB.")

    mime = _sniff(raw)
    if not mime:
        raise HTTPException(
            status_code=400,
            detail="That file is not a PNG, JPEG or WebP image. "
                   "Please export the picture as PNG or JPEG and try again.")

    encoded = base64.b64encode(raw).decode()
    return f"data:{mime};base64,{encoded}"


def data_uri_to_bytes(uri: str | None) -> bytes | None:
    """For reportlab, which needs real bytes."""
    if not uri or not uri.startswith("data:"):
        return None
    try:
        return base64.b64decode(uri.split(",", 1)[1])
    except Exception:
        return None
