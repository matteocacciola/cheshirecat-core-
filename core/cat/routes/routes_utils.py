import asyncio
from copy import deepcopy
from typing import Dict, List, Any
from pydantic import BaseModel
from fastapi import Request

from cat.exceptions import CustomForbiddenException, CustomValidationException, CustomNotFoundException
from cat.factory.base_factory import ReplacedNLPConfig
from cat.mad_hatter.march_hare import MarchHare
from cat.mad_hatter.registry import registry_search_plugins


class Plugins(BaseModel):
    installed: List[Dict]
    registry: List[Dict]


class UserCredentials(BaseModel):
    username: str
    password: str


class JWTResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UpsertSettingResponse(ReplacedNLPConfig):
    pass


class GetSettingResponse(UpsertSettingResponse):
    scheme: Dict[str, Any] | None = None


class GetSettingsResponse(BaseModel):
    settings: List[GetSettingResponse]
    selected_configuration: str | None


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


async def auth_token(request: Request, credentials: UserCredentials, agent_id: str):
    """Endpoint called from client to get a JWT from local identity provider.
    This endpoint receives username and password as form-data, validates credentials and issues a JWT.
    """

    # use username and password to authenticate user from local identity provider and get token
    access_token = await request.app.state.lizard.core_auth_handler.issue_jwt(
        credentials.username, credentials.password, key_id=agent_id
    )

    if access_token:
        return JWTResponse(access_token=access_token)

    # Invalid username or password
    # wait a little to avoid brute force attacks
    await asyncio.sleep(1)
    raise CustomForbiddenException("Invalid Credentials")


async def get_plugins(march_hare: MarchHare, query: str = None) -> Plugins:
    """
    Get the plugins related to the passed MarchHare / MadHatter instance and the query.
    Args:
        march_hare: the instance of MarchHare / MadHatter
        query: the query to look for

    Returns:
        The list of plugins
    """
    # retrieve plugins from official repo
    registry_plugins = await registry_search_plugins(query)
    # index registry plugins by url
    registry_plugins_index = {p["url"]: p for p in registry_plugins}

    # get active plugins
    active_plugins = march_hare.load_active_plugins_from_db()

    # list installed plugins' manifest
    installed_plugins = []
    for p in march_hare.plugins.values():
        # get manifest
        manifest = deepcopy(p.manifest)  # we make a copy to avoid modifying the plugin obj
        manifest["active"] = (p.id in active_plugins)  # pass along if plugin is active or not
        manifest["upgrade"] = None
        manifest["hooks"] = [{"name": hook.name, "priority": hook.priority} for hook in p.hooks]
        manifest["tools"] = [{"name": tool.name} for tool in p.tools]

        # filter by query
        plugin_text = [str(field) for field in manifest.values()]
        plugin_text = " ".join(plugin_text).lower()
        if query is None or query.lower() in plugin_text:
            for r in registry_plugins:
                if r["plugin_url"] == p.manifest["plugin_url"] and r["version"] != p.manifest["version"]:
                    manifest["upgrade"] = r["version"]
            installed_plugins.append(manifest)

        # do not show already installed plugins among registry plugins
        registry_plugins_index.pop(manifest["plugin_url"], None)

    return Plugins(installed=installed_plugins, registry=list(registry_plugins_index.values()))


async def get_available_plugins(
    march_hare: MarchHare,
    query: str = None,
    # author: str = None, to be activated in case of more granular search
    # tag: str = None, to be activated in case of more granular search
) -> GetAvailablePluginsResponse:
    """List available plugins"""

    plugins = await get_plugins(march_hare, query)

    return GetAvailablePluginsResponse(
        filters={
            "query": query,
            # "author": author, to be activated in case of more granular search
            # "tag": tag, to be activated in case of more granular search
        },
        installed=plugins.installed,
        registry=plugins.registry,
    )

def get_plugins_settings(march_hare: MarchHare, agent_id: str) -> PluginsSettingsResponse:
    settings = []

    # plugins are managed by the MarchHare / MadHatter class
    for plugin in march_hare.plugins.values():
        try:
            plugin_settings = plugin.load_settings(agent_id)
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


def get_plugin_settings(march_hare: MarchHare, plugin_id: str, agent_id: str) -> GetSettingResponse:
    """Returns the settings of a specific plugin"""

    if not march_hare.plugin_exists(plugin_id):
        raise CustomNotFoundException("Plugin not found")

    settings = march_hare.plugins[plugin_id].load_settings(agent_id)
    scheme = march_hare.plugins[plugin_id].settings_schema()

    if scheme["properties"] == {}:
        scheme = {}

    return GetSettingResponse(name=plugin_id, value=settings, scheme=scheme)
