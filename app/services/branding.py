"""School branding assets — logo, principal's signature, school stamp.

Images are stored as data URIs on the school row. That keeps deployment free
and simple (no S3 bucket, no disk that Render's free tier would wipe on every
restart), and these are small assets: we cap them and reject anything larger.
When the platform grows, swapping to object storage means changing only this
module — the report card just reads `school.logo_url`.
"""
import base64
from fastapi import HTTPException, UploadFile

MAX_BYTES = 300_000  # ~300 KB is generous for a logo/signature/stamp
ALLOWED = {"image/png": "png", "image/jpeg": "jpg", "image/jpg": "jpg"}


async def to_data_uri(file: UploadFile) -> str:
    if file.content_type not in ALLOWED:
        raise HTTPException(
            status_code=400,
            detail="Please upload a PNG or JPEG image")
    raw = await file.read()
    if len(raw) > MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Image is too large ({len(raw)//1024} KB). Please use one under 300 KB.")
    if not raw:
        raise HTTPException(status_code=400, detail="The file is empty")
    encoded = base64.b64encode(raw).decode()
    return f"data:{file.content_type};base64,{encoded}"


def data_uri_to_bytes(uri: str | None) -> bytes | None:
    """For reportlab, which needs real bytes."""
    if not uri or not uri.startswith("data:"):
        return None
    try:
        return base64.b64decode(uri.split(",", 1)[1])
    except Exception:
        return None
