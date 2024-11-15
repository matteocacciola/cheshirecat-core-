from typing import Dict, List

from cat.db import crud, models
from cat.db.database import DEFAULT_AGENT_KEY, DEFAULT_SYSTEM_KEY


def format_key(key: str) -> str:
    return f"{key}:{DEFAULT_AGENT_KEY}"


def get_settings(key_id: str, search: str = "") -> List[Dict]:
    path = f'$[?(@.name =~ ".*{search}.*")]' if search else "$"

    settings: List[Dict] = crud.read(format_key(key_id), path)
    if not settings:
        return []

    # Workaround: do not expose users in the settings list
    settings = [s for s in settings if s["name"] != "users"]
    return settings


def get_settings_by_category(key_id: str, category: str) -> List[Dict]:
    if not category:
        return []

    settings: List[Dict] = crud.read(format_key(key_id), path=f'$[?(@.category=="{category}")]')
    if not settings:
        return []

    return settings


def create_setting(key_id: str, payload: models.Setting) -> Dict:
    fkey_id = format_key(key_id)
    value = payload.model_dump()

    existing_settings = crud.read(fkey_id) or []
    existing_settings.append(value)

    crud.store(fkey_id, existing_settings)
    return value


def get_setting_by_name(key_id: str, name: str) -> Dict | None:
    settings: List[Dict] = crud.read(format_key(key_id), path=f'$[?(@.name=="{name}")]')
    if not settings:
        return None

    return settings[0]


def get_setting_by_id(key_id: str, setting_id: str) -> Dict | None:
    settings: List[Dict] = crud.read(format_key(key_id), path=f'$[?(@.setting_id=="{setting_id}")]')
    if not settings:
        return None

    return settings[0]


def delete_setting_by_id(key_id: str, setting_id: str) -> None:
    fkey_id = format_key(key_id)
    crud.delete(fkey_id, path=f'$[?(@.setting_id=="{setting_id}")]')


def delete_settings_by_category(key_id: str, category: str) -> None:
    fkey_id = format_key(key_id)
    crud.delete(fkey_id, path=f'$[?(@.category=="{category}")]')


def update_setting_by_id(key_id: str, payload: models.Setting) -> Dict | None:
    fkey_id = format_key(key_id)

    setting = get_setting_by_id(key_id, payload.setting_id)
    if not setting:
        return create_setting(key_id, payload)

    value = payload.model_dump()
    crud.store(fkey_id, value, path=f'$[?(@.setting_id=="{payload.setting_id}")]')
    return value


def upsert_setting_by_name(key_id: str, payload: models.Setting) -> Dict:
    value = payload.model_dump()

    old_setting = get_setting_by_name(key_id, payload.name)
    if not old_setting:
        create_setting(key_id, payload)
    else:
        fkey_id = format_key(key_id)
        crud.store(fkey_id, value, path=f'$[?(@.name=="{payload.name}")]')

    return value


def upsert_setting_by_category(key_id: str, payload: models.Setting) -> Dict:
    value = payload.model_dump()

    old_setting = get_settings_by_category(key_id, payload.category)
    if not old_setting:
        create_setting(key_id, payload)
    else:
        fkey_id = format_key(key_id)
        crud.store(fkey_id, value, path=f'$[?(@.category=="{payload.category}")]')

    return value


def destroy_all(key_id: str) -> None:
    crud.destroy(format_key(key_id))
