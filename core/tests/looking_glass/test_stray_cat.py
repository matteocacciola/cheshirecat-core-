import pytest

from cat.convo.messages import MessageWhy, CatMessage, UserMessage
from cat.looking_glass.stray_cat import StrayCat
from cat.memory.working_memory import WorkingMemory

from tests.utils import api_key, create_mock_plugin_zip


def test_stray_initialization(stray_no_memory):
    assert isinstance(stray_no_memory, StrayCat)
    assert stray_no_memory.user.id == "user_alice"
    assert isinstance(stray_no_memory.working_memory, WorkingMemory)


def test_stray_nlp(stray_no_memory):
    res = stray_no_memory.llm("hey")
    assert "You did not configure" in res

    embedding = stray_no_memory.embedder.embed_documents(["hey"])
    assert isinstance(embedding[0], list)
    assert isinstance(embedding[0][0], float)


def test_stray_call(stray_no_memory):
    msg = {"text": "Where do I go?"}

    reply = stray_no_memory.__call__(UserMessage(**msg))

    assert isinstance(reply, CatMessage)
    assert "You did not configure" in reply.content
    assert reply.type == "chat"
    assert isinstance(reply.why, MessageWhy)


def test_stray_classify(stray_no_memory):
    label = stray_no_memory.classify("I feel good", labels=["positive", "negative"])
    assert label is None

    label = stray_no_memory.classify("I feel bad", labels={"positive": ["I'm happy"], "negative": ["I'm sad"]})
    assert label is None


def test_recall_to_working_memory(stray_no_memory, mocked_default_llm_answer_prompt):
    # empty working memory / episodic
    assert stray_no_memory.working_memory.episodic_memories == []

    msg_text = "Where do I go?"
    msg = {"text": msg_text}

    # send message
    stray_no_memory.__call__(UserMessage(**msg))

    # recall after episodic memory was stored
    stray_no_memory.recall_relevant_memories_to_working_memory(msg_text)

    assert len(stray_no_memory.working_memory.history) == 2
    assert stray_no_memory.working_memory.user_message.text == msg_text
    assert stray_no_memory.working_memory.user_message_json.text == msg_text
    assert stray_no_memory.working_memory.history[0].content.text == msg_text
    assert stray_no_memory.working_memory.history[0].content.text == msg_text
    assert stray_no_memory.working_memory.recall_query == msg_text
    assert len(stray_no_memory.working_memory.episodic_memories) == 1
    assert stray_no_memory.working_memory.episodic_memories[0].document.page_content == msg_text


def test_stray_recall_invalid_collection_name(stray, embedder):
    with pytest.raises(ValueError) as exc_info:
        stray.recall(embedder.embed_query("Hello, I'm Alice"), "invalid_collection")
    assert "invalid_collection is not a valid collection" in str(exc_info.value)


def test_stray_recall_query(stray, embedder, mocked_default_llm_answer_prompt):
    msg_text = "Hello! I'm Alice"
    msg = {"text": msg_text}

    # send message
    stray.__call__(UserMessage(**msg))

    query = embedder.embed_query(msg_text)
    memories = stray.recall(query, "episodic")

    assert len(memories) == 1
    assert memories[0].document.page_content == msg_text
    assert isinstance(memories[0].score, float)
    assert isinstance(memories[0].vector, list)


def test_stray_recall_with_threshold(stray, embedder):
    msg_text = "Hello! I'm Alice"
    msg = {"text": msg_text}

    # send message
    stray.__call__(UserMessage(**msg))

    query = embedder.embed_query("Alice")
    memories = stray.recall(query, "episodic", threshold=1)
    assert len(memories) == 0


def test_stray_recall_all_memories(secure_client, secure_client_headers, stray, embedder):
    expected_chunks = 4
    content_type = "application/pdf"
    file_name = "sample.pdf"
    file_path = f"tests/mocks/{file_name}"
    with open(file_path, "rb") as f:
        files = {"file": (file_name, f, content_type)}
        _ = secure_client.post("/rabbithole/", files=files, headers=secure_client_headers)

    query = embedder.embed_query("")
    memories = stray.recall(query, "declarative", k=None)

    assert len(memories) == expected_chunks


def test_stray_recall_override_working_memory(stray, embedder, mocked_default_llm_answer_prompt):
    # empty working memory / episodic
    assert stray.working_memory.episodic_memories == []

    msg_text = "Hello! I'm Alice"
    msg = {"text": msg_text}

    # send message
    stray.__call__(UserMessage(**msg))

    query = embedder.embed_query("Alice")
    memories = stray.recall(query, "episodic")

    assert stray.working_memory.episodic_memories == memories
    assert len(stray.working_memory.episodic_memories) == 1
    assert stray.working_memory.episodic_memories[0].document.page_content == msg_text


def test_stray_recall_by_metadata(secure_client, secure_client_headers, stray, embedder):
    expected_chunks = 4
    content_type = "application/pdf"

    file_name = "sample.pdf"
    file_path = f"tests/mocks/{file_name}"
    with open(file_path, "rb") as f:
        files = {"file": (file_name, f, content_type)}
        _ = secure_client.post("/rabbithole/", files=files, headers=secure_client_headers)

    with open(file_path, "rb") as f:
        files = {"file": ("sample2.pdf", f, content_type)}
        _ = secure_client.post("/rabbithole/", files=files, headers=secure_client_headers)

    query = embedder.embed_query("late")
    memories = stray.recall(query, "declarative", metadata={"source": file_name})
    assert len(memories) == expected_chunks
    for mem in memories:
        assert mem.document.metadata["source"] == file_name


def test_stray_fast_reply_hook(secure_client, secure_client_headers, stray):
    ccat = stray.cheshire_cat
    ccat_headers = {"agent_id": ccat.id, "Authorization": f"Bearer {api_key}"}

    # manually install the plugin
    zip_path = create_mock_plugin_zip(flat=True, plugin_id="mock_plugin_fast_reply")
    zip_file_name = zip_path.split("/")[-1]  # mock_plugin.zip in tests/mocks folder
    with open(zip_path, "rb") as f:
        secure_client.post(
            "/admins/plugins/upload/",
            files={"file": (zip_file_name, f, "application/zip")},
            headers=secure_client_headers
        )

    # activate for the new agent
    secure_client.put("/plugins/toggle/mock_plugin_fast_reply", headers=ccat_headers)

    msg = {"text": "hello", "user_id": stray.user.id, "agent_id": stray.agent_id}

    # send message
    res = stray.__call__(msg)

    assert isinstance(res, CatMessage)
    assert res.text == "This is a fast reply"

    # there should be NO side effects
    assert stray.working_memory.user_message.text == "hello"
    assert len(stray.working_memory.history) == 0
    stray.recall_relevant_memories_to_working_memory("hello")
    assert len(stray.working_memory.episodic_memories) == 0
