from enum import Enum
from typing import List, Dict

from cat.db.database import get_db, DEFAULT_SYSTEM_KEY


def serialize_to_redis_json(data_dict: List | Dict) -> List | Dict:
    """
    Save a dictionary in a Redis JSON, correctly handling the enums.

    Args:
        data_dict (dict): dictionary to save

    Returns:
        dict: dictionary saved
    """

    if isinstance(data_dict, list):
        return [serialize_to_redis_json(d) for d in data_dict]

    return {k: v.value if isinstance(v, Enum) else v for k, v in data_dict.items()}


def read(key: str, path: str | None = "$") -> List[Dict] | Dict | None:
    value = get_db().json().get(key, path)
    if not value:
        return None

    if isinstance(value[0], list):
        return value[0]

    return value


def store(
    key: str, value: List | Dict, path: str | None = "$", nx: bool = False, xx: bool = False
) -> List[Dict] | Dict | None:
    formatted = serialize_to_redis_json(value)
    new = get_db().json().set(key, path, formatted, nx=nx, xx=xx)
    if not new:
        return None

    return value


def delete(key: str, path: str | None = "$") -> None:
    get_db().json().delete(key, path)


def destroy(key: str) -> None:
    for k in get_db().scan_iter(key):
        get_db().delete(k)


def get_agents_main_keys() -> List[str]:
    return list({k.split(":")[0]for k in get_db().scan_iter("*") if k.split(":")[0] != DEFAULT_SYSTEM_KEY})
