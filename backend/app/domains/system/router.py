"""Assemble this domain without changing its public URL paths."""

from fastapi import APIRouter

from . import health, auth, provenance, demo, demo_terminal, screens, agents, admin

router = APIRouter()
router.include_router(health.router)
router.include_router(auth.router)
router.include_router(provenance.router)
router.include_router(demo.router)
router.include_router(demo_terminal.router)
router.include_router(screens.router)
router.include_router(agents.router)
router.include_router(admin.router)
