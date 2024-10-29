from typing import Dict, List
from fastapi import Body, APIRouter, Depends
from pydantic import ValidationError, BaseModel

from cat.auth.connection import HTTPAuth, ContextualCats
from cat.auth.permissions import AuthPermission, AuthResource
from cat.exceptions import CustomValidationException, CustomNotFoundException
from cat.looking_glass.cheshire_cat import Plugins
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
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.PLUGINS, AuthPermission.LIST)),
    # author: str = None, to be activated in case of more granular search
    # tag: str = None, to be activated in case of more granular search
) -> GetAvailablePluginsResponse:
    """List available plugins"""

    plugins = await get_plugins(cats.cheshire_cat.mad_hatter, query)

    return GetAvailablePluginsResponse(
        filters={
            "query": query,
            # "author": author, to be activated in case of more granular search
            # "tag": tag, to be activated in case of more granular search
        },
        installed=plugins.installed,
        registry=plugins.registry,
    )


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
        raise CustomNotFoundException("Plugin not found")

    # toggle plugin
    ccat.mad_hatter.toggle_plugin(plugin_id)
    return TogglePluginResponse(info=f"Plugin {plugin_id} toggled")


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
            raise CustomValidationException(
                f"Error loading {plugin} settings. The result will not contain the settings for this plugin. "
                f"Error details: {e}"
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
        raise CustomNotFoundException("Plugin not found")

    settings = ccat.mad_hatter.plugins[plugin_id].load_settings()
    scheme = ccat.mad_hatter.plugins[plugin_id].settings_schema()

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
        raise CustomNotFoundException("Plugin not found")

    # Get the plugin object
    plugin = ccat.mad_hatter.plugins[plugin_id]

    try:
        # Load the plugin settings Pydantic model
        plugin_settings_model = plugin.settings_model()
        # Validate the settings
        plugin_settings_model.model_validate(payload)
    except ValidationError as e:
        raise CustomValidationException("\n".join(list(map(lambda x: x["msg"], e.errors()))))

    final_settings = plugin.save_settings(payload)

    return GetSettingResponse(name=plugin_id, value=final_settings)
