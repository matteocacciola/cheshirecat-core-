from fastapi import APIRouter

from cat.routes.admins.auth import router as auth_router
from cat.routes.admins.crud import router as crud_router

router = APIRouter()


router.include_router(auth_router, tags=["Admin Auth"], prefix="/auth")
router.include_router(crud_router, tags=["Admins"])
