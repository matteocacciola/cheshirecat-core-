from typing import Dict
from fastapi import Request, APIRouter, HTTPException, Depends, Body

from cat.auth.connection import HTTPAuth
from cat.auth.permissions import AuthPermission, AuthResource
from cat.db.crud_source import get_crud_settings, upsert_setting_by_name
from cat.db.models import CrudSetting
from cat.factory.crud_source import get_crud_sources_schemas
from cat.looking_glass.stray_cat import StrayCat

router = APIRouter()


# get configured Crud Sources and configuration schemas
@router.get("/settings")
def get_crud_sources_settings(stray: StrayCat = Depends(HTTPAuth(AuthResource.LLM, AuthPermission.LIST))) -> Dict:
    """Get the list of the Crud Sources"""
    CRUDSOURCE_SCHEMAS = get_crud_sources_schemas()

    # get selected crud source, if any
    saved_settings = get_crud_settings()

    settings = [{"name": class_name, "schema": schema} for class_name, schema in CRUDSOURCE_SCHEMAS.items()]

    return {
        "settings": settings,
        "selected_configuration": saved_settings,
    }


# get LLM settings and its schema
@router.get("/settings/{crudSourceName}")
def get_crud_source_settings(
    request: Request,
    crudSourceName: str,
    stray: StrayCat = Depends(HTTPAuth(AuthResource.LLM, AuthPermission.LIST))
) -> Dict:
    """Get settings and schema of the specified Crud Source"""
    CRUDSOURCE_SCHEMAS = get_crud_sources_schemas()

    # check that languageModelName is a valid name
    allowed_configurations = list(CRUDSOURCE_SCHEMAS.keys())
    if crudSourceName not in allowed_configurations:
        raise HTTPException(
            status_code=400,
            detail={
                "error": f"{crudSourceName} not supported. Must be one of {allowed_configurations}"
            },
        )

    setting = get_crud_settings()

    return {
        "name": crudSourceName,
        "value": setting.value if setting is not None and setting.name == crudSourceName else {},
        "schema": CRUDSOURCE_SCHEMAS[crudSourceName]
    }


@router.put("/settings/{crudSourceName}")
def upsert_crud_source_settings(
    request: Request,
    crudSourceName: str,
    payload: Dict = Body(...),
    stray: StrayCat = Depends(HTTPAuth(AuthResource.LLM, AuthPermission.EDIT)),
) -> Dict:
    """Upsert the Crud Source setting"""
    CRUDSOURCE_SCHEMAS = get_crud_sources_schemas()

    # check that crudSourceName is a valid name
    allowed_configurations = list(CRUDSOURCE_SCHEMAS.keys())
    if crudSourceName not in allowed_configurations:
        raise HTTPException(
            status_code=400,
            detail={
                "error": f"{crudSourceName} not supported. Must be one of {allowed_configurations}"
            },
        )

    # create the setting and upsert it
    final_setting = upsert_setting_by_name(CrudSetting(name=crudSourceName, value=payload))

    return {"name": crudSourceName, "value": final_setting["value"]}

