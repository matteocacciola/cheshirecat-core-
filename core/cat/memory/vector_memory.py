import sys
import socket
from qdrant_client import QdrantClient

from cat.memory.models import MemoryCollection
from cat.memory.vector_memory_collection import VectorMemoryCollection
from cat.log import log
from cat.env import get_env
from cat.utils import extract_domain_from_url, is_https


# @singleton REFACTOR: worth it to have this (or LongTermMemory) as singleton?
class VectorMemory:
    local_vector_db = None

    def __init__(
        self,
        agent_id: str,
        embedder_name: str | None = None,
        embedder_size: int | None = None,
    ) -> None:
        # connects to Qdrant and creates self.vector_db attribute
        self.vector_db = self.connect_to_vector_memory()

        # Create vector collections
        # - Episodic memory will contain user and eventually cat utterances
        # - Declarative memory will contain uploaded documents' content
        # - Procedural memory will contain tools and knowledge on how to do things
        self.collections = {}
        for collection_name in MemoryCollection:
            # Instantiate collection
            collection = VectorMemoryCollection(
                agent_id=agent_id,
                client=self.vector_db,
                collection_name=str(collection_name),
                embedder_name=embedder_name,
                embedder_size=embedder_size,
            )

            # Update dictionary containing all collections
            # Useful for cross-searching and to create/use collections from plugins
            self.collections[str(collection_name)] = collection

            # Have the collection as an instance attribute
            # (i.e. do things like cat.memory.vectors.declarative.something())
            setattr(self, str(collection_name), collection)

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
        db_path = "cat/data/local_vector_memory/"
        log.info(f"Qdrant path: {db_path}")

        # reconnect only if it's the first boot and not a reload
        if VectorMemory.local_vector_db is None:
            VectorMemory.local_vector_db = QdrantClient(
                path=db_path, force_disable_check_same_thread=True
            )

        return VectorMemory.local_vector_db
