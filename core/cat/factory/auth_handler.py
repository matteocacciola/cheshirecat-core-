from typing import Type
from pydantic import BaseModel, ConfigDict

from cat.looking_glass.cheshire_cat_manager import CheshireCatManager
from cat.factory.custom_auth_handler import (
    # ApiKeyAuthHandler,
    BaseAuthHandler,
    CoreOnlyAuthHandler,
)


class AuthHandlerConfig(BaseModel):
    _pyclass: Type[BaseAuthHandler] = None

    @classmethod
    def get_auth_handler_from_config(cls, config):
        if (
            cls._pyclass is None
            or issubclass(cls._pyclass.default, BaseAuthHandler) is False
        ):
            raise Exception(
                "AuthHandler configuration class has self._pyclass==None. Should be a valid AuthHandler class"
            )
        return cls._pyclass.default(**config)


class CoreOnlyAuthConfig(AuthHandlerConfig):
    _pyclass: Type = CoreOnlyAuthHandler

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Standalone Core Auth Handler",
            "description": "Delegate auth to Cat core, without any additional auth systems. "
            "Do not change this if you don't know what you are doing!",
            "link": "",  # TODO link to auth docs
        }
    )


# TODOAUTH: have at least another auth_handler class to test
# class ApiKeyAuthConfig(AuthHandlerConfig):
#     _pyclass: Type = ApiKeyAuthHandler

#     model_config = ConfigDict(
#         json_schema_extra={
#             "humanReadableName": "Api Key Auth Handler",
#             "description": "Yeeeeah.",
#             "link": "",
#         }
#     )


def get_allowed_auth_handler_strategies(chatbot_id: str):
    list_auth_handler_default = [
        CoreOnlyAuthConfig,
        # ApiKeyAuthConfig,
    ]

    mad_hatter_instance = CheshireCatManager().get_cheshire_cat(chatbot_id).mad_hatter
    list_auth_handler = mad_hatter_instance.execute_hook(
        "factory_allowed_auth_handlers", list_auth_handler_default, cat=None
    )

    return list_auth_handler


def get_auth_handlers_schemas(chatbot_id: str):
    auth_handler_schemas = {}
    for config_class in get_allowed_auth_handler_strategies(chatbot_id):
        schema = config_class.model_json_schema()
        schema["authorizatorName"] = schema["title"]
        auth_handler_schemas[schema["title"]] = schema

    return auth_handler_schemas


def get_auth_handler_from_name(name: str, chatbot_id: str):
    list_auth_handler = get_allowed_auth_handler_strategies(chatbot_id)
    for auth_handler in list_auth_handler:
        if auth_handler.__name__ == name:
            return auth_handler
    return None
