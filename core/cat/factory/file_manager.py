from abc import ABC
from typing import Type, List, Dict
from pydantic import ConfigDict

from cat.factory.base_factory import BaseFactory, BaseFactoryConfigModel
from cat.factory.custom_file_manager import (
    LocalFileManager,
    BaseFileManager,
    AWSFileManager,
    AzureFileManager,
    GoogleCloudFileManager,
    DigitalOceanFileManager,
)


class FileManagerConfig(BaseFactoryConfigModel, ABC):
    # class instantiating the file manager
    _pyclass: Type[BaseFileManager] = None

    @classmethod
    def base_class(cls) -> Type:
        return BaseFileManager


class LocalFileManagerConfig(FileManagerConfig):
    _pyclass: Type = LocalFileManager

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Local API File Manager",
            "description": "Configuration for File Manager to be used to locally move files and directories",
            "link": "",
        }
    )


class AWSFileManagerConfig(FileManagerConfig):
    bucket_name: str
    aws_access_key: str
    aws_secret_key: str

    _pyclass: Type = AWSFileManager

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "AWS API File Manager",
            "description": "Configuration for File Manager to be used with AWS S3 service",
            "link": "",
        }
    )


class AzureFileManagerConfig(FileManagerConfig):
    connection_string: str
    container_name: str

    _pyclass: Type = AzureFileManager

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Azure API File Manager",
            "description": "Configuration for File Manager to be used with Azure Blob service",
            "link": "",
        }
    )


class GoogleFileManagerConfig(FileManagerConfig):
    bucket_name: str
    credentials_path: str

    _pyclass: Type = GoogleCloudFileManager

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Google Cloud API File Manager",
            "description": "Configuration for File Manager to be used with Google Cloud storage service",
            "link": "",
        }
    )


class DigitalOceanFileManagerConfig(AWSFileManagerConfig):
    _pyclass: Type = DigitalOceanFileManager

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Digital Ocean API File Manager",
            "description": "Configuration for File Manager to be used with Digital Ocean Spaces service",
            "link": "",
        }
    )


class FileManagerFactory(BaseFactory):
    def get_allowed_classes(self) -> List[Type[FileManagerConfig]]:
        list_file_managers_default = [
            LocalFileManagerConfig,
            AWSFileManagerConfig,
            AzureFileManagerConfig,
            GoogleFileManagerConfig,
            DigitalOceanFileManagerConfig,
        ]

        list_file_managers_default = self._hook_manager.execute_hook(
            "factory_allowed_file_managers", list_file_managers_default, cat=None
        )
        return list_file_managers_default

    def get_from_config_name(self, agent_id: str, config_name: str) -> BaseFileManager:
        """
        Get the file manager from the configuration name.

        Args:
            agent_id: The agent key
            config_name: The configuration name

        Returns:
            BaseFileManager: The file manager instance
        """

        return self._get_from_config_name(agent_id, config_name)

    @property
    def setting_name(self) -> str:
        return "file_manager_selected"

    @property
    def setting_category(self) -> str:
        return "file_manager"

    @property
    def setting_factory_category(self) -> str:
        return "file_manager_factory"

    @property
    def default_config_class(self) -> Type[BaseFactoryConfigModel]:
        return LocalFileManagerConfig

    @property
    def default_config(self) -> Dict:
        return {}

    @property
    def schema_name(self) -> str:
        return "fileManagerName"
