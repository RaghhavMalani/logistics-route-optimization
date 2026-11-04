"""Assemble this domain without changing its public URL paths."""

from fastapi import APIRouter

from . import news, sar, global_eye, world, lenses

router = APIRouter()
router.include_router(news.router)
router.include_router(sar.router)
router.include_router(global_eye.router)
router.include_router(world.router)
router.include_router(lenses.router)
