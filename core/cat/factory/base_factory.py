from abc import ABC, abstractmethod
from typing import Type, List, Dict, Any
from pydantic import BaseModel

from cat.log import log
from cat.mad_hatter.march_hare import MarchHare
from cat.db.cruds import settings as crud_settings


class ReplacedNLPConfig(BaseModel):
    name: str
    value: Dict


class BaseConfigModel(ABC, BaseModel):
    _pyclass: Type = None

    @classmethod
    def get_from_config(cls, config) -> Type:
        if cls._pyclass and issubclass(cls.pyclass(), cls.base_class()):
            return cls.pyclass()(**config)
        raise Exception(f"Configuration class is invalid. It should be a valid {cls.base_class().__name__} class")

    @classmethod
    def pyclass(cls) -> Type:
        return cls._pyclass.default

    @classmethod
    @abstractmethod
    def base_class(cls) -> Type:
        pass


class BaseFactory(ABC):
    def __init__(self, march_hare: MarchHare):
        self._mad_hatter = march_hare

    def get_config_class_from_adapter(self, cls: Type) -> Type[BaseModel] | None:
        return next(
            (config_class for config_class in self.get_allowed_classes() if config_class.pyclass() == cls),
            None
        )

    def get_schemas(self) -> Dict:
        # schemas contains metadata to let any client know which fields are required to create the class.
        schemas = {}
        for config_class in self.get_allowed_classes():
            schema = config_class.model_json_schema()
            # useful for clients in order to call the correct config endpoints
            schema[self.schema_name] = schema["title"]
            schemas[schema["title"]] = schema

        return schemas

    def _get_factory_class(self, config_name: str) -> Type[BaseModel] | None:
        return next((cls for cls in self.get_allowed_classes() if cls.__name__ == config_name), None)

    def _get_from_config_name(self, agent_id: str, config_name: str) -> Any:
        # get plugin file manager factory class
        factory_class = next((cls for cls in self.get_allowed_classes() if cls.__name__ == config_name), None)
        if not factory_class:
            log.warning(f"Class {config_name} not found in the list of allowed classes for setting {self.setting_name}")
            return self.default_config_class.get_filemanager_from_config(self.default_config)

        # obtain configuration and instantiate the file manager
        selected_file_manager_config = crud_settings.get_setting_by_name(agent_id, config_name)
        try:
            file_manager = factory_class.get_filemanager_from_config(selected_file_manager_config["value"])
        except Exception:
            import traceback
            traceback.print_exc()

            file_manager = self.default_config_class.get_from_config(self.default_config)

        return file_manager

    @abstractmethod
    def get_allowed_classes(self) -> List[Type[BaseModel]]:
        pass

    @abstractmethod
    def get_from_config_name(self, agent_id: str, config_name: str) -> Any:
        pass

    @property
    @abstractmethod
    def setting_name(self) -> str:
        pass

    @property
    @abstractmethod
    def setting_category(self) -> str:
        pass

    @property
    @abstractmethod
    def setting_factory_category(self) -> str:
        pass

    @property
    @abstractmethod
    def default_config_class(self) -> Type[BaseModel]:
        pass

    @property
    @abstractmethod
    def default_config(self) -> Dict:
        pass

    @property
    @abstractmethod
    def schema_name(self) -> str:
        pass