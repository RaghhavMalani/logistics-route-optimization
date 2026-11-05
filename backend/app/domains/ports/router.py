"""Assemble this domain without changing its public URL paths."""

from fastapi import APIRouter

from . import model, ports, arrivals, public_arrivals, weather_verification, weather, port_twin

router = APIRouter()
router.include_router(model.router)
router.include_router(ports.router)
router.include_router(arrivals.router)
router.include_router(public_arrivals.router)
router.include_router(weather_verification.router)
router.include_router(weather.router)
router.include_router(port_twin.router)
