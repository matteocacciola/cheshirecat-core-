from fastapi import Depends, APIRouter, HTTPException

from cat.auth.permissions import AuthPermission, AuthResource
from cat.auth.connection import HTTPAuth, ContextualCats
from cat.db import models
from cat.db import crud

router = APIRouter()


@router.get("/")
def get_settings(
    search: str = "",
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.SETTINGS, AuthPermission.LIST)),
):
    """Get the entire list of settings available in the database"""

    settings = crud.get_settings(search=search, chatbot_id=cats.cheshire_cat.id)

    return {"settings": settings}


@router.post("/")
def create_setting(
    payload: models.SettingBody,
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.SETTINGS, AuthPermission.WRITE)),
):
    """Create a new setting in the database"""

    # complete the payload with setting_id and updated_at
    payload = models.Setting(**payload.model_dump())

    # save to DB
    new_setting = crud.create_setting(payload, chatbot_id=cats.cheshire_cat.id)

    return {"setting": new_setting}


@router.get("/{settingId}")
def get_setting(
    settingId: str,
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.SETTINGS, AuthPermission.READ))
):
    """Get the specific setting from the database"""

    setting = crud.get_setting_by_id(settingId, chatbot_id=cats.cheshire_cat.id)
    if not setting:
        raise HTTPException(
            status_code=404,
            detail={
                "error": f"No setting with this id: {settingId}",
            },
        )
    return {"setting": setting}


@router.put("/{settingId}")
def update_setting(
    settingId: str,
    payload: models.SettingBody,
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.SETTINGS, AuthPermission.EDIT)),
):
    """Update a specific setting in the database if it exists"""

    chatbot_id = cats.cheshire_cat.id

    # does the setting exist?
    setting = crud.get_setting_by_id(settingId, chatbot_id=chatbot_id)
    if not setting:
        raise HTTPException(
            status_code=404,
            detail={
                "error": f"No setting with this id: {settingId}",
            },
        )

    # complete the payload with setting_id and updated_at
    payload = models.Setting(**payload.model_dump())
    payload.setting_id = settingId  # force this to be the setting_id

    # save to DB
    updated_setting = crud.update_setting_by_id(payload, chatbot_id=chatbot_id)

    return {"setting": updated_setting}


@router.delete("/{settingId}")
def delete_setting(
    settingId: str,
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.SETTINGS, AuthPermission.DELETE)),
):
    """Delete a specific setting in the database"""

    chatbot_id = cats.cheshire_cat.id

    # does the setting exist?
    setting = crud.get_setting_by_id(settingId, chatbot_id=chatbot_id)
    if not setting:
        raise HTTPException(
            status_code=404,
            detail={
                "error": f"No setting with this id: {settingId}",
            },
        )

    # delete
    crud.delete_setting_by_id(settingId, chatbot_id=chatbot_id)

    return {"deleted": settingId}
