from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from cat import utils
from cat.auth.auth_utils import extract_agent_id_from_request
from cat.auth.connection import AdminConnectionAuth
from cat.auth.permissions import AdminAuthResource, AuthPermission
from cat.bill_the_lizard import BillTheLizard
from cat.db.cruds import settings as crud_settings

router = APIRouter()

class ResetResponse(BaseModel):
    deleted_settings: bool
    deleted_memories: bool


@router.post("/factory_reset", response_model=ResetResponse)
async  def factory_reset(
    request: Request,
    lizard: BillTheLizard = Depends(AdminConnectionAuth(AdminAuthResource.CHESHIRE_CATS, AuthPermission.DELETE)),
) -> ResetResponse:
    """
    Factory reset the entire application. This will delete all settings, memories, and metadata.
    """

    for ccat in lizard.cheshire_cats:
        ccat.wipe()

    await lizard.shutdown()
    deleted_memories = True

    crud_settings.wipe_settings(lizard.config_key)
    deleted_settings = True

    utils.singleton.instances.clear()

    del request.app.state.lizard
    request.app.state.lizard = BillTheLizard()

    return ResetResponse(deleted_settings=deleted_settings, deleted_memories=deleted_memories)


@router.post("/agent_reset", response_model=ResetResponse)
async def agent_reset(
    request: Request,
    lizard: BillTheLizard = Depends(AdminConnectionAuth(AdminAuthResource.CHESHIRE_CATS, AuthPermission.DELETE)),
) -> ResetResponse:
    """
    Reset a single agent. This will delete all settings, memories, and metadata, for the agent.
    """

    agent_id = extract_agent_id_from_request(request)
    ccat = lizard.get_cheshire_cat(agent_id)
    if not ccat:
        return ResetResponse(deleted_settings=False, deleted_memories=False)

    ccat.wipe()
    await lizard.remove_cheshire_cat(agent_id)

    return ResetResponse(deleted_settings=True, deleted_memories=True)
