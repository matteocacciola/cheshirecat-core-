import time
from typing import List, Literal, Dict
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, Field, ConfigDict

from cat.utils import BaseModelDict, Enum


class Role(Enum):
    AI = "AI"
    HUMAN = "Human"


class ModelInteraction(BaseModel):
    model_type: Literal["llm", "embedder"]
    source: str
    prompt: str
    input_tokens: int
    started_at: float = Field(default_factory=lambda: time.time())

    model_config = ConfigDict(protected_namespaces=())


class LLMModelInteraction(ModelInteraction):
    model_type: Literal["llm"] = Field(default="llm")
    reply: str
    output_tokens: int
    ended_at: float


class EmbedderModelInteraction(ModelInteraction):
    model_type: Literal["embedder"] = Field(default="embedder")
    source: str = Field(default="recall")
    reply: List[float]


class MessageWhy(BaseModelDict):
    """Class for wrapping message why

    Variables:
        input (str): input message
        intermediate_steps (List): intermediate steps
        memory (Dict): memory
        model_interactions (List[LLMModelInteraction | EmbedderModelInteraction]): model interactions
    """

    input: str
    intermediate_steps: List
    memory: Dict
    model_interactions: List[LLMModelInteraction | EmbedderModelInteraction]


class CatMessage(BaseModelDict):
    """Class for wrapping cat message

    Variables:
        content (str): cat message
        user_id (str): user id
        agent_id (str): agent id
        type (str): message type
        why (MessageWhy): message why
    """

    content: str
    user_id: str
    agent_id: str
    type: str = "chat"
    why: MessageWhy | None = None


class UserMessage(BaseModelDict):
    """Class for wrapping user message

    Variables:
        text (str): user message
        user_id (str): user id
        agent_id (str): agent id
    """

    text: str
    image: str | None = None
    user_id: str
    agent_id: str


class ConversationHistoryInfo(BaseModelDict):
    """Class for wrapping conversation history info

    Variables:
        who (Role): role
        message (str): message
        image (str): image or None
        why (MessageWhy): message why
        when (float): when
        role (Role): role
    """

    who: Role
    message: str
    image: str | None = None
    why: MessageWhy | None = None
    when: float | None = time.time()
    role: Role


def convert_to_langchain_message(
    messages: List[UserMessage | CatMessage],
) -> List[HumanMessage | AIMessage]:
    return [
        HumanMessage(content=m.text, response_metadata={"userId": m.user_id, "agentId": m.agent_id})
        if isinstance(m, UserMessage)
        else AIMessage(content=m.content, response_metadata={"userId": m.user_id, "agentId": m.agent_id})
        for m in messages
    ]


def convert_to_cat_message(cat_message: AIMessage, why: MessageWhy) -> CatMessage:
    return CatMessage(
        content=cat_message.content,
        user_id=cat_message.response_metadata["userId"],
        agent_id=cat_message.response_metadata["agentId"],
        why=why,
    )
