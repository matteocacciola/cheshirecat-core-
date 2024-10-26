from fastapi import APIRouter

from cat.routes.memory.points import router as points_router
from cat.routes.memory.collections import router as collections_router
from cat.routes.memory.convo_history import router as convo_history_router

router = APIRouter()

router.include_router(collections_router, tags=["Vector Memory - Collections"])
router.include_router(convo_history_router, tags=["Working Memory - Current Conversation"])
router.include_router(points_router, tags=["Vector Memory - Points"])
