import aiofiles
import mimetypes
from copy import deepcopy
from typing import Dict
from fastapi import Body, APIRouter, UploadFile, Depends

from cat.auth.connection import AdminConnectionAuth
from cat.auth.permissions import AuthPermission, AdminAuthResource
from cat.bill_the_lizard import BillTheLizard
from cat.exceptions import CustomValidationException, CustomNotFoundException
from cat.log import log
from cat.mad_hatter.registry import registry_download_plugin
from cat.routes.routes_utils import (
    DeletePluginResponse,
    GetAvailablePluginsResponse,
    GetPluginDetailsResponse,
    GetSettingResponse,
    InstallPluginFromRegistryResponse,
    InstallPluginResponse,
    PluginsSettingsResponse,
    get_available_plugins,
    get_plugins_settings,
    get_plugin_settings,
)

router = APIRouter()


# GET plugins
@router.get("/", response_model=GetAvailablePluginsResponse)
async def get_lizard_available_plugins(
    query: str = None,
    lizard: BillTheLizard = Depends(AdminConnectionAuth(AdminAuthResource.PLUGINS, AuthPermission.LIST)),
    # author: str = None, to be activated in case of more granular search
    # tag: str = None, to be activated in case of more granular search
) -> GetAvailablePluginsResponse:
    """List available plugins"""

    return await get_available_plugins(lizard.plugin_manager, query)


@router.post("/upload", response_model=InstallPluginResponse)
async def install_plugin(
    file: UploadFile,
    lizard: BillTheLizard = Depends(AdminConnectionAuth(AdminAuthResource.PLUGINS, AuthPermission.WRITE)),
) -> InstallPluginResponse:
    """Install a new plugin from a zip file"""

    admitted_mime_types = ["application/zip", "application/x-tar"]
    content_type = mimetypes.guess_type(file.filename)[0]
    if content_type not in admitted_mime_types:
        raise CustomValidationException(
            f'MIME type `{file.content_type}` not supported. Admitted types: {", ".join(admitted_mime_types)}'
        )

    log.info(f"Uploading {content_type} plugin {file.filename}")
    plugin_archive_path = f"/tmp/{file.filename}"
    async with aiofiles.open(plugin_archive_path, "wb+") as f:
        content = await file.read()
        await f.write(content)
    lizard.plugin_manager.install_plugin(plugin_archive_path)

    return InstallPluginResponse(
        filename=file.filename,
        content_type=file.content_type,
        info="Plugin is being installed asynchronously",
    )


@router.post("/upload/registry", response_model=InstallPluginFromRegistryResponse)
async def install_plugin_from_registry(
    payload: Dict = Body({"url": "https://github.com/plugin-dev-account/plugin-repo"}),
    lizard: BillTheLizard = Depends(AdminConnectionAuth(AdminAuthResource.PLUGINS, AuthPermission.WRITE)),
) -> InstallPluginFromRegistryResponse:
    """Install a new plugin from registry"""

    # download zip from registry
    try:
        tmp_plugin_path = await registry_download_plugin(payload["url"])
        lizard.plugin_manager.install_plugin(tmp_plugin_path)
    except Exception as e:
        raise CustomValidationException(f"Could not download plugin from registry: {e}")

    return InstallPluginFromRegistryResponse(url=payload["url"], info="Plugin is being installed asynchronously")


@router.get("/settings", response_model=PluginsSettingsResponse)
async def get_lizard_plugins_settings(
    lizard: BillTheLizard = Depends(AdminConnectionAuth(AdminAuthResource.PLUGINS, AuthPermission.READ)),
) -> PluginsSettingsResponse:
    """Returns the default settings of all the plugins"""

    return get_plugins_settings(lizard.plugin_manager, lizard.config_key)


@router.get("/settings/{plugin_id}", response_model=GetSettingResponse)
async def get_lizard_plugin_settings(
    plugin_id: str,
    lizard: BillTheLizard = Depends(AdminConnectionAuth(AdminAuthResource.PLUGINS, AuthPermission.READ)),
) -> GetSettingResponse:
    """Returns the default settings of a specific plugin"""

    return get_plugin_settings(lizard.plugin_manager, plugin_id, lizard.config_key)


@router.get("/{plugin_id}", response_model=GetPluginDetailsResponse)
async def get_plugin_details(
    plugin_id: str,
    lizard: BillTheLizard = Depends(AdminConnectionAuth(AdminAuthResource.PLUGINS, AuthPermission.READ)),
) -> GetPluginDetailsResponse:
    """Returns information on a single plugin, at a system level"""

    if not lizard.plugin_manager.plugin_exists(plugin_id):
        raise CustomNotFoundException("Plugin not found")

    active_plugins = lizard.plugin_manager.load_active_plugins_from_db()

    plugin = lizard.plugin_manager.plugins[plugin_id]

    # get manifest and active True/False. We make a copy to avoid modifying the original obj
    plugin_info = deepcopy(plugin.manifest)
    plugin_info["active"] = plugin_id in active_plugins
    plugin_info["hooks"] = [
        {"name": hook.name, "priority": hook.priority} for hook in plugin.hooks
    ]
    plugin_info["tools"] = [{"name": tool.name} for tool in plugin.tools]

    return GetPluginDetailsResponse(data=plugin_info)


@router.delete("/{plugin_id}", response_model=DeletePluginResponse)
async def uninstall_plugin(
    plugin_id: str,
    lizard: BillTheLizard = Depends(AdminConnectionAuth(AdminAuthResource.PLUGINS, AuthPermission.DELETE)),
) -> DeletePluginResponse:
    """Physically remove plugin at a system level."""

    if not lizard.plugin_manager.plugin_exists(plugin_id):
        raise CustomNotFoundException("Plugin not found")

    # remove folder, hooks and tools
    lizard.plugin_manager.uninstall_plugin(plugin_id)

    return DeletePluginResponse(deleted=plugin_id)
