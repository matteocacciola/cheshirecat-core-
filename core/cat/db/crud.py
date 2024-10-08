from typing import Dict, List

from cat.db.models import Setting
from cat.factory.crud_source import get_db


def get_settings(search: str = "", *args, **kwargs) -> List[Dict]:
    settings = get_db().get_settings(search, *args, **kwargs)
    # Workaround: do not expose users in the settings list
    settings = [s for s in settings if s["name"] != "users"]
    return settings


def get_settings_by_category(category: str, *args, **kwargs) -> List[Dict]:
    return get_db().get_settings_by_category(category, *args, **kwargs)


def create_setting(payload: Setting, *args, **kwargs) -> Dict:
    # Missing fields (setting_id, updated_at) are filled automatically by pydantic
    return get_db().create_setting(payload, *args, **kwargs)


def get_setting_by_name(name: str, *args, **kwargs) -> Dict | None:
    return get_db().get_setting_by_name(name, *args, **kwargs)


def get_setting_by_id(setting_id: str, *args, **kwargs) -> Dict | None:
    return get_db().get_setting_by_name(setting_id, *args, **kwargs)


def delete_setting_by_id(setting_id: str, *args, **kwargs) -> None:
    get_db().delete_setting_by_id(setting_id, *args, **kwargs)


def delete_settings_by_category(category: str, *args, **kwargs) -> None:
    get_db().delete_settings_by_category(category, *args, **kwargs)


def update_setting_by_id(payload: Setting, *args, **kwargs) -> Dict:
    return get_db().update_setting_by_id(payload, *args, **kwargs)


def upsert_setting_by_name(payload: Setting, *args, **kwargs) -> Dict:
    return get_db().upsert_setting_by_name(payload, *args, **kwargs)


def get_all_users() -> Dict[str, Dict]:
    return get_db().get_all_users()


# We store users in a setting and when there will be a graph db in the cat, we will store them there.
# P.S.: I'm not proud of this.
def get_users(*args, **kwargs) -> Dict[str, Dict]:
    return get_db().get_users(*args, **kwargs)


def update_users(users: Dict[str, Dict], *args, **kwargs) -> Dict | None:
    return get_db().update_users(users, *args, **kwargs)
