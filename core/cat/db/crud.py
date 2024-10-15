import json
from typing import Dict, List
from uuid import uuid4

from cat.auth.auth_utils import hash_password, check_password
from cat.db.database import get_db
from cat.db.models import Setting
from cat.utils import DefaultAgentKeys


def __format_key(key: str) -> str:
    if key == str(DefaultAgentKeys.SYSTEM):
        return key

    return f"{DefaultAgentKeys.AGENT}:{key}"


def __get(key: str) -> List | Dict | None:
    key = __format_key(key)
    value = get_db().get(key)
    if not value:
        return None

    if isinstance(value, (bytes, str)):
        return json.loads(value)
    else:
        raise ValueError(f"Unexpected type for Redis value: {type(value)}")


def __set(key: str, value: List | Dict) -> List | Dict | None:
    key = __format_key(key)
    new = get_db().set(key, json.dumps(value), get=True)
    if not new:
        return None

    if isinstance(new, (bytes, str)):
        return json.loads(new)
    else:
        raise ValueError(f"Unexpected type for Redis value: {type(new)}")


def __del(key: str) -> None:
    key = __format_key(key)
    get_db().delete(key)


def get_settings(key_id: str, search: str = "") -> List[Dict]:
    settings: List[Dict] = __get(key_id)
    if not settings:
        return []

    settings = [setting for setting in settings if search in setting["name"]]

    # Workaround: do not expose users in the settings list
    settings = [s for s in settings if s["name"] != "users"]
    return settings


def get_settings_by_category(key_id: str, category: str) -> List[Dict]:
    settings: List[Dict] = __get(key_id)
    if not settings:
        return []

    return [setting for setting in settings if setting["category"] == category]


def create_setting(key_id: str, payload: Setting) -> Dict:
    settings: List[Dict] = __get(key_id) or []
    settings.append(payload.model_dump())

    # create and retrieve the record we just created
    return __set(key_id, settings)


def get_setting_by_name(key_id: str, name: str) -> Dict | None:
    settings: List[Dict] = __get(key_id)
    if not settings:
        return None

    settings = [setting for setting in settings if setting["name"] == name]
    return settings[0] if settings else None


def get_setting_by_id(key_id: str, setting_id: str) -> Dict | None:
    settings: List[Dict] = __get(key_id)

    settings = [setting for setting in settings if setting["setting_id"] == setting_id]
    if not settings:
        return None

    return settings[0]


def delete_setting_by_id(key_id: str, setting_id: str) -> None:
    settings: List[Dict] = __get(key_id)

    if not settings:
        return

    settings = [setting for setting in settings if setting["setting_id"] != setting_id]
    __set(key_id, settings)


def delete_settings_by_category(key_id: str, category: str) -> None:
    settings: List[Dict] = __get(key_id)

    if not settings:
        return

    settings = [setting for setting in settings if setting["category"] != category]
    __set(key_id, settings)


def update_setting_by_id(key_id: str, payload: Setting) -> Dict | None:
    settings: List[Dict] = __get(key_id)

    if not settings:
        return None

    for setting in settings:
        if setting["setting_id"] == payload.setting_id:
            setting.update(payload.model_dump())

    __set(key_id, settings)
    return get_setting_by_id(key_id, payload.setting_id)


def upsert_setting_by_name(key_id: str, payload: Setting) -> Dict:
    old_setting = get_setting_by_name(key_id, payload.name)

    if not old_setting:
        create_setting(key_id, payload)
    else:
        settings: List[Dict] = __get(key_id) or []
        for setting in settings:
            if setting["name"] == payload.name:
                setting.update(payload.model_dump())

        __set(key_id, settings)

    return get_setting_by_name(key_id, payload.name)
