from fastapi import APIRouter, Depends, Request, HTTPException

from cat import utils
from cat.auth.connection import AdminConnectionAuth
from cat.auth.permissions import AdminAuthResource, AuthPermission
from cat.bill_the_lizard import BillTheLizard
from cat.db.cruds import settings as crud_settings

router = APIRouter()

@router.post("/factory-reset")
def factory_reset(
    request: Request,
    lizard: BillTheLizard = Depends(AdminConnectionAuth(AdminAuthResource.CHESHIRE_CATS, AuthPermission.DELETE)),
):
    """
    Factory reset the entire application. This will delete all settings, memories, and metadata.
    """

    try:
        lizard.shutdown()
        deleted_memories = True

        crud_settings.wipe_settings(lizard.config_key)
        deleted_settings = True

        utils.singleton.instances.clear()

        del request.app.state.lizard
        request.app.state.lizard = BillTheLizard()

        return {"deleted_settings": deleted_settings, "deleted_memories": deleted_memories}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "error": f"An unexpected error occurred during factory reset: {str(e)}",
            },
        )
