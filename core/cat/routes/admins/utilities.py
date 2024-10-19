from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from cat import utils
from cat.auth.connection import AdminConnectionAuth
from cat.auth.permissions import AdminAuthResource, AuthPermission
from cat.bill_the_lizard import BillTheLizard
from cat.db.cruds import settings as crud_settings

router = APIRouter()

class FactoryResetResponse(BaseModel):
    deleted_settings: bool
    deleted_memories: bool


@router.post("/factory-reset", response_model=FactoryResetResponse)
def factory_reset(
    request: Request,
    lizard: BillTheLizard = Depends(AdminConnectionAuth(AdminAuthResource.CHESHIRE_CATS, AuthPermission.DELETE)),
) -> FactoryResetResponse:
    """
    Factory reset the entire application. This will delete all settings, memories, and metadata.
    """

    lizard.shutdown()
    deleted_memories = True

    crud_settings.wipe_settings(lizard.config_key)
    deleted_settings = True

    utils.singleton.instances.clear()

    del request.app.state.lizard
    request.app.state.lizard = BillTheLizard()

    return FactoryResetResponse(deleted_settings=deleted_settings, deleted_memories=deleted_memories)
