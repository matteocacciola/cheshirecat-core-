import os
import sys
import socket

import portalocker
from qdrant_client import QdrantClient

from cat.log import log
from cat.env import get_env
from cat.utils import extract_domain_from_url, is_https, singleton

LOCAL_FOLDER_PATH = "cat/data/local_vector_memory/"


@singleton
class VectorDatabase:
    def __init__(self):
        self.local_vector_db = None
        self.db = self.connect_to_vector_memory()

    def connect_to_vector_memory(self) -> QdrantClient:
        qdrant_host = get_env("CCAT_QDRANT_HOST")
        if qdrant_host:
            # Qdrant remote or in other container
            qdrant_port = int(get_env("CCAT_QDRANT_PORT"))
            qdrant_https = is_https(qdrant_host)
            qdrant_host = extract_domain_from_url(qdrant_host)
            qdrant_api_key = get_env("CCAT_QDRANT_API_KEY")

            s = None
            try:
                s = socket.socket()
                s.connect((qdrant_host, qdrant_port))
            except Exception:
                log.error(f"QDrant does not respond to {qdrant_host}:{qdrant_port}")
                sys.exit()
            finally:
                if s:
                    s.close()

            # Qdrant vector DB client
            return QdrantClient(
                host=qdrant_host,
                port=qdrant_port,
                https=qdrant_https,
                api_key=qdrant_api_key or None,
            )

        # Qdrant local vector DB client
        db_path = LOCAL_FOLDER_PATH
        log.info(f"Qdrant path: {db_path}")

        # reconnect only if it's the first boot and not a reload
        if self.local_vector_db is None:
            self.local_vector_db = QdrantClient(path=db_path, force_disable_check_same_thread=True)

        return self.local_vector_db


def get_vector_db() -> QdrantClient:
    return VectorDatabase().db


def unlock_local_vector_db():
    lock_file_path = os.path.join(LOCAL_FOLDER_PATH, ".lock")
    if not os.path.exists(lock_file_path):
        return

    try:
        with open(lock_file_path, "r+") as lock_file:
            portalocker.unlock(lock_file)
    except (IOError, portalocker.LockException):
        pass  # If we can't unlock, it's probably already unlocked
