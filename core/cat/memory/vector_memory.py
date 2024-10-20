
from typing import Dict

from cat.memory.vector_memory_collection import VectorMemoryCollection, VectoryMemoryCollectionTypes


class VectorMemory:
    collections: Dict[str, VectorMemoryCollection] = {}

    def __init__(
        self,
        agent_id: str,
        embedder_name: str | None = None,
        embedder_size: int | None = None,
    ) -> None:
        # Create vector collections
        # - Episodic memory will contain user and eventually cat utterances
        # - Declarative memory will contain uploaded documents' content
        # - Procedural memory will contain tools and knowledge on how to do things
        for collection_name in VectoryMemoryCollectionTypes:
            # Instantiate collection
            collection = VectorMemoryCollection(
                agent_id=agent_id,
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

    def wipe_collections(self) -> None:
        for c in VectoryMemoryCollectionTypes:
            self.collections[str(c)].wipe()
