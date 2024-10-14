import time
from typing import List

from cat.agents import AgentInput
from cat.convo.messages import Role, UserMessage, ModelInteraction, MessageWhy
from cat.experimental.form.cat_form import CatForm
from cat.utils import BaseModelDict


class WorkingMemory(BaseModelDict):
    """Cat's volatile memory.

    Handy class that behaves like a `Dict` to store temporary custom data.

    Returns
    -------
    Dict[str, List]
        Default instance is a dictionary with `history` key set to an empty list.

    Notes
    -----
    The constructor instantiates a dictionary with a `history` key set to an empty list that is further used to store
    the conversation turns between the Human and the AI.
    """

    # stores conversation history
    __history: List = []
    user_message_json: UserMessage | None = None
    active_form: CatForm | None = None

    # recalled memories attributes
    recall_query: str = ""
    episodic_memories: List = []
    declarative_memories: List = []
    procedural_memories: List = []

    agent_input: AgentInput | None = None

    # track models usage
    model_interactions: List[ModelInteraction] = []

    def get_conversation_history(self) -> List:
        """Get the conversation history.

        Returns
        -------
        List
            The conversation history.
        """

        return self.__history

    def set_conversation_history(self, history: List) -> "WorkingMemory":
        """
        Set the conversation history.
        Args:
            history:

        Returns:
            The current instance of the WorkingMemory class.
        """
        self.__history = history
        return self

    def reset_conversation_history(self) -> "WorkingMemory":
        """
        Reset the conversation history.

        Returns:
            The current instance of the WorkingMemory class.
        """
        self.__history = []
        return self

    def update_conversation_history(self, who, message, why: MessageWhy | None = None):
        """Update the conversation history.

        The methods append to the history key the last three conversation turns.

        Parameters
        ----------
        who : str
            Who said the message. Can either be `Human` or `AI`.
        message : str
            The message said.
        why : MessageWhy, optional
            The reason why the message was said. Default is None.

        """

        why = why.model_dump() if why else {}

        # append latest message in conversation
        # TODO: Message should be of type CatMessage or UserMessage. For backward compatibility we put a new key
        # we are sure that who is not change in the current call
        self.__history.append(
            {
                "who": who,
                "message": message,
                "why": why,
                "when": time.time(),
                "role": Role.AI if who == "AI" else Role.Human,
            }
        )
