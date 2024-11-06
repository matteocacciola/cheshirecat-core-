from typing import List
from abc import ABC, abstractmethod

from cat.utils import BaseModelDict


class AgentInput(BaseModelDict):
    episodic_memory: str
    declarative_memory: str
    tools_output: str
    input: str
    chat_history: str


class AgentOutput(BaseModelDict):
    output: str | None = None
    intermediate_steps: List = []
    return_direct: bool = False


class BaseAgent(ABC):
    @abstractmethod
    async def execute(self, stray, *args, **kwargs) -> AgentOutput:
        """
        Execute the agents.

        Args:
            stray: StrayCat
                Stray Cat instance containing the working memory and the chat history.

        Returns:
            agent_output: AgentOutput
                Reply of the agent, instance of AgentOutput.
        """

        pass

    def __str__(self):
        return self.__class__.__name__

    @property
    def name(self):
        return str(self)
