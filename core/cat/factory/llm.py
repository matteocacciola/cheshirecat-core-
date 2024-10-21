from langchain_core.language_models import BaseLanguageModel
from langchain_openai import AzureChatOpenAI
from langchain_openai import AzureOpenAI
from langchain_community.llms import (
    HuggingFaceTextGenInference,
    HuggingFaceEndpoint,
)
from langchain_openai import ChatOpenAI, OpenAI
from langchain_cohere import ChatCohere
from langchain_google_genai import ChatGoogleGenerativeAI
from typing import Type, Dict, List
import json
from pydantic import BaseModel, ConfigDict

from cat.db.cruds import settings as crud_settings
from cat.factory.custom_llm import LLMDefault, LLMCustom, CustomOpenAI, CustomOllama
from cat.log import log
from cat.mad_hatter.mad_hatter import MadHatter


# Base class to manage LLM configuration.
class LLMSettings(BaseModel):
    _is_multimodal: bool = False

    # class instantiating the model
    _pyclass: Type[BaseLanguageModel] = None

    # This is related to pydantic, because "model_*" attributes are protected.
    # We deactivate the protection because langchain relies on several "model_*" named attributes
    model_config = ConfigDict(protected_namespaces=())

    # instantiate an LLM from configuration
    @classmethod
    def get_llm_from_config(cls, config) -> BaseLanguageModel:
        if cls._pyclass:
            return cls._pyclass.default(**config)
        raise Exception("Language model configuration class is invalid. It should be a valid BaseLanguageModel class")

    @classmethod
    def pyclass(cls) -> Type[BaseLanguageModel]:
        return cls._pyclass.default

    @classmethod
    def is_multimodal(cls) -> bool:
        return cls._is_multimodal.default


class LLMDefaultConfig(LLMSettings):
    _pyclass: Type = LLMDefault

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Default Language Model",
            "description": "A dumb LLM just telling that the Cat is not configured. "
            "There will be a nice LLM here once consumer hardware allows it.",
            "link": "",
        }
    )


class LLMCustomConfig(LLMSettings):
    url: str
    auth_key: str = "optional_auth_key"
    options: str = "{}"

    _pyclass: Type = LLMCustom

    # instantiate Custom LLM from configuration
    @classmethod
    def get_llm_from_config(cls, config):
        options = config["options"]
        # options are inserted as a string in the admin
        if isinstance(options, str):
            if options != "":
                config["options"] = json.loads(options)
            else:
                config["options"] = {}

        return cls._pyclass.default(**config)

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Custom LLM",
            "description": "LLM on a custom endpoint. See docs for examples.",
            "link": "https://cheshirecat.ai/custom-large-language-model/",
        }
    )


class LLMOpenAICompatibleConfig(LLMSettings):
    url: str
    temperature: float = 0.01
    model_name: str
    api_key: str
    streaming: bool = True

    _pyclass: Type = CustomOpenAI

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "OpenAI-compatible API",
            "description": "Configuration for OpenAI-compatible APIs, e.g. llama-cpp-python server, text-generation-webui, OpenRouter, TinyLLM, TogetherAI and many others.",
            "link": "",
        }
    )


class LLMOpenAIChatConfig(LLMSettings):
    openai_api_key: str
    model_name: str = "gpt-4o-mini"
    temperature: float = 0.7
    streaming: bool = True

    _pyclass: Type = ChatOpenAI

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "OpenAI ChatGPT",
            "description": "Chat model from OpenAI",
            "link": "https://platform.openai.com/docs/models/overview",
        }
    )


class LLMOpenAIConfig(LLMSettings):
    openai_api_key: str
    model_name: str = "gpt-3.5-turbo-instruct"
    temperature: float = 0.7
    streaming: bool = True

    _pyclass: Type = OpenAI

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "OpenAI GPT-3",
            "description": "OpenAI GPT-3. More expensive but also more flexible than ChatGPT.",
            "link": "https://platform.openai.com/docs/models/overview",
        }
    )


# https://learn.microsoft.com/en-gb/azure/cognitive-services/openai/reference#chat-completions
class LLMAzureChatOpenAIConfig(LLMSettings):
    openai_api_key: str
    model_name: str = "gpt-35-turbo"  # or gpt-4, use only chat models !
    azure_endpoint: str
    max_tokens: int = 2048
    openai_api_type: str = "azure"
    # Dont mix api versions https://github.com/hwchase17/langchain/issues/4775
    openai_api_version: str = "2023-05-15"
    azure_deployment: str
    streaming: bool = True

    _pyclass: Type = AzureChatOpenAI

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Azure OpenAI Chat Models",
            "description": "Chat model from Azure OpenAI",
            "link": "https://azure.microsoft.com/en-us/products/ai-services/openai-service",
        }
    )


# https://python.langchain.com/en/latest/modules/models/llms/integrations/azure_openai_example.html
class LLMAzureOpenAIConfig(LLMSettings):
    openai_api_key: str
    azure_endpoint: str
    max_tokens: int = 2048
    api_type: str = "azure"
    # https://learn.microsoft.com/en-us/azure/cognitive-services/openai/reference#completions
    # Current supported versions 2022-12-01, 2023-03-15-preview, 2023-05-15
    # Don't mix api versions: https://github.com/hwchase17/langchain/issues/4775
    api_version: str = "2023-05-15"
    azure_deployment: str = "gpt-35-turbo-instruct"
    model_name: str = "gpt-35-turbo-instruct"  # Use only completion models !
    streaming: bool = True

    _pyclass: Type = AzureOpenAI

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Azure OpenAI Completion models",
            "description": "Configuration for Cognitive Services Azure OpenAI",
            "link": "https://azure.microsoft.com/en-us/products/ai-services/openai-service",
        }
    )


class LLMCohereConfig(LLMSettings):
    cohere_api_key: str
    model: str = "command"
    temperature: float = 0.7
    streaming: bool = True

    _pyclass: Type = ChatCohere

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Cohere",
            "description": "Configuration for Cohere language model",
            "link": "https://docs.cohere.com/docs/models",
        }
    )


# https://python.langchain.com/en/latest/modules/models/llms/integrations/huggingface_textgen_inference.html
class LLMHuggingFaceTextGenInferenceConfig(LLMSettings):
    inference_server_url: str
    max_new_tokens: int = 512
    top_k: int = 10
    top_p: float = 0.95
    typical_p: float = 0.95
    temperature: float = 0.01
    repetition_penalty: float = 1.03

    _pyclass: Type = HuggingFaceTextGenInference

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "HuggingFace TextGen Inference",
            "description": "Configuration for HuggingFace TextGen Inference",
            "link": "https://huggingface.co/text-generation-inference",
        }
    )


# https://api.python.langchain.com/en/latest/llms/langchain_community.llms.huggingface_endpoint.HuggingFaceEndpoint.html
class LLMHuggingFaceEndpointConfig(LLMSettings):
    endpoint_url: str
    huggingfacehub_api_token: str
    task: str = "text-generation"
    max_new_tokens: int = 512
    top_k: int = None
    top_p: float = 0.95
    temperature: float = 0.8
    return_full_text: bool = False

    _pyclass: Type = HuggingFaceEndpoint

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "HuggingFace Endpoint",
            "description": "Configuration for HuggingFace Endpoint language models",
            "link": "https://huggingface.co/inference-endpoints",
        }
    )


class LLMOllamaConfig(LLMSettings):
    base_url: str
    model: str = "llama3"
    num_ctx: int = 2048
    repeat_last_n: int = 64
    repeat_penalty: float = 1.1
    temperature: float = 0.8

    _pyclass: Type = CustomOllama

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Ollama",
            "description": "Configuration for Ollama",
            "link": "https://ollama.ai/library",
        }
    )


class LLMGeminiChatConfig(LLMSettings):
    """Configuration for the Gemini large language model (LLM).

    This class inherits from the `LLMSettings` class and provides default values for the following attributes:

    * `google_api_key`: The Google API key used to access the Google Natural Language Processing (NLP) API.
    * `model`: The name of the LLM model to use. In this case, it is set to "gemini".
    * `temperature`: The temperature of the model, which controls the creativity and variety of the generated responses.
    * `top_p`: The top-p truncation value, which controls the probability of the generated words.
    * `top_k`: The top-k truncation value, which controls the number of candidate words to consider during generation.
    * `max_output_tokens`: The maximum number of tokens to generate in a single response.

    The `LLMGeminiChatConfig` class is used to create an instance of the Gemini LLM model, which can be used to generate text in natural language.
    """

    google_api_key: str
    model: str = "gemini-1.5-pro-latest"
    temperature: float = 0.1
    top_p: int = 1
    top_k: int = 1
    max_output_tokens: int = 29000

    _pyclass: Type = ChatGoogleGenerativeAI

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Google Gemini",
            "description": "Configuration for Gemini",
            "link": "https://deepmind.google/technologies/gemini",
        }
    )


def get_allowed_language_models(mad_hatter: MadHatter) -> List[Type[LLMSettings]]:
    list_llms_default = [
        LLMOpenAIChatConfig,
        LLMOpenAIConfig,
        LLMOpenAICompatibleConfig,
        LLMOllamaConfig,
        LLMGeminiChatConfig,
        LLMCohereConfig,
        LLMAzureOpenAIConfig,
        LLMAzureChatOpenAIConfig,
        LLMHuggingFaceEndpointConfig,
        LLMHuggingFaceTextGenInferenceConfig,
        LLMCustomConfig,
        LLMDefaultConfig,
    ]

    list_llms = mad_hatter.execute_hook(
        "factory_allowed_llms", list_llms_default, cat=None
    )
    return list_llms


def get_llms_schemas(mad_hatter: MadHatter) -> Dict:
    # llm_schemas contains metadata to let any client know
    # which fields are required to create the language model.
    llm_schemas = {}
    for config_class in get_allowed_language_models(mad_hatter):
        schema = config_class.model_json_schema()
        # useful for clients in order to call the correct config endpoints
        schema["languageModelName"] = schema["title"]
        llm_schemas[schema["title"]] = schema

    return llm_schemas


def get_llm_config_class_from_model(cls: Type[BaseLanguageModel], mad_hatter: MadHatter) -> Type[LLMSettings] | None:
    """Find the class of the llm adapter"""

    return next(
        (config_class for config_class in get_allowed_language_models(mad_hatter) if config_class.pyclass() == cls),
        None
    )


def get_llm_from_config_name(agent_id: str, config_name: str, mad_hatter: MadHatter) -> BaseLanguageModel:
    """
    Get the language model from the configuration name.

    Args:
        agent_id: The agent key
        config_name: The configuration name
        mad_hatter: The MadHatter instance

    Returns:
        BaseLanguageModel: The language model instance
    """

    # get LLM factory class
    list_llms = get_allowed_language_models(mad_hatter)
    factory_class = next((cls for cls in list_llms if cls.__name__ == config_name), None)
    if not factory_class:
        log.warning(f"LLM class {config_name} not found in the list of allowed LLMs")
        return LLMDefaultConfig.get_llm_from_config({})

    # obtain configuration and instantiate LLM
    selected_llm_config = crud_settings.get_setting_by_name(agent_id, config_name)
    try:
        llm = factory_class.get_llm_from_config(selected_llm_config["value"])
    except Exception:
        import traceback
        traceback.print_exc()

        llm = LLMDefaultConfig.get_llm_from_config({})

    return llm


def get_config_class_name(cls: Type[LLMSettings]) -> str:
    return cls.__name__