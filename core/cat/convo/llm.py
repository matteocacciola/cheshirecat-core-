from langchain_core.language_models import BaseLanguageModel
from pydantic import BaseModel
import base64
from langchain_core.messages import HumanMessage
import requests

from cat.log import log


class LargeLanguageModelModality(BaseModel):
    """
    Class for wrapping large language model modality. This is used to determine the supported modalities of the LLM.

    Variables:
        text (bool): text
        data_uri (bool): data URI
        image_url (bool): image URL
        audio_url (bool): audio URL
    """

    text: bool = True
    data_uri: bool = False
    image_url: bool = False
    audio_url: bool = False

    __url = "https://raw.githubusercontent.com/ai-blackbird/cheshirecat-core/refs/heads/main/readme/cheshire-cat.jpeg"

    def __init__(self, llm: BaseLanguageModel):
        super().__init__()
        self.__llm = llm

        fields = [field for field, info in self.model_fields.items() if info.default is False]
        for field in fields:
            value = getattr(self, f"_build_{field}")()
            setattr(self, field, self.__single_modality(field, value) if value else False)

    def _build_data_uri(self):
        try:
            response = requests.get(self.__url)
            if response.status_code == 200:
                encoded_image = base64.b64encode(response.content).decode('utf-8')
                return f"data:image/jpeg;base64,{encoded_image}"
        except Exception as e:
            log.warning(f"Failed to encode image to data URI.")
            log.debug(e)
        return None

    def _build_image_url(self):
        return self.__url

    def _build_audio_url(self):
        return None

    def __single_modality(self, field: str, value: str) -> bool:
        # Prepare message content
        content = [
            {"type": "text", "text": "Respond with `MEOW`."},
            {"type": "image_url", "image_url": {"url": value}}
        ]
        message = HumanMessage(content=content)
        # Perform the image support check
        try:
            self.__llm.invoke([message])
            return True
        except Exception as e:
            log.warning(f"The selected LLM does not support {field} as input images.")
            log.debug(e)
            return False
