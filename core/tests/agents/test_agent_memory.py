import time
from langchain.docstore.document import Document

from cat.memory.vector_memory_collection import DocumentRecall


def test_format_agent_input_on_empty_memory(stray):
    # empty memory
    agent_input = stray.main_agent.format_agent_input(stray)
    assert agent_input["input"] == "meow"
    assert agent_input["episodic_memory"] == ""
    assert agent_input["declarative_memory"] == ""
    assert agent_input["tools_output"] == ""


def test_format_agent_input(stray):
    # episodic and declarative memories are present
    stray = fill_working_memory(stray)

    agent_input = stray.main_agent.format_agent_input(stray)
    assert agent_input["input"] == "meow"
    assert (
        agent_input["episodic_memory"]
        == """## Context of things the Human said in the past: 
  - A (0 minutes ago)
  - B (1 days ago)"""
    )
    assert (
        agent_input["declarative_memory"]
        == """## Context of documents containing relevant information: 
  - A (extracted from a.pdf)
  - B (extracted from http://b)"""
    )
    assert agent_input["tools_output"] == ""


def test_agent_prompt_episodic_memories(stray):
    # empty episodic memory
    episodic_prompt = stray.main_agent.agent_prompt_episodic_memories([])
    assert episodic_prompt == ""

    # some points in episodic memory
    stray = fill_working_memory(stray)

    episodic_prompt = stray.main_agent.agent_prompt_episodic_memories(
        stray.working_memory.episodic_memories
    )
    assert (
        episodic_prompt
        == """## Context of things the Human said in the past: 
  - A (0 minutes ago)
  - B (1 days ago)"""
    )


def test_agent_prompt_declarative_memories(stray):
    # empty declarative memory
    declarative_prompt = stray.main_agent.agent_prompt_declarative_memories([])
    assert declarative_prompt == ""

    # some points in declarative memory
    stray = fill_working_memory(stray)
    declarative_prompt = stray.main_agent.agent_prompt_declarative_memories(
        stray.working_memory.declarative_memories
    )
    assert (
        declarative_prompt
        == """## Context of documents containing relevant information: 
  - A (extracted from a.pdf)
  - B (extracted from http://b)"""
    )

# utility to add content to the working memory
def fill_working_memory(stray_cat):
    stray_cat.working_memory.episodic_memories = [
        DocumentRecall(
            document=Document(
                page_content="A",
                metadata={
                    "when": time.time(),
                },
            ),
            score=0.99,
        ),
        DocumentRecall(
            document=Document(
                page_content="B",
                metadata={
                    "when": time.time() - (60 * 60 * 24),
                },
            ),
            score=0.88
        ),
    ]

    stray_cat.working_memory.declarative_memories = [
        DocumentRecall(
            document=Document(
                page_content="A",
                metadata={
                    "source": "a.pdf",
                },
            ),
            score=0.99
        ),
        DocumentRecall(
            document=Document(
                page_content="B",
                metadata={
                    "source": "http://b",
                },
            ),
            score=0.88
        ),
    ]

    stray_cat.working_memory.procedural_memories = [
        DocumentRecall(
            document=Document(
                page_content="what time is it",
                metadata={
                    "source": "TODO",
                },
            ),
            score=0.99,
        )
    ]

    return stray_cat
