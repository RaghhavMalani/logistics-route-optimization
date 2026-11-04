"""Assemble this domain without changing its public URL paths."""

from fastapi import APIRouter

from . import advisories, handoffs

router = APIRouter()
router.include_router(advisories.router)
router.include_router(handoffs.router)
