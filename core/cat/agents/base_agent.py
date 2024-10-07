from typing import List
from abc import ABC, abstractmethod

from cat.looking_glass.stray_cat import StrayCat
from cat.utils import BaseModelDict


class AgentOutput(BaseModelDict):
    output: str | None = None
    intermediate_steps: List = []
    return_direct: bool = False


class BaseAgent(ABC):
    @abstractmethod
    async def execute(self, stray: StrayCat, *args, **kwargs) -> AgentOutput:
        pass