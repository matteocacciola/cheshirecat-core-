from typing import Dict, List

from cat.db import crud, models


def get_settings(key_id: str, search: str = "") -> List[Dict]:
    settings: List[Dict] = crud.read(key_id)
    if not settings:
        return []

    settings = [setting for setting in settings if search in setting["name"]]

    # Workaround: do not expose users in the settings list
    settings = [s for s in settings if s["name"] != "users"]
    return settings


def get_settings_by_category(key_id: str, category: str) -> List[Dict]:
    settings: List[Dict] = crud.read(key_id)
    if not settings:
        return []

    return [setting for setting in settings if setting["category"] == category]


def create_setting(key_id: str, payload: models.Setting) -> Dict:
    settings: List[Dict] = crud.read(key_id) or []
    settings.append(payload.model_dump())

    # create and retrieve the record we just created
    return crud.store(key_id, settings)


def get_setting_by_name(key_id: str, name: str) -> Dict | None:
    settings: List[Dict] = crud.read(key_id)
    if not settings:
        return None

    settings = [setting for setting in settings if setting["name"] == name]
    return settings[0] if settings else None


def get_setting_by_id(key_id: str, setting_id: str) -> Dict | None:
    settings: List[Dict] = crud.read(key_id)

    settings = [setting for setting in settings if setting["setting_id"] == setting_id]
    if not settings:
        return None

    return settings[0]


def delete_setting_by_id(key_id: str, setting_id: str) -> None:
    settings: List[Dict] = crud.read(key_id)

    if not settings:
        return

    settings = [setting for setting in settings if setting["setting_id"] != setting_id]
    crud.store(key_id, settings)


def delete_settings_by_category(key_id: str, category: str) -> None:
    settings: List[Dict] = crud.read(key_id)

    if not settings:
        return

    settings = [setting for setting in settings if setting["category"] != category]
    crud.store(key_id, settings)


def update_setting_by_id(key_id: str, payload: models.Setting) -> Dict | None:
    settings: List[Dict] = crud.read(key_id)

    if not settings:
        return None

    for setting in settings:
        if setting["setting_id"] == payload.setting_id:
            setting.update(payload.model_dump())

    crud.store(key_id, settings)
    return get_setting_by_id(key_id, payload.setting_id)


def upsert_setting_by_name(key_id: str, payload: models.Setting) -> Dict:
    old_setting = get_setting_by_name(key_id, payload.name)

    if not old_setting:
        create_setting(key_id, payload)
    else:
        settings: List[Dict] = crud.read(key_id) or []
        for setting in settings:
            if setting["name"] == payload.name:
                setting.update(payload.model_dump())

        crud.store(key_id, settings)

    return get_setting_by_name(key_id, payload.name)
