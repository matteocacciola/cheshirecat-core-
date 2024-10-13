from typing import Dict
from fastapi import APIRouter, Body, HTTPException, Depends

from cat.auth.connection import ConnectionSuperAdminAuth
from cat.auth.permissions import AuthPermission, AuthResource
from cat.bill_the_lizard import BillTheLizard
from cat.db import crud
from cat.exceptions import LoadMemoryException
from cat.factory.embedder import get_embedders_schemas

router = APIRouter()


# get configured Embedders and configuration schemas
@router.get("/settings")
def get_embedders_settings(
    lizard: BillTheLizard = Depends(ConnectionSuperAdminAuth(AuthResource.EMBEDDER, AuthPermission.LIST)),
) -> Dict:
    """Get the list of the Embedders"""

    # embedder type and config are saved in settings table under "embedder_factory" category
    saved_settings = crud.get_settings_by_category(lizard.config_key, "embedder_factory")
    saved_settings = {s["name"]: s for s in saved_settings}

    settings = [{
        "name": class_name,
        "value": saved_settings[class_name]["value"] if class_name in saved_settings else {},
        "schema": schema,
    } for class_name, schema in get_embedders_schemas(lizard.mad_hatter).items()]

    return {
        "settings": settings,
        "selected_configuration": lizard.get_selected_embedder_settings(),
    }


# get Embedder settings and its schema
@router.get("/settings/{language_embedder_name}")
def get_embedder_settings(
    language_embedder_name: str,
    lizard: BillTheLizard = Depends(ConnectionSuperAdminAuth(AuthResource.EMBEDDER, AuthPermission.READ)),
) -> Dict:
    """Get settings and schema of the specified Embedder"""

    embedder_schemas = get_embedders_schemas(lizard.mad_hatter)
    # check that language_embedder_name is a valid name
    allowed_configurations = list(embedder_schemas.keys())
    if language_embedder_name not in allowed_configurations:
        raise HTTPException(
            status_code=400,
            detail={
                "error": f"{language_embedder_name} not supported. Must be one of {allowed_configurations}"
            },
        )

    setting = crud.get_setting_by_name(lizard.config_key, language_embedder_name)
    schema = embedder_schemas[language_embedder_name]

    setting = {} if setting is None else setting["value"]

    return {"name": language_embedder_name, "value": setting, "schema": schema}


@router.put("/settings/{language_embedder_name}")
def upsert_embedder_setting(
    language_embedder_name: str,
    payload: Dict = Body({"openai_api_key": "your-key-here"}),
    lizard: BillTheLizard = Depends(ConnectionSuperAdminAuth(AuthResource.EMBEDDER, AuthPermission.EDIT)),
) -> Dict:
    """Upsert the Embedder setting"""

    embedder_schemas = get_embedders_schemas(lizard.mad_hatter)
    # check that language_embedder_name is a valid name
    allowed_configurations = list(embedder_schemas.keys())
    if language_embedder_name not in allowed_configurations:
        raise HTTPException(
            status_code=400,
            detail={
                "error": f"{language_embedder_name} not supported. Must be one of {allowed_configurations}"
            },
        )

    try:
        status = lizard.replace_embedder(language_embedder_name, payload)
    except LoadMemoryException as e:
        raise HTTPException(
            status_code=400, detail={"error": str(e)}
        )

    return status
