from cat.convo.messages import MessageWhy, CatMessage
from cat.looking_glass.stray_cat import StrayCat
from cat.memory.working_memory import WorkingMemory


def test_stray_initialization(stray_no_memory):
    assert isinstance(stray_no_memory, StrayCat)
    assert stray_no_memory.user_id == "user_alice"
    assert isinstance(stray_no_memory.working_memory, WorkingMemory)


def test_stray_nlp(stray_no_memory):
    res = stray_no_memory.llm_response("hey")
    assert "You did not configure" in res

    embedding = stray_no_memory.embedder.embed_documents(["hey"])
    assert isinstance(embedding[0], list)
    assert isinstance(embedding[0][0], float)


def test_stray_call(stray_no_memory):
    msg = {"text": "Where do I go?", "user_id": "Alice"}

    reply = stray_no_memory.loop.run_until_complete(stray_no_memory.__call__(msg))

    assert isinstance(reply, CatMessage)
    assert "You did not configure" in reply.content
    assert reply.user_id == "user_alice"
    assert reply.type == "chat"
    assert isinstance(reply.why, MessageWhy)


# TODO: update these tests once we have a real LLM in tests
def test_stray_classify(stray_no_memory):
    label = stray_no_memory.classify("I feel good", labels=["positive", "negative"])
    assert label is None  # TODO: should be "positive"

    label = stray_no_memory.classify(
        "I feel bad", labels={"positive": ["I'm happy"], "negative": ["I'm sad"]}
    )
    assert label is None  # TODO: should be "negative"


def test_recall_to_working_memory(stray_no_memory):
    # empty working memory / episodic
    assert stray_no_memory.working_memory.episodic_memories == []

    msg_text = "Where do I go?"
    msg = {"text": msg_text, "user_id": "Alice"}

    # send message
    stray_no_memory.loop.run_until_complete(stray_no_memory.__call__(msg))

    # recall after episodic memory was stored
    stray_no_memory.recall_relevant_memories_to_working_memory(msg_text)

    assert stray_no_memory.working_memory.recall_query == msg_text
    assert len(stray_no_memory.working_memory.episodic_memories) == 1
    assert stray_no_memory.working_memory.episodic_memories[0][0].page_content == msg_text
