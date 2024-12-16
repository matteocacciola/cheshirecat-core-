from typing import Dict

from cat.memory.utils import VectorMemoryCollectionTypes
from cat.memory.vector_memory_collection import VectorMemoryCollection


class VectorMemory:
    def __init__(self, agent_id: str) -> None:
        self.collections: Dict[str, VectorMemoryCollection] = {}

        # Create vector collections
        # - Episodic memory will contain user and eventually cat utterances
        # - Declarative memory will contain uploaded documents' content
        # - Procedural memory will contain tools and knowledge on how to do things
        for collection_name in VectorMemoryCollectionTypes:
            # Instantiate collection
            collection = VectorMemoryCollection(agent_id=agent_id, collection_name=str(collection_name))

            # Update dictionary containing all collections
            # Useful for cross-searching and to create/use collections from plugins
            self.collections[str(collection_name)] = collection

            # Have the collection as an instance attribute
            # (i.e. do things like cat.memory.vectors.declarative.something())
            setattr(self, str(collection_name), collection)

    def destroy_collections(self) -> None:
        for c in VectorMemoryCollectionTypes:
            self.collections[str(c)].destroy_all_points()
