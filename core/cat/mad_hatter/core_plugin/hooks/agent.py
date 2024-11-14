"""Hooks to modify the Cat's *Agent*.

Here is a collection of methods to hook into the *Agent* execution pipeline.

"""

from typing import List, Dict
from cat.agents import AgentOutput

from cat.mad_hatter.decorators import hook


@hook(priority=0)
def before_agent_starts(agent_input: Dict, cat) -> Dict:
    """
    Hook to read and edit the agent input

    Args:
        agent_input: Dict
            Input that is about to be passed to the agent.
        cat: StrayCat
            Stray Cat instance.

    Returns:
        Agent Input as Dictionary
    """

    return agent_input


@hook(priority=0)
def agent_fast_reply(ag_fast_reply: Dict, cat) -> Dict | None:
    """
    This hook allows for a custom response after memory recall, skipping default agent execution.
    It's useful for custom agent logic or when you want to use recalled memories but avoid the main agent.

    Args:
        ag_fast_reply: Dict
            Input is a dictionary (initially empty), which can be enriched with an "output" key with the shortcut
            response.
        cat: StrayCat
            Stray Cat instance.

    Returns:
        response: Dict | None
            If you want to bypass the main agent, return a Dict with a valid `output` key.
            Return None or an empty Dict or a Dict without a valid `output` key to continue with normal execution.
            See below for examples of Cat response

    Examples
    --------

    Example 1: don't remember (no uploaded documents about topic)
    ```python
    num_declarative_memories = len( cat.working_memory.declarative_memories )
    if num_declarative_memories == 0:
        return {
           "output": "Sorry, I have no memories about that."
        }
    ```
    """

    return ag_fast_reply


@hook(priority=0)
def agent_allowed_tools(allowed_tools: List[str], cat) -> List[str]:
    """
    Hook the allowed tools.

    Allows to decide which tools end up in the *Agent* prompt.

    To decide, you can filter the list of tools' names, but you can also check the context in `cat.working_memory`
    and launch custom chains with `cat.llm`.

    Args:
        allowed_tools: List[str]
            List of tools that are allowed to be used by the *
        cat: StrayCat
            Stray Cat instance.

    Returns:
        tools: List[str]
            List of allowed Langchain tools.
    """

    return allowed_tools
