from typing import Dict, Any

from cat.db import crud


def format_key(agent_id: str, plugin_id: str) -> str:
    return f"{agent_id}:plugin:{plugin_id}"


def get_setting(agent_id: str, plugin_id: str) -> Dict[str, Any]:
    settings = crud.read(format_key(agent_id, plugin_id))

    if isinstance(settings, list):
        settings = settings[0]

    return settings if settings else {}


def set_setting(agent_id: str, plugin_id: str, settings: Dict[str, Any]) -> Dict[str, Any]:
    crud.store(format_key(agent_id, plugin_id), settings)
    return settings


def update_setting(agent_id: str, plugin_id: str, updated_settings: Dict) -> Dict[str, Any]:
    settings_db = get_setting(agent_id, plugin_id)
    settings_db.update(updated_settings)

    return set_setting(agent_id, plugin_id, settings_db)


def delete_setting(agent_id: str, plugin_id: str) -> None:
    crud.delete(format_key(agent_id, plugin_id))


def destroy_all(agent_id: str) -> None:
    crud.delete(format_key(agent_id, "*"))


def destroy_plugin(plugin_id: str) -> None:
    crud.delete(format_key("*", plugin_id))
