from typing import List

from cat.factory.llm import LLMSettings
from cat.factory.embedder import EmbedderSettings
from cat.factory.auth_handler import AuthHandlerConfig
from cat.factory.plugin_filemanager import PluginFileManagerConfig
from cat.mad_hatter.decorators import hook


@hook(priority=0)
def factory_allowed_llms(allowed: List[LLMSettings], cat) -> List:
    """Hook to extend support of llms.

    Args:
        allowed : List of LLMSettings classes
            list of allowed language models
        cat : CheshireCat
            Cheshire Cat instance

    Returns:
        supported : List of LLMSettings classes
            list of allowed language models
    """
    return allowed


@hook(priority=0)
def factory_allowed_embedders(allowed: List[EmbedderSettings], cat) -> List:
    """Hook to extend list of supported embedders.

    Args:
        allowed : embedder of EmbedderSettings classes
            list of allowed embedders
        cat : CheshireCat
            Cheshire Cat instance

    Returns:
        supported : List of EmbedderSettings classes
            list of allowed embedders
    """
    return allowed


@hook(priority=0)
def factory_allowed_auth_handlers(allowed: List[AuthHandlerConfig], cat) -> List:
    """Hook to extend list of supported auth_handlers.

    Args:
        allowed : List of AuthHandlerConfig classes
            list of allowed auth_handlers
        cat : CheshireCat
            Cheshire Cat instance

    Returns:
        supported : List of AuthHandlerConfig classes
            list of allowed auth_handlers
    """

    return allowed


@hook(priority=0)
def factory_allowed_plugin_file_managers(allowed: List[PluginFileManagerConfig], cat) -> List:
    """Hook to extend list of supported plugin file managers.

    Args:
        allowed : List of PluginFileManagerConfig classes
            list of allowed plugin file managers
        cat : CheshireCat
            Cheshire Cat instance

    Returns:
        supported : List of PluginFileManagerConfig classes
            list of allowed plugin file managers
    """

    return allowed
