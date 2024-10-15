from typing import Dict
from uuid import uuid4

from cat.auth.auth_utils import hash_password, check_password
from cat.db.cruds import settings as crud_settings
from cat.db.models import Setting


# We store users in a setting and when there will be a graph db in the cat, we will store them there.
# create admin user
def get_users(key_id: str) -> Dict[str, Dict]:
    users = crud_settings.get_setting_by_name(key_id, "users")
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

    users = get_users(key_id)
    for user in users.values():
        if user["username"] == username and check_password(password, user["password"]):
            return user

    return None
