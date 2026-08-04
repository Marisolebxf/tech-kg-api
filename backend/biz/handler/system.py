"""System-level endpoints that are intentionally outside the versioned API prefix."""

from fastapi import APIRouter

router = APIRouter(tags=["system"])


@router.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
