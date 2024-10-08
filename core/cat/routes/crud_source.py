from typing import Dict
from fastapi import APIRouter, HTTPException, Depends, Body

from cat.auth.connection import HTTPAuth
from cat.auth.permissions import AuthPermission, AuthResource
from cat.db.crud_source import get_crud_settings, upsert_setting_by_name
from cat.db.models import CrudSetting
from cat.factory.crud_source import get_crud_sources_schemas

router = APIRouter()


# get configured Crud Sources and configuration schemas
@router.get("/settings", dependencies=[Depends(HTTPAuth(AuthResource.CRUD, AuthPermission.LIST))])
def get_crud_sources_settings() -> Dict:
    """Get the list of the Crud Sources"""
    crudsource_schemas = get_crud_sources_schemas()

    # get selected crud source, if any
    saved_settings = get_crud_settings()

    settings = [{"name": class_name, "schema": schema} for class_name, schema in crudsource_schemas.items()]

    return {
        "settings": settings,
        "selected_configuration": saved_settings,
    }


# get LLM settings and its schema
@router.get("/settings/{crud_source_name}", dependencies=[Depends(HTTPAuth(AuthResource.CRUD, AuthPermission.LIST))])
def get_crud_source_settings(crud_source_name: str) -> Dict:
    """Get settings and schema of the specified Crud Source"""
    crudsource_schemas = get_crud_sources_schemas()

    # check that languageModelName is a valid name
    allowed_configurations = list(crudsource_schemas.keys())
    if crud_source_name not in allowed_configurations:
        raise HTTPException(
            status_code=400,
            detail={
                "error": f"{crud_source_name} not supported. Must be one of {allowed_configurations}"
            },
        )

    setting = get_crud_settings()

    return {
        "name": crud_source_name,
        "value": setting.value if setting is not None and setting.name == crud_source_name else {},
        "schema": crudsource_schemas[crud_source_name]
    }


@router.put("/settings/{crud_source_name}", dependencies=[Depends(HTTPAuth(AuthResource.CRUD, AuthPermission.EDIT))])
def upsert_crud_source_settings(crud_source_name: str, payload: Dict = Body(...)) -> Dict:
    """Upsert the Crud Source setting"""
    crudsource_schemas = get_crud_sources_schemas()

    # check that crudSourceName is a valid name
    allowed_configurations = list(crudsource_schemas.keys())
    if crud_source_name not in allowed_configurations:
        raise HTTPException(
            status_code=400,
            detail={
                "error": f"{crud_source_name} not supported. Must be one of {allowed_configurations}"
            },
        )

    # create the setting and upsert it
    final_setting = upsert_setting_by_name(CrudSetting(name=crud_source_name, value=payload))

    return {"name": crud_source_name, "value": final_setting["value"]}

