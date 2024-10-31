import time
from typing import Dict
from uuid import uuid4

from cat.auth.auth_utils import hash_password, check_password
from cat.db import crud


def format_key(agent_id: str) -> str:
    return f"{agent_id}:users"


# We store users in a setting and when there will be a graph db in the cat, we will store them there.
# create admin user
def get_users(key_id: str, with_password: bool = False, with_timestamps: bool = False) -> Dict[str, Dict]:
    users = crud.read(format_key(key_id))
    if isinstance(users, list):
        users = users[0]

    if not users:
        return {}

    excluded_keys = []
    if not with_timestamps:
        excluded_keys = ["created_at", "updated_at"]

    if not with_password:
        excluded_keys.append("password")

    users = {uid: {k: v for k, v in u.items() if k not in excluded_keys} for uid, u in users.items()}
    return users


def create_user(key_id: str, new_user: Dict) -> Dict | None:
    # check for user duplication
    user = get_user_by_username(key_id, new_user["username"], with_password=True)
    if user:
        return None

    new_id = str(uuid4())
    new_user_copy = new_user.copy()
    new_user_copy["id"] = new_id
    new_user_copy["created_at"] = time.time()
    new_user_copy["updated_at"] = new_user_copy["created_at"]

    # hash password
    password = hash_password(new_user_copy["password"])
    del new_user_copy["password"]

    # create user
    users_db = get_users(key_id, with_password=True, with_timestamps=True)
    users_db[new_id] = {"password": password, **new_user_copy}

    set_users(key_id, users_db)

    return new_user_copy


def get_user(key_id, user_id: str) -> Dict | None:
    path = f'$.[?(@.id=="{user_id}")]'
    result = crud.read(format_key(key_id), path)
    if not result:
        return None

    return {k: v for k, v in result[0].items() if k not in ["created_at", "updated_at", "password"]}


def get_user_by_username(key_id: str, username: str, with_password: bool = False) -> Dict | None:
    path = f'$.[?(@.username=="{username}")]'
    result = crud.read(format_key(key_id), path)
    if not result:
        return None

    if with_password:
        return result[0]

    return {k: v for k, v in result[0].items() if k not in ["created_at", "updated_at", "password"]}


def update_user(key_id: str, user_id: str, updated_info: Dict) -> Dict:
    users_db = get_users(key_id, with_password=True)
    users_db[user_id] = updated_info
    users_db[user_id]["updated_at"] = time.time()

    set_users(key_id, users_db)

    return {k: v for k, v in updated_info.items() if k not in ["created_at", "updated_at", "password"]}


def delete_user(key_id: str, user_id: str) -> Dict | None:
    users_db = get_users(key_id, with_password=True, with_timestamps=True)
    if user_id not in users_db.keys():
        return None

    user = users_db.pop(user_id)
    set_users(key_id, users_db)

    return user


def set_users(key_id, users: Dict[str, Dict]) -> Dict | None:
    crud.store(format_key(key_id), users)
    return users


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
            "permissions": <dict_of_permissions_0>
        }
    """

    user = get_user_by_username(key_id, username, with_password=True)
    if not user:
        return None

    if check_password(password, user["password"]):
        return {k: v for k, v in user.items() if k != "password"}

    return None


def destroy_all(agent_id: str) -> None:
    crud.destroy(format_key(agent_id))
