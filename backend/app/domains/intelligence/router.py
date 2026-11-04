"""Assemble this domain without changing its public URL paths."""

from fastapi import APIRouter

from . import intelligence, current_inputs, public_research, public_workspace, shipping_intelligence, operational_evidence, shared_feedback, navigation_restrictions, operational_notices, learning, capabilities

router = APIRouter()
router.include_router(intelligence.router)
router.include_router(current_inputs.router)
router.include_router(public_research.router)
router.include_router(public_workspace.router)
router.include_router(shipping_intelligence.router)
router.include_router(operational_evidence.router)
router.include_router(shared_feedback.router)
router.include_router(navigation_restrictions.router)
router.include_router(operational_notices.router)
router.include_router(learning.router)
router.include_router(capabilities.router)
