from typing import List, Any, Dict

from cat.agents import AgentInput
from cat.convo.messages import Role, UserMessage, ModelInteraction, MessageWhy, ConversationHistoryInfo
from cat.db.cruds import history as crud_history
from cat.experimental.form.cat_form import CatForm
from cat.memory.vector_memory_collection import VectoryMemoryCollectionTypes
from cat.utils import BaseModelDict


class WorkingMemory(BaseModelDict):
    """Cat's volatile memory.

    Handy class that behaves like a `Dict` to store temporary custom data.

    Returns:
        Dict[str, List]: Default instance is a dictionary with `history` key set to an empty list.

    Notes
    -----
    The constructor instantiates a dictionary with a `history` key set to an empty list that is further used to store
    the conversation turns between the Human and the AI.
    """

    agent_id: str
    user_id: str

    user_message_json: UserMessage | None = None
    active_form: CatForm | None = None

    # recalled memories attributes
    recall_query: str = ""

    agent_input: AgentInput | None = None

    # track models usage
    model_interactions: List[ModelInteraction] = []

    def __init__(self, **data: Any):
        super().__init__(**data)

        self.__history = self.__to_list_conversation_history_info(crud_history.get_history(self.agent_id, self.user_id))

        # Have the memories as instance attributes (i.e. do things like stray.working_memory.declarative_memories
        # or stray.working_memory.declarative_memories[something])
        # Each element is a List[Tuple[Document, float]] where the first element is the document and the second is the
        # similarity score
        for collection_name in VectoryMemoryCollectionTypes:
            setattr(self, f"{collection_name}_memories".lower(), [])

    def set_conversation_history(self, conversation_history: List[ConversationHistoryInfo]) -> "WorkingMemory":
        """
        Set the conversation history.

        Args:
            conversation_history: The conversation history to save

        Returns:
            The current instance of the WorkingMemory class.
        """

        conversation_history = [message.model_dump() for message in conversation_history]

        crud_history.set_history(self.agent_id, self.user_id, conversation_history)
        self.__history = conversation_history

        return self

    def reset_conversation_history(self) -> "WorkingMemory":
        """
        Reset the conversation history.

        Returns:
            The current instance of the WorkingMemory class.
        """

        crud_history.set_history(self.agent_id, self.user_id, [])
        self.__history = []

        return self

    def update_conversation_history(self, who: Role, message: str, why: MessageWhy | None = None):
        """Update the conversation history.

        The methods append to the history key the last three conversation turns.

        Args
            who : str
                Who said the message. Can either be Role.Human or Role.AI.
            message : str
                The message said.
            why : MessageWhy, optional
                The reason why the message was said. Default is None.
        """

        role = Role.AI if who == Role.AI else Role.HUMAN

        # TODO: Message should be of type CatMessage or UserMessage. For backward compatibility we put a new key
        # we are sure that who is not change in the current call
        conversation_history_info = ConversationHistoryInfo(who=who, message=message, why=why, role=role)

        # append latest message in conversation
        conversation_history = crud_history.update_history(self.agent_id, self.user_id, conversation_history_info)
        self.__history = self.__to_list_conversation_history_info(conversation_history)

    def __to_list_conversation_history_info(self, conversation_history: List[Dict]):
        return [ConversationHistoryInfo(**m) for m in conversation_history]

    @property
    def history(self) -> List[ConversationHistoryInfo]:
        """Get the conversation history.

        Returns:
            List[ConversationHistoryInfo]: The conversation history.
        """

        return self.__history
