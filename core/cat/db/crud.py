from typing import List, Dict

from cat.db.database import get_db


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
    new = get_db().json().set(key, path, value, nx=nx, xx=xx)
    if not new:
        return None

    return value


def delete(key: str, path: str | None = "$") -> None:
    get_db().json().delete(key, path)


def destroy(key: str) -> None:
    get_db().delete(key)
