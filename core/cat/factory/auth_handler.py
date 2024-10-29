from abc import ABC
from typing import Type, Dict
from pydantic import BaseModel, ConfigDict

from cat.factory.base_factory import BaseFactory, BaseConfigModel
from cat.factory.custom_auth_handler import (
    # ApiKeyAuthHandler,
    BaseAuthHandler,
    CoreOnlyAuthHandler,
)


class AuthHandlerConfig(BaseConfigModel, ABC):
    _pyclass: Type[BaseAuthHandler] = None

    @classmethod
    def base_class(cls) -> Type:
        return BaseAuthHandler


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


# TODO AUTH: have at least another auth_handler class to test
# class ApiKeyAuthConfig(AuthHandlerConfig):
#     _pyclass: Type = ApiKeyAuthHandler

#     model_config = ConfigDict(
#         json_schema_extra={
#             "humanReadableName": "Api Key Auth Handler",
#             "description": "Yeeeeah.",
#             "link": "",
#         }
#     )


class AuthHandlerFactory(BaseFactory):
    def get_allowed_classes(self) -> list[Type[AuthHandlerConfig]]:
        list_auth_handler_default = [
            CoreOnlyAuthConfig,
            # ApiKeyAuthConfig,
        ]

        list_auth_handler = self._mad_hatter.execute_hook(
            "factory_allowed_auth_handlers", list_auth_handler_default, cat=None
        )

        return list_auth_handler

    def get_from_config_name(self, agent_id: str, config_name: str) -> BaseAuthHandler:
        return self._get_from_config_name(agent_id, config_name)

    @property
    def setting_name(self) -> str:
        return "auth_handler_selected"

    @property
    def setting_category(self) -> str:
        return "auth_handler"

    @property
    def setting_factory_category(self) -> str:
        return "auth_handler_factory"

    @property
    def default_config_class(self) -> Type[BaseModel]:
        return CoreOnlyAuthConfig

    @property
    def default_config(self) -> Dict:
        return {}

    @property
    def schema_name(self) -> str:
        return "authorizatorName"
