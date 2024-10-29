import asyncio
from copy import deepcopy
from typing import Dict, List, Any
from pydantic import BaseModel
from fastapi import Request

from cat.exceptions import CustomForbiddenException
from cat.factory.base_factory import ReplacedNLPConfig
from cat.looking_glass.cheshire_cat import Plugins
from cat.mad_hatter.march_hare import MarchHare
from cat.mad_hatter.registry import registry_search_plugins


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
