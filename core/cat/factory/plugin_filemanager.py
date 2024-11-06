from abc import ABC
from typing import Type, List, Dict
from pydantic import ConfigDict

from cat.factory.base_factory import BaseFactory, BaseFactoryConfigModel
from cat.factory.custom_filemanager import (
    LocalFileManager,
    BaseFileManager,
    AWSFileManager,
    AzureFileManager,
    GoogleCloudFileManager,
    DigitalOceanFileManager,
)
import cat.utils as utils


class PluginFileManagerConfig(BaseFactoryConfigModel, ABC):
    storage_dir: str = "plugins"

    # class instantiating the plugin file manager
    _pyclass: Type[BaseFileManager] = None

    @classmethod
    def base_class(cls) -> Type:
        return BaseFileManager


class LocalPluginFileManagerConfig(PluginFileManagerConfig):
    storage_dir: str = utils.get_plugins_path()

    _pyclass: Type = LocalFileManager

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Local API Plugin File Manager",
            "description": "Configuration for Plugin File Manager to be used to locally move files and directories",
            "link": "",
        }
    )


class AWSPluginFileManagerConfig(PluginFileManagerConfig):
    bucket_name: str
    aws_access_key: str
    aws_secret_key: str

    _pyclass: Type = AWSFileManager

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "AWS API Plugin File Manager",
            "description": "Configuration for Plugin File Manager to be used with AWS S3 service",
            "link": "",
        }
    )


class AzurePluginFileManagerConfig(PluginFileManagerConfig):
    connection_string: str
    container_name: str

    _pyclass: Type = AzureFileManager

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Azure API Plugin File Manager",
            "description": "Configuration for Plugin File Manager to be used with Azure Blob service",
            "link": "",
        }
    )


class GoogleCloudPluginFileManagerConfig(PluginFileManagerConfig):
    bucket_name: str
    credentials_path: str

    _pyclass: Type = GoogleCloudFileManager

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Google Cloud API Plugin File Manager",
            "description": "Configuration for Plugin File Manager to be used with Google Cloud storage service",
            "link": "",
        }
    )


class DigitalOceanPluginFileManagerConfig(AWSPluginFileManagerConfig):
    _pyclass: Type = DigitalOceanFileManager

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Digital Ocean API Plugin File Manager",
            "description": "Configuration for Plugin File Manager to be used with Digital Ocean Spaces service",
            "link": "",
        }
    )


class PluginFileManagerFactory(BaseFactory):
    def get_allowed_classes(self) -> List[Type[PluginFileManagerConfig]]:
        list_file_managers_default = [
            LocalPluginFileManagerConfig,
            AWSPluginFileManagerConfig,
            AzurePluginFileManagerConfig,
            GoogleCloudPluginFileManagerConfig,
            DigitalOceanPluginFileManagerConfig,
        ]

        list_file_managers_default = self._hook_manager.execute_hook(
            "factory_allowed_plugin_file_managers", list_file_managers_default, cat=None
        )
        return list_file_managers_default

    def get_from_config_name(self, agent_id: str, config_name: str) -> BaseFileManager:
        """
        Get the plugin file manager from the configuration name.

        Args:
            agent_id: The agent key
            config_name: The configuration name

        Returns:
            BaseFileManager: The plugin file manager instance
        """

        return self._get_from_config_name(agent_id, config_name)

    @property
    def setting_name(self) -> str:
        return "plugin_filemanager_selected"

    @property
    def setting_category(self) -> str:
        return "plugin_filemanager"

    @property
    def setting_factory_category(self) -> str:
        return "plugin_filemanager_factory"

    @property
    def default_config_class(self) -> Type[BaseFactoryConfigModel]:
        return LocalPluginFileManagerConfig

    @property
    def default_config(self) -> Dict:
        return {"storage_dir": utils.get_plugins_path()}

    @property
    def schema_name(self) -> str:
        return "pluginFileManagerName"
