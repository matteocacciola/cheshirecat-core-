from typing import Type, Dict
from pydantic import BaseModel, ConfigDict

from cat.db.cruds import settings as crud_settings
from cat.factory.base_factory import BaseFactory
from cat.factory.custom_auth_handler import (
    # ApiKeyAuthHandler,
    BaseAuthHandler,
    CoreOnlyAuthHandler,
)
from cat.log import log


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


    def get_schemas(self) -> Dict:
        auth_handler_schemas = {}
        for config_class in self.get_allowed_classes():
            schema = config_class.model_json_schema()
            schema["authorizatorName"] = schema["title"]
            auth_handler_schemas[schema["title"]] = schema

        return auth_handler_schemas

    def get_config_class_from_adapter(self, cls: Type[BaseAuthHandler]) -> Type[AuthHandlerConfig] | None:
        """Find the class of the auth handler adapter"""

        return next(
            (config_class for config_class in self.get_allowed_classes() if config_class.pyclass() == cls),
            None
        )

    def get_from_config_name(self, agent_id: str, config_name: str) -> BaseAuthHandler:
        # get AuthHandler factory class
        list_auth_handlers = self.get_allowed_classes()
        factory_class = next(
            (auth_handler for auth_handler in list_auth_handlers if auth_handler.__name__ == config_name), None
        )
        if factory_class is None:
            log.warning(f"Auth Handler class {config_name} not found in the list of allowed auth handlers")
            return CoreOnlyAuthConfig.get_auth_handler_from_config({})

        # obtain configuration and instantiate AuthHandler
        selected_auth_handler_config = crud_settings.get_setting_by_name(agent_id, config_name)
        try:
            auth_handler = factory_class.get_auth_handler_from_config(selected_auth_handler_config["value"])
        except Exception:
            import traceback
            traceback.print_exc()

        auth_handler = CoreOnlyAuthConfig.get_auth_handler_from_config({})

        return auth_handler

    @property
    def setting_name(self) -> str:
        return "auth_handler_selected"

    @property
    def setting_category(self) -> str:
        return "auth_handler"

    @property
    def setting_factory_category(self) -> str:
        return "auth_handler_factory"
