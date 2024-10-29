from typing import Dict
from fastapi import APIRouter, Body, Depends

from cat.auth.connection import AdminConnectionAuth
from cat.auth.permissions import AdminAuthResource, AuthPermission
from cat.bill_the_lizard import BillTheLizard
from cat.db.cruds import settings as crud_settings
from cat.exceptions import CustomValidationException
from cat.factory.base_factory import ReplacedNLPConfig
from cat.factory.plugin_uploader import PluginUploaderFactory
from cat.routes.routes_utils import GetSettingsResponse, GetSettingResponse, UpsertSettingResponse

router = APIRouter()


# get configured Embedders and configuration schemas
@router.get("/settings", response_model=GetSettingsResponse)
def get_plugin_uploader_settings(
    lizard: BillTheLizard = Depends(AdminConnectionAuth(AdminAuthResource.UPLOADER, AuthPermission.LIST)),
) -> GetSettingsResponse:
    """Get the list of the Plugin Uploaders"""

    factory = PluginUploaderFactory(lizard.march_hare)

    selected = crud_settings.get_setting_by_name(lizard.config_key, factory.setting_name)
    if selected is not None:
        selected = selected["value"]["name"]

    saved_settings = crud_settings.get_settings_by_category(lizard.config_key, factory.setting_factory_category)
    saved_settings = {s["name"]: s for s in saved_settings}

    settings = [GetSettingResponse(
        name=class_name,
        value=saved_settings[class_name]["value"] if class_name in saved_settings else {},
        scheme=scheme
    ) for class_name, scheme in factory.get_schemas().items()]

    return GetSettingsResponse(settings=settings, selected_configuration=selected)


@router.get("/settings/{plugin_uploader_name}", response_model=GetSettingResponse)
def get_plugin_uploader_settings(
    plugin_uploader_name: str,
    lizard: BillTheLizard = Depends(AdminConnectionAuth(AdminAuthResource.UPLOADER, AuthPermission.READ)),
) -> GetSettingResponse:
    """Get settings and scheme of the specified Plugin Uploader"""

    plugin_uploader_schemas = PluginUploaderFactory(lizard.march_hare).get_schemas()
    # check that plugin_uploader_name is a valid name
    allowed_configurations = list(plugin_uploader_schemas.keys())
    if plugin_uploader_name not in allowed_configurations:
        raise CustomValidationException(f"{plugin_uploader_name} not supported. Must be one of {allowed_configurations}")

    setting = crud_settings.get_setting_by_name(lizard.config_key, plugin_uploader_name)
    setting = {} if setting is None else setting["value"]

    scheme = plugin_uploader_schemas[plugin_uploader_name]

    return GetSettingResponse(name=plugin_uploader_name, value=setting, scheme=scheme)


@router.put("/settings/{plugin_uploader_name}", response_model=UpsertSettingResponse)
def upsert_plugin_uploader_setting(
    plugin_uploader_name: str,
    payload: Dict = Body(...),
    lizard: BillTheLizard = Depends(AdminConnectionAuth(AdminAuthResource.UPLOADER, AuthPermission.EDIT)),
) -> ReplacedNLPConfig:
    """Upsert the Plugin Uploader setting"""

    plugin_uploader_schemas = PluginUploaderFactory(lizard.march_hare).get_schemas()
    # check that plugin_uploader_name is a valid name
    allowed_configurations = list(plugin_uploader_schemas.keys())
    if plugin_uploader_name not in allowed_configurations:
        raise CustomValidationException(f"{plugin_uploader_name} not supported. Must be one of {allowed_configurations}")

    return lizard.replace_plugin_uploader(plugin_uploader_name, payload)
