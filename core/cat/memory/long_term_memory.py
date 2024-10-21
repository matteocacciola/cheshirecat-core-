from typing import Dict

from cat.memory.vector_memory import VectorMemory


# This class represents the Cat long term memory (content the cat saves on disk).
class LongTermMemory:
    """Cat's non-volatile memory.

    This is an abstract class to interface with the Cat's vector memory collections.

    Attributes
    ----------
    vectors : VectorMemory
        Vector Memory collection.
    """

    def __init__(self, agent_id: str, vector_memory_config: Dict | None = None):
        vector_memory_config = vector_memory_config or {}

        # Vector based memory (will store embeddings and their metadata)
        self.vectors = VectorMemory(agent_id, **vector_memory_config)

        # What type of memory is coming next?
        # Surprise surprise, my dear!

    def wipe(self) -> None:
        """Wipe all data from the long term memory."""

        self.vectors.wipe_collections()
        self.vectors = None
