import time
from abc import ABC
from typing import List, Literal, Dict, TypeAlias
from langchain_core.messages import AIMessage, HumanMessage, BaseMessage as BaseLangchainMessage
from pydantic import BaseModel, Field, ConfigDict, computed_field
import requests
import base64
from io import BytesIO
from PIL import Image
from typing_extensions import deprecated

from cat.convo.llm import LargeLanguageModelModality
from cat.log import log
from cat.utils import BaseModelDict, Enum


class Role(Enum):
    """
    Enum for role of the agent in the conversation history info. It can be either AI or Human (Enum).

    Variables:
        AI (str): AI
        HUMAN (str): Human
    """
    AI = "AI"
    HUMAN = "Human"


class ModelInteraction(BaseModel):
    """
    Class for wrapping model interaction in the conversation history info. It can be either LLMModelInteraction or
    EmbedderModelInteraction.

    Variables:
        model_type (Literal["llm", "embedder"]): model type
        source (str): source of the model interaction
        prompt (str): prompt for the model interaction
        input_tokens (int): input tokens
        started_at (float): started at time in seconds since epoch (default: time.time())
    """

    model_type: Literal["llm", "embedder"]
    source: str
    prompt: str
    input_tokens: int
    started_at: float = Field(default_factory=lambda: time.time())

    model_config = ConfigDict(protected_namespaces=())


class LLMModelInteraction(ModelInteraction):
    """
    Class for wrapping LLM model interaction in the conversation history info. It is a subclass of ModelInteraction.

    Variables:
        model_type (Literal["llm"]): model type
        reply (str): reply to the input
        output_tokens (int): output tokens
        ended_at (float): ended at time in seconds since epoch (default: time.time())
    """

    model_type: Literal["llm"] = Field(default="llm")
    reply: str
    output_tokens: int
    ended_at: float


class EmbedderModelInteraction(ModelInteraction):
    """
    Class for wrapping Embedder model interaction in the conversation history info. It is a subclass of ModelInteraction.

    Variables:
        model_type (Literal["embedder"]): model type
        source (str): source of the model interaction
        reply (List[float]): reply
    """

    model_type: Literal["embedder"] = Field(default="embedder")
    source: str = Field(default="recall")
    reply: List[float]


class MessageWhy(BaseModelDict):
    """
    Class for wrapping message why. This is used to explain why the agent replied with the message.

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


class BaseMessage(BaseModelDict, ABC):
    """
    Class for wrapping cat or human message.

    Variables:
        text (str): cat message
        images (List[str]): images or None, the eventual images in the message
        audio (List[str]): audio or None, the eventual audio in the message
    """

    text: str
    images: List[str] | None = None
    audio: List[str] | None = None


class CatMessage(BaseMessage):
    """
    Class for wrapping cat message. This is used to send the message to the cat. It is based on the BaseMessage class.

    Variables:
        text (str): cat message
        images (List[str]): images or None, the eventual images in the message
        audio (List[str]): audio or None, the eventual audio in the message
        why (MessageWhy): why the agent replied with the message
    """

    why: MessageWhy | None = None

    @computed_field
    @property
    def type(self) -> str:
        return "chat"

    @computed_field
    @property
    @deprecated("This attribute is deprecated. Use `text` instead.")
    def content(self) -> str:
        """
        This attribute is deprecated. Use `text` instead. Get the text content of the message.

        Returns:
            str: The text content of the message.
        """
        return self.text

    @content.setter
    def content(self, value: str):
        """
        This attribute is deprecated. Use `text` instead. Set the text content of the message.

        Args:
            value: str
        """
        self.text = value


class UserMessage(BaseMessage):
    """
    Class for wrapping user message. This is used to send the message to the agent. It is based on the BaseMessage
    class.

    Variables:
        text (str): user message
        images (List[str]): images or None, the eventual images in the message
        audio (List[str]): audio or None, the eventual audio in the message
    """
    pass


class ConversationHistoryItem(BaseModelDict):
    """
    Class for wrapping conversation history items. This is used to store the conversation history. It can be either AI
    or Human. The conversation history is then persisted in the database.

    Variables:
        who (Role): who is the author of the message (AI or Human)
        when (float): when the message was sent in seconds since epoch (default: time.time())
        content (BaseMessage): content of the message
    """

    who: Role
    when: float | None = time.time()
    content: BaseMessage

    @computed_field
    @property
    @deprecated("This attribute is deprecated. Use `content.text` instead")
    def message(self) -> str:
        """
        This attribute is deprecated. Use `content.text` instead. Get the text content of the message.

        Returns:
            str: The text content of the message.
        """
        return self.content.text

    @message.setter
    def message(self, value: str):
        """
        This attribute is deprecated. Use `content.text` instead. Set the text content of the message.

        Args:
            value: str
        """
        self.content.text = value

    @computed_field
    @property
    @deprecated("This attribute is deprecated. Use `content.why` instead")
    def why(self) -> MessageWhy | None:
        """
        This attribute is deprecated. Use `content.why` instead. Deprecated. Get additional context about the message.

        Returns:
            MessageWhy (optional): The additional context about the message, or None.
        """

        return self.content.why if isinstance(self.content, CatMessage) else None

    @why.setter
    def why(self, value: MessageWhy | None):
        """
        This attribute is deprecated. Use `content.why` instead. Set additional context about the message.

        Args:
            value: MessageWhy | None
        """
        self.content.why = value

    @computed_field
    @property
    @deprecated("This attribute is deprecated. Use `who` instead")
    def role(self) -> Role:
        """
        This attribute is deprecated. Use `who` instead. Get the name of the message author.

        Returns
            Role: The author of the speaker.
        """
        return self.who

    @role.setter
    def role(self, value: Role):
        """
        This attribute is deprecated. Use `who` instead. Set the name of the message author.

        Args:
            value: Role
        """
        self.who = value


ConversationHistory: TypeAlias = List[ConversationHistoryItem]


def convert_to_langchain_message(
    history_info: ConversationHistoryItem, llm_modalities: LargeLanguageModelModality
) -> BaseLangchainMessage:
    """
    Convert a conversation history info to a langchain message. The langchain message can be either an AI message or a
    human message.

    Args:
        history_info: ConversationHistoryInfo, the conversation history info to convert
        llm_modalities: LargeLanguageModelModality, the supported modalities of the LLM

    Returns:
        BaseLangchainMessage: The langchain message
    """
    def format_image(image: str) -> str | None:
        if llm_modalities.data_uri:
            return image
        if image.startswith("http"):
            if llm_modalities.image_url:
                return image
            try:
                response = requests.get(image)
                if response.status_code == 200:
                    # Open the image using Pillow to determine its MIME type
                    # Get MIME type (e.g., jpeg, png)
                    mime_type = Image.open(BytesIO(response.content)).format.lower()
                    # Encode the image to base64
                    encoded_image = base64.b64encode(response.content).decode('utf-8')
                    image_uri = f"data:image/{mime_type};base64,{encoded_image}"
                    # Add the image as a data URI with the correct MIME type
                    return image_uri
            except Exception as e:
                log.error(f"Failed to process image {image}: {e}")
                return None
        return None

    if history_info.who == Role.AI:
        return AIMessage(name=str(history_info.who), content=history_info.content.text)

    content = [{"type": "text", "text": history_info.content.text}]
    if history_info.content.images:
        formatted_images = [format_image(image) for image in history_info.content.images]
        content.extend([{"type": "image_url", "image_url": {"url": image}} for image in formatted_images if image])
    if history_info.content.audio:
        content.extend([
            {"type": "audio_url", "audio_url": {"url": audio}} for audio in history_info.content.audio
        ])

    return HumanMessage(name=str(history_info.who), content=content)


def convert_to_cat_message(ai_message: AIMessage, why: MessageWhy) -> CatMessage:
    content = ai_message.content

    if isinstance(content, str):
        return CatMessage(text=content, why=why)

    images = []
    audio = []
    text = None
    for item in content:
        if isinstance(item, str):
            text = item
            continue

        if "type" not in item:
            continue

        match item["type"]:
            case "text":
                text = item
            case "image_url":
                images.append(item["image_url"]["url"])
            case "audio_url":
                audio.append(item["audio_url"]["url"])

    return CatMessage(text=text, images=images, audio=audio, why=why)


def convert_to_conversation_history(infos: List[Dict]) -> ConversationHistory:
    return [ConversationHistoryItem(**info) for info in infos]
