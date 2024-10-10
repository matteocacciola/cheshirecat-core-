import pytest
import asyncio

from cat.auth.permissions import AuthUserInfo
from cat.convo.messages import MessageWhy, CatMessage
from cat.looking_glass.stray_cat import StrayCat
from cat.memory.working_memory import WorkingMemory


@pytest.fixture
def stray(client, cheshire_cat_manager) -> StrayCat:
    cheshire_cat = cheshire_cat_manager.get_or_create_cheshire_cat("test")

    yield StrayCat(
        user_data=AuthUserInfo(id="user_alice", name="Alice"),
        main_loop=asyncio.new_event_loop(),
        chatbot_id=cheshire_cat.id
    )


def test_stray_initialization(stray):
    assert isinstance(stray, StrayCat)
    assert stray.user_id == "user_alice"
    assert isinstance(stray.working_memory, WorkingMemory)


def test_stray_nlp(stray):
    res = stray.llm_response("hey")
    assert "You did not configure" in res

    embedding = stray.cheshire_cat.embedder.embed_documents(["hey"])
    assert isinstance(embedding[0], list)
    assert isinstance(embedding[0][0], float)


def test_stray_call(stray):
    msg = {"text": "Where do I go?", "user_id": "Alice"}

    reply = stray.loop.run_until_complete(stray.__call__(msg))

    assert isinstance(reply, CatMessage)
    assert "You did not configure" in reply.content
    assert reply.user_id == "user_alice"
    assert reply.type == "chat"
    assert isinstance(reply.why, MessageWhy)


# TODO: update these tests once we have a real LLM in tests
def test_stray_classify(stray):
    label = stray.classify("I feel good", labels=["positive", "negative"])
    assert label is None  # TODO: should be "positive"

    label = stray.classify(
        "I feel bad", labels={"positive": ["I'm happy"], "negative": ["I'm sad"]}
    )
    assert label is None  # TODO: should be "negative"


def test_recall_to_working_memory(stray):
    # empty working memory / episodic
    assert stray.working_memory.episodic_memories == []

    msg_text = "Where do I go?"
    msg = {"text": msg_text, "user_id": "Alice"}

    # send message
    stray.loop.run_until_complete(stray.__call__(msg))

    # recall after episodic memory was stored
    stray.recall_relevant_memories_to_working_memory(msg_text)

    assert stray.working_memory.recall_query == msg_text
    assert len(stray.working_memory.episodic_memories) == 1
    assert stray.working_memory.episodic_memories[0][0].page_content == msg_text
