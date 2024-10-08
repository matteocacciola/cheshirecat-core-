from typing import Dict
from fastapi import APIRouter, Body, HTTPException, Depends

from cat.auth.connection import HTTPAuth, ContextualCats
from cat.auth.permissions import AuthPermission, AuthResource
from cat.db import crud, models
from cat.factory.auth_handler import get_auth_handlers_schemas

router = APIRouter()

AUTH_HANDLER_SELECTED_NAME = "auth_handler_selected"
AUTH_HANDLER_CATEGORY = "auth_handler_factory"


@router.get("/settings")
def get_auth_handler_settings(
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.AUTH_HANDLER, AuthPermission.LIST))
) -> Dict:
    """Get the list of the AuthHandlers"""

    chatbot_id = cats.cheshire_cat.id

    # get selected AuthHandler
    selected = crud.get_setting_by_name(name=AUTH_HANDLER_SELECTED_NAME, chatbot_id=chatbot_id)
    if selected is not None:
        selected = selected["value"]["name"]

    saved_settings = crud.get_settings_by_category(category=AUTH_HANDLER_CATEGORY, chatbot_id=chatbot_id)
    saved_settings = {s["name"]: s for s in saved_settings}

    settings = []
    for class_name, schema in get_auth_handlers_schemas(chatbot_id).items():
        if class_name in saved_settings:
            saved_setting = saved_settings[class_name]["value"]
        else:
            saved_setting = {}

        settings.append(
            {
                "name": class_name,
                "value": saved_setting,
                "schema": schema,
            }
        )

    return {
        "settings": settings,
        "selected_configuration": selected,
    }


@router.get("/settings/{auth_handler_name}")
def get_auth_handler_setting(
    auth_handler_name: str,
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.AUTH_HANDLER, AuthPermission.LIST))
) -> Dict:
    """Get the settings of a specific AuthHandler"""

    chatbot_id = cats.cheshire_cat.id

    auth_handler_schemas = get_auth_handlers_schemas(chatbot_id)

    allowed_configurations = list(auth_handler_schemas.keys())
    if auth_handler_name not in allowed_configurations:
        raise HTTPException(
            status_code=400,
            detail={
                "error": f"{auth_handler_name} not supported. Must be one of {allowed_configurations}"
            },
        )

    setting = crud.get_setting_by_name(name=auth_handler_name, chatbot_id=chatbot_id)
    schema = auth_handler_schemas[auth_handler_name]

    setting = {} if setting is None else setting["value"]

    return {"name": auth_handler_name, "value": setting, "schema": schema}


@router.put("/settings/{auth_handler_name}")
def upsert_authenticator_setting(
    auth_handler_name: str,
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.AUTH_HANDLER, AuthPermission.LIST)),
    payload: Dict = Body(...),
) -> Dict:
    """Upsert the settings of a specific AuthHandler"""

    ccat = cats.cheshire_cat
    chatbot_id = ccat.id

    auth_handler_schemas = get_auth_handlers_schemas(chatbot_id)

    allowed_configurations = list(auth_handler_schemas.keys())
    if auth_handler_name not in allowed_configurations:
        raise HTTPException(
            status_code=400,
            detail={
                "error": f"{auth_handler_name} not supported. Must be one of {allowed_configurations}"
            },
        )

    crud.upsert_setting_by_name(
        models.Setting(
            name=auth_handler_name, value=payload, category=AUTH_HANDLER_CATEGORY
        ),
        chatbot_id=chatbot_id,
    )

    crud.upsert_setting_by_name(
        models.Setting(
            name=AUTH_HANDLER_SELECTED_NAME,
            value={"name": auth_handler_name},
            category=AUTH_HANDLER_CATEGORY,
        ),
        chatbot_id=chatbot_id,
    )

    ccat.load_auth()

    return {
        "name": auth_handler_name,
        "value": payload,
    }
