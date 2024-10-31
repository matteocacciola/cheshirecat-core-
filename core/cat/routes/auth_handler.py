from typing import Dict
from fastapi import APIRouter, Body, Depends

from cat.auth.connection import HTTPAuth, ContextualCats
from cat.auth.permissions import AuthPermission, AuthResource
from cat.db.cruds import settings as crud_settings
from cat.exceptions import CustomValidationException
from cat.factory.auth_handler import AuthHandlerFactory
from cat.factory.base_factory import ReplacedNLPConfig
from cat.routes.routes_utils import GetSettingsResponse, GetSettingResponse, UpsertSettingResponse

router = APIRouter()


@router.get("/settings", response_model=GetSettingsResponse)
def get_auth_handler_settings(
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.AUTH_HANDLER, AuthPermission.LIST))
) -> GetSettingsResponse:
    """Get the list of the AuthHandlers"""

    ccat = cats.cheshire_cat
    factory = AuthHandlerFactory(ccat.plugin_manager)

    # get selected AuthHandler
    selected = crud_settings.get_setting_by_name(ccat.id, factory.setting_name)
    if selected is not None:
        selected = selected["value"]["name"]

    saved_settings = crud_settings.get_settings_by_category(ccat.id, factory.setting_factory_category)
    saved_settings = {s["name"]: s for s in saved_settings}

    settings = [GetSettingResponse(
        name=class_name,
        value=saved_settings[class_name]["value"] if class_name in saved_settings else {},
        scheme=scheme
    ) for class_name, scheme in factory.get_schemas().items()]

    return GetSettingsResponse(settings=settings, selected_configuration=selected)


@router.get("/settings/{auth_handler_name}", response_model=GetSettingResponse)
def get_auth_handler_setting(
    auth_handler_name: str,
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.AUTH_HANDLER, AuthPermission.LIST))
) -> GetSettingResponse:
    """Get the settings of a specific AuthHandler"""

    auth_handler_schemas = AuthHandlerFactory(cats.cheshire_cat.plugin_manager).get_schemas()

    allowed_configurations = list(auth_handler_schemas.keys())
    if auth_handler_name not in allowed_configurations:
        raise CustomValidationException(f"{auth_handler_name} not supported. Must be one of {allowed_configurations}")

    setting = crud_settings.get_setting_by_name(cats.cheshire_cat.id, auth_handler_name)
    setting = {} if setting is None else setting["value"]

    scheme = auth_handler_schemas[auth_handler_name]

    return GetSettingResponse(name=auth_handler_name, value=setting, scheme=scheme)


@router.put("/settings/{auth_handler_name}", response_model=UpsertSettingResponse)
def upsert_authenticator_setting(
    auth_handler_name: str,
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.AUTH_HANDLER, AuthPermission.LIST)),
    payload: Dict = Body(...),
) -> ReplacedNLPConfig:
    """Upsert the settings of a specific AuthHandler"""

    ccat = cats.cheshire_cat
    auth_handler_schemas = AuthHandlerFactory(ccat.plugin_manager).get_schemas()

    allowed_configurations = list(auth_handler_schemas.keys())
    if auth_handler_name not in allowed_configurations:
        raise CustomValidationException(f"{auth_handler_name} not supported. Must be one of {allowed_configurations}")

    return ccat.replace_auth_handler(auth_handler_name, payload)
