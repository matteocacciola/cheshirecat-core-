from typing import Type, Dict, List
from pydantic import BaseModel, ConfigDict

from cat.db.cruds import settings as crud_settings
from cat.factory.base_factory import BaseFactory
from cat.factory.custom_uploader import (
    LocalUploader,
    BaseUploader,
    AWSUploader,
    AzureUploader,
    GoogleCloudUploader,
)
from cat.log import log


class UploaderConfig(BaseModel):
    destination_path: str

    # class instantiating the plugin uploader
    _pyclass: Type[BaseUploader] = None

    @classmethod
    def get_uploader_from_config(cls, config) -> BaseUploader:
        if cls._pyclass and issubclass(cls._pyclass.default, BaseUploader):
            config_copy = config.copy()
            del config_copy["destination_path"]
            return cls._pyclass.default(**config_copy)
        raise Exception("PluginUploader configuration class is invalid. It should be a valid BaseUploader class")

    @classmethod
    def pyclass(cls) -> Type[BaseUploader]:
        return cls._pyclass.default


class LocalUploaderConfig(UploaderConfig):
    _pyclass = LocalUploader

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Local API  Uploader",
            "description": "Configuration for Uploader to be used to locally move files and directories",
            "link": "",
        }
    )


class AWSUploaderConfig(UploaderConfig):
    bucket_name: str
    aws_access_key: str
    aws_secret_key: str

    _pyclass: Type = AWSUploader

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "AWS API Uploader",
            "description": "Configuration for Uploader to be used with AWS S3 service",
            "link": "",
        }
    )


class AzureUploaderConfig(UploaderConfig):
    connection_string: str
    container_name: str

    _pyclass: Type = AzureUploader

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Azure API Uploader",
            "description": "Configuration for Uploader to be used with Azure Blob service",
            "link": "",
        }
    )


class GoogleCloudUploaderConfig(UploaderConfig):
    bucket_name: str
    credentials_path: str

    _pyclass: Type = GoogleCloudUploader

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Google Cloud API Uploader",
            "description": "Configuration for Uploader to be used with Google Cloud storage service",
            "link": "",
        }
    )


class UploaderFactory(BaseFactory):
    def get_allowed_classes(self) -> List[Type[UploaderConfig]]:
        list_uploaders_default = [
            LocalUploaderConfig,
            AWSUploaderConfig,
            AzureUploaderConfig,
            GoogleCloudUploaderConfig,
        ]

        list_uploaders_default = self._mad_hatter.execute_hook(
            "factory_allowed_uploaders", list_uploaders_default, cat=None
        )
        return list_uploaders_default

    def get_schemas(self) -> Dict:
        # llm_schemas contains metadata to let any client know
        # which fields are required to create the language model.
        uploaders_schemas = {}
        for config_class in self.get_allowed_classes():
            schema = config_class.model_json_schema()
            # useful for clients in order to call the correct config endpoints
            schema["languageModelName"] = schema["title"]
            uploaders_schemas[schema["title"]] = schema

        return uploaders_schemas

    def get_config_class_from_adapter(self, cls: Type[BaseUploader]) -> Type[UploaderConfig] | None:
        """Find the class of the llm adapter"""

        return next(
            (config_class for config_class in self.get_allowed_classes() if config_class.pyclass() == cls),
            None
        )

    def get_from_config_name(self, agent_id: str, config_name: str) -> BaseUploader:
        """
        Get the language model from the configuration name.

        Args:
            agent_id: The agent key
            config_name: The configuration name

        Returns:
            BaseUploader: The plugin uploader instance
        """

        # get Uploader factory class
        list_uploaders = self.get_allowed_classes()
        factory_class = next((cls for cls in list_uploaders if cls.__name__ == config_name), None)
        if not factory_class:
            log.warning(f"Uploader class {config_name} not found in the list of allowed Uploaders")
            return LocalUploaderConfig.get_uploader_from_config({})

        # obtain configuration and instantiate the uploader
        selected_uploader_config = crud_settings.get_setting_by_name(agent_id, config_name)
        try:
            uploader = factory_class.get_uploader_from_config(selected_uploader_config["value"])
        except Exception:
            import traceback
            traceback.print_exc()

            uploader = LocalUploaderConfig.get_uploader_from_config({})

        return uploader

    @property
    def setting_name(self) -> str:
        return "uploader_selected"

    @property
    def setting_category(self) -> str:
        return "uploader"

    @property
    def setting_factory_category(self) -> str:
        return "uploader_factory"
