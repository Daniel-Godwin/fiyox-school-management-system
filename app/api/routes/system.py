"""System endpoints (health checks, liveness)."""
from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
async def health():
    return {"status": "ok"}
