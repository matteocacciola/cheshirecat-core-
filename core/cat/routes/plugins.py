from typing import Dict
from fastapi import Body, APIRouter, Depends
from pydantic import ValidationError

from cat.auth.connection import HTTPAuth, ContextualCats
from cat.auth.permissions import AuthPermission, AuthResource
from cat.exceptions import CustomValidationException, CustomNotFoundException
from cat.routes.routes_utils import (
    GetAvailablePluginsResponse,
    GetSettingResponse,
    PluginsSettingsResponse,
    TogglePluginResponse,
    get_available_plugins,
    get_plugins_settings,
    get_plugin_settings,
)

router = APIRouter()


# GET plugins
@router.get("/", response_model=GetAvailablePluginsResponse)
async def get_cheshirecat_available_plugins(
    query: str = None,
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.PLUGINS, AuthPermission.LIST)),
    # author: str = None, to be activated in case of more granular search
    # tag: str = None, to be activated in case of more granular search
) -> GetAvailablePluginsResponse:
    """List available plugins"""

    return await get_available_plugins(cats.cheshire_cat.plugin_manager, query)


@router.put("/toggle/{plugin_id}", status_code=200, response_model=TogglePluginResponse)
async def toggle_plugin(
    plugin_id: str,
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.PLUGINS, AuthPermission.WRITE)),
) -> TogglePluginResponse:
    """Enable or disable a single plugin"""

    # access cat instance
    ccat = cats.cheshire_cat

    # check if plugin exists
    if not ccat.plugin_manager.plugin_exists(plugin_id):
        raise CustomNotFoundException("Plugin not found")

    # toggle plugin
    ccat.plugin_manager.toggle_plugin(plugin_id)
    return TogglePluginResponse(info=f"Plugin {plugin_id} toggled")


@router.get("/settings", response_model=PluginsSettingsResponse)
async def get_cheshirecat_plugins_settings(
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.PLUGINS, AuthPermission.READ)),
) -> PluginsSettingsResponse:
    """Returns the settings of all the plugins"""

    return get_plugins_settings(cats.cheshire_cat.plugin_manager, cats.cheshire_cat.id)


@router.get("/settings/{plugin_id}", response_model=GetSettingResponse)
async def get_cheshirecat_plugin_settings(
    plugin_id: str,
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.PLUGINS, AuthPermission.READ)),
) -> GetSettingResponse:
    """Returns the settings of a specific plugin"""

    return get_plugin_settings(cats.cheshire_cat.plugin_manager, plugin_id, cats.cheshire_cat.id)


@router.put("/settings/{plugin_id}", response_model=GetSettingResponse)
async def upsert_cheshirecat_plugin_settings(
    plugin_id: str,
    payload: Dict = Body({"setting_a": "some value", "setting_b": "another value"}),
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.PLUGINS, AuthPermission.EDIT)),
) -> GetSettingResponse:
    """Updates the settings of a specific plugin"""

    # access cat instance
    ccat = cats.cheshire_cat

    if not ccat.plugin_manager.plugin_exists(plugin_id):
        raise CustomNotFoundException("Plugin not found")

    # Get the plugin object
    plugin = ccat.plugin_manager.plugins[plugin_id]

    try:
        # Load the plugin settings Pydantic model, and validate the settings
        plugin.settings_model().model_validate(payload)
    except ValidationError as e:
        raise CustomValidationException("\n".join(list(map(lambda x: x["msg"], e.errors()))))

    final_settings = plugin.save_settings(payload, ccat.id)

    return GetSettingResponse(name=plugin_id, value=final_settings)
