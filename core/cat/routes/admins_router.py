from fastapi import APIRouter

from cat.routes.admins.auth import router as auth_router
from cat.routes.admins.crud import router as crud_router
from cat.routes.admins.plugins import router as plugins_router
from cat.routes.admins.utilities import router as crud_utilities

router = APIRouter()


router.include_router(auth_router, tags=["Admin Auth"], prefix="/auth")
router.include_router(plugins_router, tags=["Admin Plugins"], prefix="/plugins")
router.include_router(crud_utilities, tags=["Admin Utilities"], prefix="/utils")
router.include_router(crud_router, tags=["Admins"], prefix="/users")
