from typing import Type, List
from pydantic import BaseModel, ConfigDict

from cat.db.cruds import settings as crud_settings
from cat.factory.base_factory import BaseFactory
from cat.factory.custom_uploader import (
    LocalUploader,
    BaseUploader,
    AWSUploader,
    AzureUploader,
    GoogleCloudUploader,
    DigitalOceanUploader,
)
from cat.log import log
import cat.utils as utils


class PluginUploaderConfig(BaseModel):
    storage_dir: str = "plugins"

    # class instantiating the plugin uploader
    _pyclass: Type[BaseUploader] = None

    @classmethod
    def get_uploader_from_config(cls, config) -> BaseUploader:
        if cls._pyclass and issubclass(cls._pyclass.default, BaseUploader):
            return cls._pyclass.default(**config)
        raise Exception("Uploader configuration class is invalid. It should be a valid BaseUploader class")

    @classmethod
    def pyclass(cls) -> Type[BaseUploader]:
        return cls._pyclass.default


class LocalPluginUploaderConfig(PluginUploaderConfig):
    storage_dir: str = utils.get_plugins_path()

    _pyclass: Type = LocalUploader

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Local API Plugin Uploader",
            "description": "Configuration for Plugin Uploader to be used to locally move files and directories",
            "link": "",
        }
    )


class AWSPluginUploaderConfig(PluginUploaderConfig):
    bucket_name: str
    aws_access_key: str
    aws_secret_key: str

    _pyclass: Type = AWSUploader

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "AWS API Plugin Uploader",
            "description": "Configuration for Plugin Uploader to be used with AWS S3 service",
            "link": "",
        }
    )


class AzurePluginUploaderConfig(PluginUploaderConfig):
    connection_string: str
    container_name: str

    _pyclass: Type = AzureUploader

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Azure API Plugin Uploader",
            "description": "Configuration for Plugin Uploader to be used with Azure Blob service",
            "link": "",
        }
    )


class GoogleCloudPluginUploaderConfig(PluginUploaderConfig):
    bucket_name: str
    credentials_path: str

    _pyclass: Type = GoogleCloudUploader

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Google Cloud API Plugin Uploader",
            "description": "Configuration for Plugin Uploader to be used with Google Cloud storage service",
            "link": "",
        }
    )


class DigitalOceanPluginUploaderConfig(AWSPluginUploaderConfig):
    _pyclass: Type = DigitalOceanUploader

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Digital Ocean API Plugin Uploader",
            "description": "Configuration for Plugin Uploader to be used with Digital Ocean Spaces service",
            "link": "",
        }
    )


class PluginUploaderFactory(BaseFactory):
    def get_allowed_classes(self) -> List[Type[PluginUploaderConfig]]:
        list_uploaders_default = [
            LocalPluginUploaderConfig,
            AWSPluginUploaderConfig,
            AzurePluginUploaderConfig,
            GoogleCloudPluginUploaderConfig,
            DigitalOceanPluginUploaderConfig,
        ]

        list_uploaders_default = self._mad_hatter.execute_hook(
            "factory_allowed_plugin_uploaders", list_uploaders_default, cat=None
        )
        return list_uploaders_default

    def get_from_config_name(self, agent_id: str, config_name: str) -> BaseUploader:
        """
        Get the plugin uploader from the configuration name.

        Args:
            agent_id: The agent key
            config_name: The configuration name

        Returns:
            BaseUploader: The plugin uploader instance
        """

        # get plugin uploader factory class
        factory_class = next((cls for cls in self.get_allowed_classes() if cls.__name__ == config_name), None)
        if not factory_class:
            log.warning(f"Uploader class {config_name} not found in the list of allowed Uploaders")
            return LocalPluginUploaderConfig.get_uploader_from_config({"storage_dir": utils.get_plugins_path()})

        # obtain configuration and instantiate the uploader
        selected_uploader_config = crud_settings.get_setting_by_name(agent_id, config_name)
        try:
            uploader = factory_class.get_uploader_from_config(selected_uploader_config["value"])
        except Exception:
            import traceback
            traceback.print_exc()

            uploader = LocalPluginUploaderConfig.get_uploader_from_config({"storage_dir": utils.get_plugins_path()})

        return uploader

    @property
    def setting_name(self) -> str:
        return "plugin_uploader_selected"

    @property
    def setting_category(self) -> str:
        return "plugin_uploader"

    @property
    def setting_factory_category(self) -> str:
        return "plugin_uploader_factory"

    @property
    def schema_name(self) -> str:
        return "pluginUploaderName"
