import redis

from cat.utils import singleton
from cat.env import get_env

DEFAULT_AGENT_KEY = "agent"  # default agent_id for backward compatibility
DEFAULT_SYSTEM_KEY = "system"


@singleton
class Database:
    def __init__(self):
        self.db = self.get_redis_client()

    def get_redis_client(self) -> redis.Redis:
        password = get_env("CCAT_REDIS_PASSWORD")

        if password:
            return redis.Redis(
                host=get_env("CCAT_REDIS_HOST"),
                port=int(get_env("CCAT_REDIS_PORT")),
                db=get_env("CCAT_REDIS_DB"),
                password=password,
                encoding="utf-8",
                decode_responses=True
            )

        return redis.Redis(
            host=get_env("CCAT_REDIS_HOST"),
            port=int(get_env("CCAT_REDIS_PORT")),
            db=get_env("CCAT_REDIS_DB"),
            encoding="utf-8",
            decode_responses=True
        )


def get_db() -> redis.Redis:
    return Database().db
