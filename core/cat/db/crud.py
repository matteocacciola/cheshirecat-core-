import json
from typing import Dict, List
from uuid import uuid4

from cat.auth.permissions import get_full_permissions, get_base_permissions
from cat.auth.auth_utils import hash_password
from cat.db.database import get_db
from cat.db.models import Setting

USERS_KEY = "users"


def __get(key: str) -> List | Dict | None:
    value = get_db().get(key)
    if not value:
        return None

    if isinstance(value, (bytes, str)):
        return json.loads(value)
    else:
        raise ValueError(f"Unexpected type for Redis value: {type(value)}")


def __set(key: str, value: List | Dict) -> List | Dict | None:
    new = get_db().set(key, json.dumps(value), get=True)
    if not new:
        return None

    if isinstance(new, (bytes, str)):
        return json.loads(new)
    else:
        raise ValueError(f"Unexpected type for Redis value: {type(new)}")


def get_settings(search: str = "", **kwargs) -> List[Dict]:
    chatbot_id: str = kwargs.get("chatbot_id")
    settings: List[Dict] = __get(chatbot_id)
    if not settings:
        return []

    settings = [setting for setting in settings if search in setting["name"]]

    # Workaround: do not expose users in the settings list
    settings = [s for s in settings if s["name"] != "users"]
    return settings


def get_settings_by_category(category: str, **kwargs) -> List[Dict]:
    chatbot_id: str = kwargs.get("chatbot_id")
    settings: List[Dict] = __get(chatbot_id)
    if not settings:
        return []

    return [setting for setting in settings if setting["category"] == category]


def create_setting(payload: Setting, **kwargs) -> Dict:
    chatbot_id: str = kwargs.get("chatbot_id")

    # create and retrieve the record we just created
    return __set(chatbot_id, [payload.model_dump()]) or {}


def get_setting_by_name(name: str, **kwargs) -> Dict | None:
    chatbot_id: str = kwargs.get("chatbot_id")
    settings: List[Dict] = __get(chatbot_id)
    if not settings:
        return None

    settings = [setting for setting in settings if setting["name"] == name]
    return settings[0] if settings else None


def get_setting_by_id(setting_id: str, **kwargs) -> Dict | None:
    chatbot_id: str = kwargs.get("chatbot_id")
    settings: List[Dict] = __get(chatbot_id)

    settings = [setting for setting in settings if setting["setting_id"] == setting_id]
    if not settings:
        return None

    return settings[0]


def delete_setting_by_id(setting_id: str, **kwargs) -> None:
    chatbot_id: str = kwargs.get("chatbot_id")
    settings: List[Dict] = __get(chatbot_id)

    if not settings:
        return

    settings = [setting for setting in settings if setting["setting_id"] != setting_id]
    __set(chatbot_id, settings)


def delete_settings_by_category(category: str, **kwargs) -> None:
    chatbot_id: str = kwargs.get("chatbot_id")
    settings: List[Dict] = __get(chatbot_id)

    if not settings:
        return

    settings = [setting for setting in settings if setting["category"] != category]
    __set(chatbot_id, settings)


def update_setting_by_id(payload: Setting, **kwargs) -> Dict | None:
    chatbot_id: str = kwargs.get("chatbot_id")
    settings: List[Dict] = __get(chatbot_id)

    if not settings:
        return None

    for setting in settings:
        if setting["setting_id"] == payload.setting_id:
            setting.update(payload.model_dump())

    __set(chatbot_id, settings)
    return get_setting_by_id(payload.setting_id)


def upsert_setting_by_name(payload: Setting, **kwargs) -> Dict:
    chatbot_id: str = kwargs.get("chatbot_id")
    old_setting = get_setting_by_name(payload.name, chatbot_id=chatbot_id)

    if not old_setting:
        create_setting(payload, chatbot_id=chatbot_id)
    else:
        settings: List[Dict] = __get(chatbot_id) or []
        for setting in settings:
            if setting["name"] == payload.name:
                setting.update(payload.model_dump())

        __set(chatbot_id, settings)

    return get_setting_by_name(payload.name, chatbot_id=chatbot_id)


def get_all_users() -> Dict[str, Dict]:
    """
    Get all users.
    Returns:
        A dictionary with the following format:
        {
            <id_0>: {
                "id": <id_0>,
                "username": "<username_0>",
                "password": "<hashed_password_0>",
                "permissions": <dict_of_permissions_0>
            },
            ...
        }
    """

    return __get(USERS_KEY)


# We store users in a setting and when there will be a graph db in the cat, we will store them there.
# P.S.: I'm not proud of this.
def get_users(**kwargs) -> Dict[str, Dict]:
    users = get_setting_by_name("users", **kwargs)
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
        })
    return get_setting_by_name("users", **kwargs)["value"]


def create_user(new_user: Dict, **kwargs) -> Dict | None:
    chatbot_id: str = kwargs.get("chatbot_id")
    users_db = get_users(chatbot_id=chatbot_id)

    # check for user duplication with shameful loop
    for u in users_db.values():
        if u["username"] == new_user["username"]:
            return None

    # hash password
    new_user["password"] = hash_password(new_user["password"])

    # create user
    new_id = str(uuid4())
    users_db[new_id] = {"id": new_id, **new_user}
    update_users(users_db, chatbot_id=chatbot_id)

    return users_db[new_id]


def get_user(user_id: str, **kwargs) -> Dict | None:
    chatbot_id: str = kwargs.get("chatbot_id")

    users_db = get_users(chatbot_id=chatbot_id)
    if user_id not in users_db:
        return None

    return users_db[user_id]


def update_user(user_id: str, updated_info: Dict, **kwargs) -> Dict:
    chatbot_id: str = kwargs.get("chatbot_id")
    users_db = get_users(chatbot_id=chatbot_id)

    users_db[user_id] = updated_info

    return update_users(users_db, **kwargs)


def delete_user(user_id: str, **kwargs) -> Dict | None:
    chatbot_id: str = kwargs.get("chatbot_id")
    users_db = get_users(chatbot_id=chatbot_id)

    if user_id not in users_db:
        raise None

    user = users_db.pop(user_id)
    update_users(users_db, **kwargs)

    return user


def update_users(users: Dict[str, Dict], **kwargs) -> Dict | None:
    updated_users = Setting(name="users", value=users)

    # add or update the set from USERS_KEY with the new users
    all_users = {**get_all_users(), **users}
    __set(USERS_KEY, all_users)

    return upsert_setting_by_name(updated_users, **kwargs)
