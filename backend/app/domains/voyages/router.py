"""Assemble this domain without changing its public URL paths."""

from fastapi import APIRouter

from . import fleet, scenarios, company, decisions, commercial, finance, missions

router = APIRouter()
router.include_router(fleet.router)
router.include_router(scenarios.router)
router.include_router(company.router)
router.include_router(decisions.router)
router.include_router(commercial.router)
router.include_router(finance.router)
router.include_router(missions.router)
