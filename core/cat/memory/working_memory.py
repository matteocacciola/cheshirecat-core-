from typing import List, Any
from typing_extensions import deprecated

from cat.agents import AgentInput
from cat.convo.messages import (
    Role,
    BaseMessage,
    CatMessage,
    UserMessage,
    ModelInteraction,
    MessageWhy,
    ConversationHistoryItem,
    ConversationHistory,
    convert_to_conversation_history,
)
from cat.db.cruds import history as crud_history
from cat.experimental.form.cat_form import CatForm
from cat.memory.vector_memory_collection import VectoryMemoryCollectionTypes
from cat.utils import BaseModelDict


class WorkingMemory(BaseModelDict):
    """
    Cat's volatile memory.

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

    # stores conversation history
    history: ConversationHistory | None = []
    user_message: UserMessage | None = None
    active_form: CatForm | None = None

    # recalled memories attributes
    recall_query: str = ""

    agent_input: AgentInput | None = None

    # track models usage
    model_interactions: List[ModelInteraction] = []

    def __init__(self, **data: Any):
        super().__init__(**data)

        self.history = convert_to_conversation_history(crud_history.get_history(self.agent_id, self.user_id))

        for collection_name in VectoryMemoryCollectionTypes:
            setattr(self, f"{collection_name}_memories".lower(), [])

    def set_history(self, conversation_history: ConversationHistory) -> "WorkingMemory":
        """
        Set the conversation history.

        Args:
            conversation_history: The conversation history to save

        Returns:
            The current instance of the WorkingMemory class.
        """

        crud_history.set_history(
            self.agent_id, self.user_id, [message.model_dump() for message in conversation_history]
        )
        self.history = conversation_history

        return self

    def reset_history(self) -> "WorkingMemory":
        """
        Reset the conversation history.

        Returns:
            The current instance of the WorkingMemory class.
        """

        crud_history.set_history(self.agent_id, self.user_id, [])
        self.history = []

        return self

    @deprecated("use `update_history` instead.")
    def update_conversation_history(
        self,
        who: Role,
        message: str,
        images: List[str] | None = None,
        audio: List[str] | None = None,
        why: MessageWhy | None = None,
    ):
        """
        Update the conversation history.

        The methods append to the history key the last three conversation turns.

        Args
            who: str
                Who said the message. Can either be Role.Human or Role.AI.
            message: str
                The message said.
            images: List[str], optional
                The images said. Default is None.
            audio: List[str], optional
                The audio said. Default is None.
            why: MessageWhy, optional
                The reason why the message was said. Default is None.
        """

        role = Role.AI if who == Role.AI else Role.HUMAN
        message = CatMessage(text=message, images=images, audio=audio, why=why) if role == Role.AI else UserMessage(
            text=message, images=images, audio=audio,
        )

        return self.update_history(role, message)

    def update_history(self, who: Role, content: BaseMessage):
        """
        Update the conversation history.

        The methods append to the history key the last three conversation turns.

        Args
            who: Role, who said the message. Can either be Role.Human or Role.AI.
            content: BaseMessage, the message said.
            why: MessageWhy, optional, the reason why the message was said. Default is None.
        """

        # we are sure that who is not change in the current call
        conversation_history_info = ConversationHistoryItem(who=who, content=content)

        # append latest message in conversation
        self.history = convert_to_conversation_history(
            crud_history.update_history(self.agent_id, self.user_id, conversation_history_info)
        )

    @property
    def user_message_json(self) -> UserMessage | None:
        return self.user_message