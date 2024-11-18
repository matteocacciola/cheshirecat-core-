import pytest

from cat.agents.main_agent import MainAgent
from cat.agents.base_agent import AgentOutput
from cat.utils import default_llm_answer_prompt


def test_main_agent_instantiation(stray):
    assert isinstance(stray.main_agent, MainAgent)
    assert stray.main_agent.verbose in [True, False]


@pytest.mark.asyncio(scope="function")
async def test_execute_main_agent(stray):
    # empty agent execution
    out = await stray.main_agent.execute(stray)
    assert isinstance(out, AgentOutput)
    assert not out.return_direct
    assert out.intermediate_steps == []
    assert out.output == default_llm_answer_prompt()
