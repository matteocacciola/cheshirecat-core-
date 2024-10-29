from abc import ABC, abstractmethod
from typing import Type, List, Dict, Any
from pydantic import BaseModel

from cat.mad_hatter.march_hare import MarchHare


class ReplacedNLPConfig(BaseModel):
    name: str
    value: Dict


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
    def schema_name(self) -> str:
        pass