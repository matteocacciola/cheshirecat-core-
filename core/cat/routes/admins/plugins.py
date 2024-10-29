import aiofiles
import mimetypes
from copy import deepcopy
from typing import Dict, List
from fastapi import Body, APIRouter, UploadFile, Depends
from pydantic import BaseModel

from cat.auth.connection import AdminConnectionAuth
from cat.auth.permissions import AuthPermission, AdminAuthResource
from cat.bill_the_lizard import BillTheLizard
from cat.exceptions import CustomValidationException, CustomNotFoundException
from cat.log import log
from cat.looking_glass.cheshire_cat import Plugins
from cat.mad_hatter.registry import registry_download_plugin
from cat.routes.routes_utils import GetSettingResponse, get_plugins

router = APIRouter()


class GetAvailablePluginsFilter(BaseModel):
    query: str | None


class GetAvailablePluginsResponse(Plugins):
    filters: GetAvailablePluginsFilter


class TogglePluginResponse(BaseModel):
    info: str


class InstallPluginResponse(TogglePluginResponse):
    filename: str
    content_type: str


class InstallPluginFromRegistryResponse(TogglePluginResponse):
    url: str


class PluginsSettingsResponse(BaseModel):
    settings: List[GetSettingResponse]


class GetPluginDetailsResponse(BaseModel):
    data: Dict


class DeletePluginResponse(BaseModel):
    deleted: str


# GET plugins
@router.get("/", response_model=GetAvailablePluginsResponse)
async def get_available_plugins(
    query: str = None,
    lizard: BillTheLizard = Depends(AdminConnectionAuth(AdminAuthResource.PLUGINS, AuthPermission.LIST)),
    # author: str = None, to be activated in case of more granular search
    # tag: str = None, to be activated in case of more granular search
) -> GetAvailablePluginsResponse:
    """List available plugins"""

    plugins = await get_plugins(lizard.march_hare, query)

    return GetAvailablePluginsResponse(
        filters={
            "query": query,
            # "author": author, to be activated in case of more granular search
            # "tag": tag, to be activated in case of more granular search
        },
        installed=plugins.installed,
        registry=plugins.registry,
    )


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
    lizard.march_hare.install_plugin(plugin_archive_path)

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
        lizard.march_hare.install_plugin(tmp_plugin_path)
    except Exception as e:
        raise CustomValidationException(f"Could not download plugin form registry: {e}")

    return InstallPluginFromRegistryResponse(url=payload["url"], info="Plugin is being installed asynchronously")


@router.get("/settings", response_model=PluginsSettingsResponse)
async def get_plugins_settings(
    lizard: BillTheLizard = Depends(AdminConnectionAuth(AdminAuthResource.PLUGINS, AuthPermission.READ)),
) -> PluginsSettingsResponse:
    """Returns the default settings of all the plugins"""

    settings = []

    # plugins are managed by the MadHatter class
    for plugin in lizard.march_hare.plugins.values():
        try:
            plugin_settings = plugin.load_settings()
            plugin_schema = plugin.settings_schema()
            if plugin_schema["properties"] == {}:
                plugin_schema = {}
            settings.append(
                GetSettingResponse(name=plugin.id, value=plugin_settings, scheme=plugin_schema)
            )
        except Exception as e:
            raise CustomValidationException(
                f"Error loading {plugin} settings. The result will not contain the settings for this plugin. "
                f"Error details: {e}"
            )

    return PluginsSettingsResponse(settings=settings)


@router.get("/settings/{plugin_id}", response_model=GetSettingResponse)
async def get_plugin_settings(
    plugin_id: str,
    lizard: BillTheLizard = Depends(AdminConnectionAuth(AdminAuthResource.PLUGINS, AuthPermission.READ)),
) -> GetSettingResponse:
    """Returns the default settings of a specific plugin"""

    if not lizard.march_hare.plugin_exists(plugin_id):
        raise CustomNotFoundException("Plugin not found")

    settings = lizard.march_hare.plugins[plugin_id].load_settings()
    scheme = lizard.march_hare.plugins[plugin_id].settings_schema()

    if scheme["properties"] == {}:
        scheme = {}

    return GetSettingResponse(name=plugin_id, value=settings, scheme=scheme)


@router.get("/{plugin_id}", response_model=GetPluginDetailsResponse)
async def get_plugin_details(
    plugin_id: str,
    lizard: BillTheLizard = Depends(AdminConnectionAuth(AdminAuthResource.PLUGINS, AuthPermission.READ)),
) -> GetPluginDetailsResponse:
    """Returns information on a single plugin, at a system level"""

    if not lizard.march_hare.plugin_exists(plugin_id):
        raise CustomNotFoundException("Plugin not found")

    active_plugins = lizard.march_hare.load_active_plugins_from_db()

    plugin = lizard.march_hare.plugins[plugin_id]

    # get manifest and active True/False. We make a copy to avoid modifying the original obj
    plugin_info = deepcopy(plugin.manifest)
    plugin_info["active"] = plugin_id in active_plugins
    plugin_info["hooks"] = [
        {"name": hook.name, "priority": hook.priority} for hook in plugin.hooks
    ]
    plugin_info["tools"] = [{"name": tool.name} for tool in plugin.tools]

    return GetPluginDetailsResponse(data=plugin_info)


@router.delete("/{plugin_id}", response_model=DeletePluginResponse)
async def delete_plugin(
    plugin_id: str,
    lizard: BillTheLizard = Depends(AdminConnectionAuth(AdminAuthResource.PLUGINS, AuthPermission.DELETE)),
) -> DeletePluginResponse:
    """Physically remove plugin at a system level."""

    if not lizard.march_hare.plugin_exists(plugin_id):
        raise CustomNotFoundException("Plugin not found")

    # remove folder, hooks and tools
    lizard.march_hare.uninstall_plugin(plugin_id)

    return DeletePluginResponse(deleted=plugin_id)