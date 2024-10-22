from abc import ABC, abstractmethod
from typing import Type, List, Dict, Any
from pydantic import BaseModel

from cat.mad_hatter.mad_hatter import MadHatter


class ReplacedNLPConfig(BaseModel):
    name: str
    value: Dict


class BaseFactory(ABC):
    def __init__(self, mad_hatter: MadHatter):
        self._mad_hatter = mad_hatter

    @abstractmethod
    def get_allowed_classes(self) -> List[Type]:
        pass

    @abstractmethod
    def get_schemas(self) -> Dict:
        pass

    @abstractmethod
    def get_config_class_from_adapter(self, cls: Type) -> Type | None:
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
