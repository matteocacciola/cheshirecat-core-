import json
from typing import List, Dict

from cat.db.database import get_db
from cat.utils import DefaultAgentKeys


def __format_key(key: str) -> str:
    if key == str(DefaultAgentKeys.SYSTEM):
        return key

    return f"{DefaultAgentKeys.AGENT}:{key}"


def read(key: str) -> List | Dict | None:
    key = __format_key(key)
    value = get_db().get(key)
    if not value:
        return None

    if isinstance(value, (bytes, str)):
        return json.loads(value)
    else:
        raise ValueError(f"Unexpected type for Redis value: {type(value)}")


def store(key: str, value: List | Dict) -> List | Dict | None:
    key = __format_key(key)
    new = get_db().set(key, json.dumps(value), get=True)
    if not new:
        return None

    if isinstance(new, (bytes, str)):
        return json.loads(new)
    else:
        raise ValueError(f"Unexpected type for Redis value: {type(new)}")


def delete(key: str) -> None:
    key = __format_key(key)
    get_db().delete(key)
