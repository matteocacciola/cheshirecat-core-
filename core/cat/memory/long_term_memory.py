from cat.memory.utils import VectorMemoryConfig
from cat.memory.vector_memory import VectorMemory


# This class represents the Cat long term memory (content the cat saves on disk).
class LongTermMemory:
    """
    Cat's non-volatile memory.

    This is an abstract class to interface with the Cat's vector memory collections.

    Attributes
    ----------
    vectors: VectorMemory
        Vector Memory collection.
    """

    def __init__(self, agent_id: str):
        # Vector based memory (will store embeddings and their metadata)
        self.vectors = VectorMemory(agent_id)

    def destroy(self) -> None:
        """Wipe all data from the long term memory."""

        self.vectors.destroy_collections()
        self.vectors = None
