from typing import Dict
from fastapi import APIRouter, Body, Depends

from cat.auth.connection import AdminConnectionAuth
from cat.auth.permissions import AdminAuthResource, AuthPermission
from cat.db.cruds import settings as crud_settings
from cat.exceptions import CustomValidationException
from cat.factory.base_factory import ReplacedNLPConfig
from cat.factory.file_manager import FileManagerFactory
from cat.looking_glass.bill_the_lizard import BillTheLizard
from cat.routes.routes_utils import GetSettingsResponse, GetSettingResponse, UpsertSettingResponse

router = APIRouter()


# get configured Plugin File Managers and configuration schemas
@router.get("/settings", response_model=GetSettingsResponse)
async def get_file_managers_settings(
    lizard: BillTheLizard = Depends(AdminConnectionAuth(AdminAuthResource.FILE_MANAGER, AuthPermission.LIST)),
) -> GetSettingsResponse:
    """Get the list of the Plugin File Managers and their settings"""

    factory = FileManagerFactory(lizard.plugin_manager)

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


@router.get("/settings/{file_manager_name}", response_model=GetSettingResponse)
async def get_file_manager_settings(
    file_manager_name: str,
    lizard: BillTheLizard = Depends(AdminConnectionAuth(AdminAuthResource.FILE_MANAGER, AuthPermission.READ)),
) -> GetSettingResponse:
    """Get settings and scheme of the specified Plugin File Manager"""

    plugin_filemanager_schemas = FileManagerFactory(lizard.plugin_manager).get_schemas()
    # check that plugin_filemanager_name is a valid name
    allowed_configurations = list(plugin_filemanager_schemas.keys())
    if file_manager_name not in allowed_configurations:
        raise CustomValidationException(
            f"{file_manager_name} not supported. Must be one of {allowed_configurations}"
        )

    setting = crud_settings.get_setting_by_name(lizard.config_key, file_manager_name)
    setting = {} if setting is None else setting["value"]

    scheme = plugin_filemanager_schemas[file_manager_name]

    return GetSettingResponse(name=file_manager_name, value=setting, scheme=scheme)


@router.put("/settings/{file_manager_name}", response_model=UpsertSettingResponse)
async def upsert_file_manager_setting(
    file_manager_name: str,
    payload: Dict = Body(...),
    lizard: BillTheLizard = Depends(AdminConnectionAuth(AdminAuthResource.FILE_MANAGER, AuthPermission.EDIT)),
) -> ReplacedNLPConfig:
    """Upsert the Plugin File Manager setting"""

    plugin_filemanager_schemas = FileManagerFactory(lizard.plugin_manager).get_schemas()
    # check that plugin_filemanager_name is a valid name
    allowed_configurations = list(plugin_filemanager_schemas.keys())
    if file_manager_name not in allowed_configurations:
        raise CustomValidationException(
            f"{file_manager_name} not supported. Must be one of {allowed_configurations}"
        )

    return lizard.replace_file_manager(file_manager_name, payload)
