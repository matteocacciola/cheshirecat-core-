import redis

from cat.utils import singleton
from cat.env import get_env


@singleton
class Database:
    def __init__(self):
        self.db = redis.Redis(
            host=get_env("CCAT_REDIS_HOST"),
            port=get_env("CCAT_REDIS_PORT"),
            db=get_env("CCAT_REDIS_DB"),
            password=get_env("CCAT_REDIS_PASSWORD"),
            encoding="utf-8",
            decode_responses=True
        )


def get_db() -> redis.Redis:
    return Database().db
