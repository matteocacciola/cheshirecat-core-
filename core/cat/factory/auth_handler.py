from typing import Type, Dict
from pydantic import BaseModel, ConfigDict

from cat.factory.custom_auth_handler import (
    # ApiKeyAuthHandler,
    BaseAuthHandler,
    CoreOnlyAuthHandler,
)
from cat.mad_hatter.mad_hatter import MadHatter


class AuthHandlerConfig(BaseModel):
    _pyclass: Type[BaseAuthHandler] = None

    @classmethod
    def get_auth_handler_from_config(cls, config) -> BaseAuthHandler:
        if cls._pyclass and issubclass(cls._pyclass.default, BaseAuthHandler):
            return cls._pyclass.default(**config)
        raise Exception("AuthHandler configuration class is invalid. It should be a valid BaseAuthHandler class")

    @classmethod
    def pyclass(cls) -> Type[BaseAuthHandler]:
        return cls._pyclass.default


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


def get_allowed_auth_handler_strategies(mad_hatter: MadHatter) -> list[Type[AuthHandlerConfig]]:
    list_auth_handler_default = [
        CoreOnlyAuthConfig,
        # ApiKeyAuthConfig,
    ]

    list_auth_handler = mad_hatter.execute_hook(
        "factory_allowed_auth_handlers", list_auth_handler_default, cat=None
    )

    return list_auth_handler


def get_auth_handlers_schemas(mad_hatter: MadHatter) -> Dict:
    auth_handler_schemas = {}
    for config_class in get_allowed_auth_handler_strategies(mad_hatter):
        schema = config_class.model_json_schema()
        schema["authorizatorName"] = schema["title"]
        auth_handler_schemas[schema["title"]] = schema

    return auth_handler_schemas


def get_auth_handler_factory_from_config_name(name: str, mad_hatter: MadHatter) -> Type[AuthHandlerConfig] | None:
    list_auth_handler = get_allowed_auth_handler_strategies(mad_hatter)
    for auth_handler in list_auth_handler:
        if auth_handler.__name__ == name:
            return auth_handler
    return None


def get_auth_handler_config_class_from_strategy(cls: Type[BaseAuthHandler], mad_hatter: MadHatter) -> str | None:
    """Find the class name of the auth handler strategy"""
    for config_class in get_allowed_auth_handler_strategies(mad_hatter):
        if config_class.pyclass() == cls:
            return config_class.__name__
    return None
