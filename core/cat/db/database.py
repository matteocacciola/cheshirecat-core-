import redis

from cat.utils import singleton
from cat.env import get_env


@singleton
class Database:
    def __init__(self):
        password = get_env("CCAT_REDIS_PASSWORD")

        if password:
            client = redis.Redis(
                host=get_env("CCAT_REDIS_HOST"),
                port=int(get_env("CCAT_REDIS_PORT")),
                db=get_env("CCAT_REDIS_DB"),
                password=password,
                encoding="utf-8",
                decode_responses=True
            )
        else:
            client = redis.Redis(
                host=get_env("CCAT_REDIS_HOST"),
                port=int(get_env("CCAT_REDIS_PORT")),
                db=get_env("CCAT_REDIS_DB"),
                encoding="utf-8",
                decode_responses=True
            )

        self.db = client


def get_db() -> redis.Redis:
    return Database().db
