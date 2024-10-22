from typing import Dict
from uuid import uuid4

from cat.auth.auth_utils import hash_password, check_password
from cat.db import crud
from cat.db.cruds import settings as crud_settings
from cat.db.models import Setting


# We store users in a setting and when there will be a graph db in the cat, we will store them there.
# create admin user
def get_users(key_id: str, with_password: bool = False) -> Dict[str, Dict]:
    users = crud_settings.get_setting_by_name(key_id, "users")
    if not users:
        return {}

    if with_password:
        return users["value"]

    users = {uid: {k: v for k, v in u.items() if k != "password"} for uid, u in users["value"].items()}
    return users


def create_user(key_id: str, new_user: Dict) -> Dict | None:
    # check for user duplication
    user = get_user_by_username(key_id, new_user["username"], with_password=True)
    if user:
        return None

    new_id = str(uuid4())
    new_user_copy = new_user.copy()
    new_user_copy["id"] = new_id

    # hash password
    password = hash_password(new_user_copy["password"])
    del new_user_copy["password"]

    # create user
    users_db = get_users(key_id, with_password=True)
    users_db[new_id] = {"password": password, **new_user_copy}

    update_users(key_id, users_db)

    return new_user_copy


def get_user(key_id, user_id: str) -> Dict | None:
    path = f'$[?(@.name=="users")].value.{user_id}'
    result = crud.read(crud_settings.format_key(key_id), path)
    if not result:
        return None

    return {k: v for k, v in result[0].items() if k != "password"}


def get_user_by_username(key_id: str, username: str, with_password: bool = False) -> Dict | None:
    path = f'$[?(@.name=="users")].value[?(@.username=="{username}")]'
    result = crud.read(crud_settings.format_key(key_id), path)
    if not result:
        return None

    if with_password:
        return result[0]

    return {k: v for k, v in result[0].items() if k != "password"}


def update_user(key_id: str, user_id: str, updated_info: Dict) -> Dict:
    users_db = get_users(key_id, with_password=True)
    users_db[user_id] = updated_info

    update_users(key_id, users_db)

    return {k: v for k, v in updated_info.items() if k != "password"}


def delete_user(key_id: str, user_id: str) -> Dict | None:
    users_db = get_users(key_id, with_password=True)
    if user_id not in users_db.keys():
        return None

    user = users_db.pop(user_id)
    update_users(key_id, users_db)

    return user


def update_users(key_id, users: Dict[str, Dict]) -> Dict | None:
    updated_users = Setting(name="users", value=users)

    return crud_settings.upsert_setting_by_name(key_id, updated_users)


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

    user = get_user_by_username(key_id, username, with_password=True)
    if not user:
        return None

    if check_password(password, user["password"]):
        return user

    return None
