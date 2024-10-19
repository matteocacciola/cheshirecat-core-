import mimetypes
from copy import deepcopy
from typing import Dict, List
from fastapi import Body, APIRouter, HTTPException, UploadFile, Depends
from pydantic import ValidationError, BaseModel

from cat.auth.connection import HTTPAuth, ContextualCats
from cat.auth.permissions import AuthPermission, AuthResource
from cat.log import log
from cat.looking_glass.cheshire_cat import Plugins
from cat.mad_hatter.registry import registry_download_plugin
from cat.routes.routes_utils import GetSettingResponse

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
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.PLUGINS, AuthPermission.LIST)),
    # author: str = None, to be activated in case of more granular search
    # tag: str = None, to be activated in case of more granular search
) -> GetAvailablePluginsResponse:
    """List available plugins"""

    plugins = await cats.cheshire_cat.get_plugins(query)

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
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.PLUGINS, AuthPermission.WRITE)),
) -> InstallPluginResponse:
    """Install a new plugin from a zip file"""

    # access cat instance
    ccat = cats.cheshire_cat

    admitted_mime_types = ["application/zip", "application/x-tar"]
    content_type = mimetypes.guess_type(file.filename)[0]
    if content_type not in admitted_mime_types:
        raise HTTPException(
            status_code=400,
            detail={
                "error": f'MIME type `{file.content_type}` not supported. Admitted types: {", ".join(admitted_mime_types)}'
            },
        )

    log.info(f"Uploading {content_type} plugin {file.filename}")
    plugin_archive_path = f"/tmp/{file.filename}"
    with open(plugin_archive_path, "wb+") as f:
        f.write(file.file.read())
    ccat.mad_hatter.install_plugin(plugin_archive_path)

    return InstallPluginResponse(
        filename=file.filename,
        content_type=file.content_type,
        info="Plugin is being installed asynchronously",
    )


@router.post("/upload/registry", response_model=InstallPluginFromRegistryResponse)
async def install_plugin_from_registry(
    payload: Dict = Body({"url": "https://github.com/plugin-dev-account/plugin-repo"}),
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.PLUGINS, AuthPermission.WRITE)),
) -> InstallPluginFromRegistryResponse:
    """Install a new plugin from registry"""

    # access cat instance
    ccat = cats.cheshire_cat

    # download zip from registry
    try:
        tmp_plugin_path = registry_download_plugin(payload["url"])
        ccat.mad_hatter.install_plugin(tmp_plugin_path)
    except Exception as e:
        log.error("Could not download plugin form registry")
        log.error(e)
        raise HTTPException(status_code=500, detail={"error": str(e)})

    return InstallPluginFromRegistryResponse(url=payload["url"], info="Plugin is being installed asynchronously")


@router.put("/toggle/{plugin_id}", status_code=200, response_model=TogglePluginResponse)
async def toggle_plugin(
    plugin_id: str,
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.PLUGINS, AuthPermission.WRITE)),
) -> TogglePluginResponse:
    """Enable or disable a single plugin"""

    # access cat instance
    ccat = cats.cheshire_cat

    # check if plugin exists
    if not ccat.mad_hatter.plugin_exists(plugin_id):
        raise HTTPException(status_code=404, detail={"error": "Plugin not found"})

    try:
        # toggle plugin
        ccat.mad_hatter.toggle_plugin(plugin_id)
        return TogglePluginResponse(info=f"Plugin {plugin_id} toggled")
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.get("/settings", response_model=PluginsSettingsResponse)
async def get_plugins_settings(
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.PLUGINS, AuthPermission.READ)),
) -> PluginsSettingsResponse:
    """Returns the settings of all the plugins"""

    # access cat instance
    ccat = cats.cheshire_cat

    settings = []

    # plugins are managed by the MadHatter class
    for plugin in ccat.mad_hatter.plugins.values():
        try:
            plugin_settings = plugin.load_settings()
            plugin_schema = plugin.settings_schema()
            if plugin_schema["properties"] == {}:
                plugin_schema = {}
            settings.append(
                GetSettingResponse(name=plugin.id, value=plugin_settings, scheme=plugin_schema)
            )
        except Exception as e:
            log.error(
                f"Error loading {plugin} settings. The result will not contain the settings for this plugin. Error details: {e}"
            )

    return PluginsSettingsResponse(settings=settings)


@router.get("/settings/{plugin_id}", response_model=GetSettingResponse)
async def get_plugin_settings(
    plugin_id: str,
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.PLUGINS, AuthPermission.READ)),
) -> GetSettingResponse:
    """Returns the settings of a specific plugin"""

    # access cat instance
    ccat = cats.cheshire_cat

    if not ccat.mad_hatter.plugin_exists(plugin_id):
        raise HTTPException(status_code=404, detail={"error": "Plugin not found"})

    try:
        settings = ccat.mad_hatter.plugins[plugin_id].load_settings()
        scheme = ccat.mad_hatter.plugins[plugin_id].settings_schema()
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": e})

    if scheme["properties"] == {}:
        scheme = {}

    return GetSettingResponse(name=plugin_id, value=settings, scheme=scheme)


@router.put("/settings/{plugin_id}", response_model=GetSettingResponse)
async def upsert_plugin_settings(
    plugin_id: str,
    payload: Dict = Body({"setting_a": "some value", "setting_b": "another value"}),
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.PLUGINS, AuthPermission.EDIT)),
) -> GetSettingResponse:
    """Updates the settings of a specific plugin"""

    # access cat instance
    ccat = cats.cheshire_cat

    if not ccat.mad_hatter.plugin_exists(plugin_id):
        raise HTTPException(status_code=404, detail={"error": "Plugin not found"})

    # Get the plugin object
    plugin = ccat.mad_hatter.plugins[plugin_id]

    try:
        # Load the plugin settings Pydantic model
        plugin_settings_model = plugin.settings_model()
        # Validate the settings
        plugin_settings_model.model_validate(payload)
    except ValidationError as e:
        raise HTTPException(
            status_code=400,
            detail={"error": "\n".join(list(map((lambda x: x["msg"]), e.errors())))},
        )

    final_settings = plugin.save_settings(payload)

    return GetSettingResponse(name=plugin_id, value=final_settings)


@router.get("/{plugin_id}", response_model=GetPluginDetailsResponse)
async def get_plugin_details(
    plugin_id: str,
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.PLUGINS, AuthPermission.READ)),
) -> GetPluginDetailsResponse:
    """Returns information on a single plugin"""

    # access cat instance
    ccat = cats.cheshire_cat

    if not ccat.mad_hatter.plugin_exists(plugin_id):
        raise HTTPException(status_code=404, detail={"error": "Plugin not found"})

    active_plugins = ccat.mad_hatter.load_active_plugins_from_db()

    plugin = ccat.mad_hatter.plugins[plugin_id]

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
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.PLUGINS, AuthPermission.DELETE)),
) -> DeletePluginResponse:
    """Physically remove plugin."""

    # access cat instance
    ccat = cats.cheshire_cat

    if not ccat.mad_hatter.plugin_exists(plugin_id):
        raise HTTPException(status_code=404, detail={"error": "Item not found"})

    # remove folder, hooks and tools
    ccat.mad_hatter.uninstall_plugin(plugin_id)

    return DeletePluginResponse(deleted=plugin_id)
