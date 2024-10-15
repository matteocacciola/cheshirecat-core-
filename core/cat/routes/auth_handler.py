from typing import Dict
from fastapi import APIRouter, Body, HTTPException, Depends

from cat.auth.connection import HTTPAuth, ContextualCats
from cat.auth.permissions import AuthPermission, AuthResource
from cat.db import models
from cat.db.cruds import settings as crud_settings
from cat.factory.auth_handler import get_auth_handlers_schemas

router = APIRouter()


@router.get("/settings")
def get_auth_handler_settings(
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.AUTH_HANDLER, AuthPermission.LIST))
) -> Dict:
    """Get the list of the AuthHandlers"""

    agent_id = cats.cheshire_cat.id

    # get selected AuthHandler
    selected = crud_settings.get_setting_by_name(agent_id, "auth_handler_selected")
    if selected is not None:
        selected = selected["value"]["name"]

    saved_settings = crud_settings.get_settings_by_category(agent_id, "auth_handler_factory")
    saved_settings = {s["name"]: s for s in saved_settings}

    settings = [{
        "name": class_name,
        "value": saved_settings[class_name]["value"] if class_name in saved_settings else {},
        "schema": schema,
    } for class_name, schema in get_auth_handlers_schemas(cats.cheshire_cat.mad_hatter).items()]

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

    auth_handler_schemas = get_auth_handlers_schemas(cats.cheshire_cat.mad_hatter)

    allowed_configurations = list(auth_handler_schemas.keys())
    if auth_handler_name not in allowed_configurations:
        raise HTTPException(
            status_code=400,
            detail={
                "error": f"{auth_handler_name} not supported. Must be one of {allowed_configurations}"
            },
        )

    setting = crud_settings.get_setting_by_name(cats.cheshire_cat.id, auth_handler_name)
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
    agent_id = ccat.id

    auth_handler_schemas = get_auth_handlers_schemas(ccat.mad_hatter)

    allowed_configurations = list(auth_handler_schemas.keys())
    if auth_handler_name not in allowed_configurations:
        raise HTTPException(
            status_code=400,
            detail={
                "error": f"{auth_handler_name} not supported. Must be one of {allowed_configurations}"
            },
        )

    crud_settings.upsert_setting_by_name(
        agent_id,
        models.Setting(
            name=auth_handler_name, value=payload, category="auth_handler_factory"
        ),
    )

    crud_settings.upsert_setting_by_name(
        agent_id,
        models.Setting(
            name="auth_handler_selected",
            value={"name": auth_handler_name},
            category="auth_handler_factory",
        ),
    )

    ccat.load_auth()

    return {
        "name": auth_handler_name,
        "value": payload,
    }
