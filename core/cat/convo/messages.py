import time
from typing import List, Literal, Dict
from langchain_core.messages import AIMessage, HumanMessage, BaseMessage
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
    """
    Class for wrapping message why

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
    agent_output: Dict | None = None


class CatMessage(BaseModelDict):
    """
    Class for wrapping cat message

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
    """
    Class for wrapping user message

    Variables:
        text (str): user message
        image (str): image or None, the eventual image in the message
        audio (str): audio or None, the eventual audio in the message
        user_id (str): user id
        agent_id (str): agent id
    """

    text: str
    image: str | None = None
    audio: str | None = None
    user_id: str
    agent_id: str


class ConversationHistoryInfo(BaseModelDict):
    """
    Class for wrapping conversation history info

    Variables:
        who (Role): role
        message (str): message
        image (str): image or None, the eventual image in the message
        audio (str): audio or None, the eventual audio in the message
        why (MessageWhy): message why
        when (float): when
        role (Role): role
    """

    who: Role
    message: str
    image: str | None = None
    audio: str | None = None
    why: MessageWhy | None = None
    when: float | None = time.time()
    role: Role
    user_id: str
    agent_id: str


def convert_to_langchain_message(history_info: ConversationHistoryInfo) -> BaseMessage:
    if history_info.role == Role.HUMAN:
        content = [{"type": "text", "text": history_info.message}]
        if history_info.image:
            content.append({"type": "image_url", "image_url": {"url": history_info.image}})
        if history_info.audio:
            content.append({"type": "audio_url", "audio_url": {"url": history_info.audio}})
        return HumanMessage(
            name=str(history_info.who),
            content=content,
            response_metadata={"userId": history_info.user_id, "agentId": history_info.agent_id}
        )

    return AIMessage(
        name=str(history_info.who),
        content=history_info.message,
        response_metadata={"userId": history_info.user_id, "agentId": history_info.agent_id}
    )


def convert_to_langchain_messages(history: List[ConversationHistoryInfo]) -> List[BaseMessage]:
    return [convert_to_langchain_message(h) for h in history]


def convert_to_cat_message(ai_message: AIMessage, why: MessageWhy) -> CatMessage:
    return CatMessage(
        content=ai_message.content,
        user_id=ai_message.response_metadata["userId"],
        agent_id=ai_message.response_metadata["agentId"],
        why=why,
    )


def convert_to_conversation_history_info(info: Dict, user_id: str, agent_id: str) -> ConversationHistoryInfo:
    return ConversationHistoryInfo(**{**info, **{"user_id": user_id, "agent_id": agent_id}})


def convert_to_conversation_history(infos: List[Dict], user_id: str, agent_id: str) -> List[ConversationHistoryInfo]:
    return [convert_to_conversation_history_info(info, user_id, agent_id) for info in infos]
