from typing import Dict, List
from uuid import uuid4

from cat.auth.permissions import get_full_permissions, get_base_permissions
from cat.auth.auth_utils import hash_password
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


def upsert_setting_by_name(payload: Setting, *args, **kwargs) -> Setting:
    return get_db().upsert_setting_by_name(payload, *args, **kwargs)


# We store users in a setting and when there will be a graph db in the cat, we will store them there.
# P.S.: I'm not proud of this.
def get_users(*args, **kwargs) -> Dict[str, Dict]:
    users = get_setting_by_name("users", *args, **kwargs)
    if not users:
        # create admin user and an ordinary user
        admin_id = str(uuid4())
        user_id = str(uuid4())

        update_users({
            admin_id: {
                "id": admin_id,
                "username": "admin",
                "password": hash_password("admin"),
                # admin has all permissions
                "permissions": get_full_permissions()
            },
            user_id: {
                "id": user_id,
                "username": "user",
                "password": hash_password("user"),
                # user has minor permissions
                "permissions": get_base_permissions()
            }
        }, *args, **kwargs)
    return get_setting_by_name("users", *args, **kwargs)["value"]

def update_users(users: Dict[str, Dict], *args, **kwargs) -> Setting:
    updated_users = Setting(name="users", value=users)
    return upsert_setting_by_name(updated_users, *args, **kwargs)
