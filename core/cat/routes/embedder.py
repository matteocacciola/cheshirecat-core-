from typing import Dict
from fastapi import APIRouter, Body, HTTPException, Depends

from cat.auth.connection import AdminConnectionAuth
from cat.auth.permissions import AdminAuthResource, AuthPermission
from cat.bill_the_lizard import BillTheLizard
from cat.db.cruds import settings as crud_settings
from cat.exceptions import LoadMemoryException
from cat.factory.embedder import get_embedders_schemas
from cat.routes.routes_utils import GetSettingsResponse, GetSettingResponse, UpsertSettingResponse

router = APIRouter()


# get configured Embedders and configuration schemas
@router.get("/settings", response_model=GetSettingsResponse)
def get_embedders_settings(
    lizard: BillTheLizard = Depends(AdminConnectionAuth(AdminAuthResource.EMBEDDER, AuthPermission.LIST)),
) -> GetSettingsResponse:
    """Get the list of the Embedders"""

    # embedder type and config are saved in settings table under "embedder_factory" category
    saved_settings = crud_settings.get_settings_by_category(lizard.config_key, "embedder_factory")
    saved_settings = {s["name"]: s for s in saved_settings}

    settings = [GetSettingResponse(
        name=class_name,
        value=saved_settings[class_name]["value"] if class_name in saved_settings else {},
        scheme=scheme
    ) for class_name, scheme in get_embedders_schemas(lizard.mad_hatter).items()]

    return GetSettingsResponse(
        settings=settings, selected_configuration=lizard.get_selected_embedder_settings()
    )


# get Embedder settings and its scheme
@router.get("/settings/{language_embedder_name}", response_model=GetSettingResponse)
def get_embedder_settings(
    language_embedder_name: str,
    lizard: BillTheLizard = Depends(AdminConnectionAuth(AdminAuthResource.EMBEDDER, AuthPermission.READ)),
) -> GetSettingResponse:
    """Get settings and scheme of the specified Embedder"""

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

    setting = crud_settings.get_setting_by_name(lizard.config_key, language_embedder_name)
    scheme = embedder_schemas[language_embedder_name]

    setting = {} if setting is None else setting["value"]

    return GetSettingResponse(name=language_embedder_name, value=setting, scheme=scheme)


@router.put("/settings/{language_embedder_name}", response_model=UpsertSettingResponse)
def upsert_embedder_setting(
    language_embedder_name: str,
    payload: Dict = Body({"openai_api_key": "your-key-here"}),
    lizard: BillTheLizard = Depends(AdminConnectionAuth(AdminAuthResource.EMBEDDER, AuthPermission.EDIT)),
) -> UpsertSettingResponse:
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
