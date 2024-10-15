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


# We store users in a setting and when there will be a graph db in the cat, we will store them there.
# create admin user and an ordinary user
def create_basic_users(key_id: str, full_permissions: Dict, base_permissions: Dict | None = None) -> None:
    admin_id = str(uuid4())
    user_id = str(uuid4())

    basic_users = {
        admin_id: {
            "id": admin_id,
            "username": "admin",
            "password": hash_password("admin"),
            # admin has all permissions
            "permissions": full_permissions
        }
    }

    if base_permissions:
        basic_users[user_id] = {
            "id": user_id,
            "username": "user",
            "password": hash_password("user"),
            # user has minor permissions
            "permissions": base_permissions
        }

    update_users(key_id, basic_users)


def get_users(key_id: str) -> Dict[str, Dict]:
    users = get_setting_by_name(key_id, "users")
    return users["value"] if users else {}


def create_user(key_id: str, new_user: Dict) -> Dict | None:
    users_db = get_users(key_id)

    # check for user duplication with shameful loop
    for u in users_db.values():
        if u["username"] == new_user["username"]:
            return None

    # hash password
    new_user["password"] = hash_password(new_user["password"])

    # create user
    new_id = str(uuid4())
    users_db[new_id] = {"id": new_id, **new_user}
    update_users(key_id, users_db)

    return users_db[new_id]


def get_user(key_id, user_id: str) -> Dict | None:
    users_db = get_users(key_id)
    if user_id not in users_db:
        return None

    return users_db[user_id]


def get_user_by_username(key_id: str, username: str) -> Dict | None:
    users_db = get_users(key_id)
    for user in users_db.values():
        if user["username"] == username:
            return user

    return None


def update_user(key_id: str, user_id: str, updated_info: Dict) -> Dict:
    users_db = get_users(key_id)
    users_db[user_id] = updated_info

    return update_users(key_id, users_db)


def delete_user(key_id: str, user_id: str) -> Dict | None:
    users_db = get_users(key_id)

    if user_id not in users_db:
        return None

    user = users_db.pop(user_id)
    update_users(key_id, users_db)

    return user


def update_users(key_id, users: Dict[str, Dict]) -> Dict | None:
    updated_users = Setting(name="users", value=users)

    return upsert_setting_by_name(key_id, updated_users)


def get_all(key_id: str):
    return __get(key_id)


def get_user_by_credentials(key_id: str, username: str, password: str) -> Dict | None:
    """
    Get a user by their username and password. If the user is not found, return None.

    Args:
        key_id: the key to look for Redis
        username: the username of the user to look for
        password: the password of the user to look for

    Returns:
        The user if found, None otherwise. The user has the format:
        {
            "id": <id_0>,
            "username": "<username_0>",
            "password": "<hashed_password_0>",
            "permissions": <dict_of_permissions_0>
        }
    """

    users = get_users(key_id)
    for user in users.values():
        if user["username"] == username and check_password(password, user["password"]):
            return user

    return None
