from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from cat import utils
from cat.auth.auth_utils import extract_agent_id_from_request
from cat.auth.connection import AdminConnectionAuth
from cat.auth.permissions import AdminAuthResource, AuthPermission
from cat.bill_the_lizard import BillTheLizard
from cat.db.database import get_db
from cat.log import log
from cat.utils import empty_plugin_folder

router = APIRouter()

class ResetResponse(BaseModel):
    deleted_settings: bool
    deleted_memories: bool
    deleted_plugin_folders: bool


@router.post("/factory_reset", response_model=ResetResponse)
async def factory_reset(
    request: Request,
    lizard: BillTheLizard = Depends(AdminConnectionAuth(AdminAuthResource.CHESHIRE_CATS, AuthPermission.DELETE)),
) -> ResetResponse:
    """
    Factory reset the entire application. This will delete all settings, memories, and metadata.
    """

    try:
        for ccat in lizard.cheshire_cats.values():
            await ccat.destroy()
        deleted_settings = True
    except Exception as e:
        log.error(f"Error deleting settings: {e}")
        traceback.print_exc()
        deleted_settings = False

    try:
        await lizard.shutdown()
        get_db().flushdb()
        deleted_memories = True
    except Exception as e:
        log.error(f"Error deleting memories: {e}")
        deleted_memories = False

    try:
        empty_plugin_folder()
        deleted_plugin_folders = True
    except Exception as e:
        log.error(f"Error deleting plugin folders: {e}")
        deleted_plugin_folders = False

    utils.singleton.instances.clear()

    del request.app.state.lizard
    request.app.state.lizard = BillTheLizard()

    return ResetResponse(
        deleted_settings=deleted_settings,
        deleted_memories=deleted_memories,
        deleted_plugin_folders=deleted_plugin_folders,
    )


@router.post("/agent_destroy", response_model=ResetResponse)
async def agent_destroy(
    request: Request,
    lizard: BillTheLizard = Depends(AdminConnectionAuth(AdminAuthResource.CHESHIRE_CATS, AuthPermission.DELETE)),
) -> ResetResponse:
    """
    Reset a single agent. This will delete all settings, memories, and metadata, for the agent.
    """

    agent_id = extract_agent_id_from_request(request)
    ccat = lizard.get_cheshire_cat(agent_id)
    if not ccat:
        return ResetResponse(deleted_settings=False, deleted_memories=False, deleted_plugin_folders=False)

    try:
        await ccat.destroy()
        await lizard.remove_cheshire_cat(agent_id)
        deleted_settings = True
        deleted_memories = True
    except Exception as e:
        log.error(f"Error deleting settings: {e}")
        deleted_settings = False
        deleted_memories = False

    return ResetResponse(
        deleted_settings=deleted_settings,
        deleted_memories=deleted_memories,
        deleted_plugin_folders=False,
    )


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
        return ResetResponse(deleted_settings=False, deleted_memories=False, deleted_plugin_folders=False)

    try:
        await ccat.destroy()
        await lizard.remove_cheshire_cat(agent_id)
        lizard.get_or_create_cheshire_cat(agent_id)
        deleted_settings = True
        deleted_memories = True
    except Exception as e:
        log.error(f"Error deleting settings: {e}")
        deleted_settings = False
        deleted_memories = False

    return ResetResponse(
        deleted_settings=deleted_settings,
        deleted_memories=deleted_memories,
        deleted_plugin_folders=False,
    )
