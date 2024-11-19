from cat.db.cruds import users as crud_users

from tests.utils import send_n_websocket_messages, agent_id


# search on default startup memory
def test_memory_recall_default_success(secure_client, secure_client_headers):
    params = {"text": "Red Queen"}
    response = secure_client.get("/memory/recall/", params=params, headers=secure_client_headers)
    json = response.json()
    assert response.status_code == 200

    # query was received and embedded
    assert json["query"]["text"] == params["text"]
    assert isinstance(json["query"]["vector"], list)
    assert isinstance(json["query"]["vector"][0], float)

    # results are grouped by collection
    assert len(json["vectors"]["collections"]) == 3
    assert {"episodic", "declarative", "procedural"} == set(
        json["vectors"]["collections"].keys()
    )

    # initial collections contents
    for collection in json["vectors"]["collections"].keys():
        assert isinstance(json["vectors"]["collections"][collection], list)
        if collection == "procedural":
            assert len(json["vectors"]["collections"][collection]) > 0
        else:
            assert len(json["vectors"]["collections"][collection]) == 0


# search without query should throw error
def test_memory_recall_without_query_error(secure_client, secure_client_headers):
    response = secure_client.get("/memory/recall", headers=secure_client_headers)
    assert response.status_code == 400


# search with query
def test_memory_recall_success(secure_client, secure_client_headers, mocked_default_llm_answer_prompt):
    # send a few messages via chat
    num_messages = 3
    send_n_websocket_messages(num_messages, secure_client)

    user = crud_users.get_user_by_username(agent_id, "user")

    # recall
    params = {"text": "Red Queen"}
    response = secure_client.get(
        "/memory/recall/", params=params, headers={**secure_client_headers, **{"user_id": user["id"]}}
    )
    json = response.json()
    assert response.status_code == 200
    episodic_memories = json["vectors"]["collections"]["episodic"]
    assert len(episodic_memories) == num_messages  # all 3 retrieved


# search with query and k
def test_memory_recall_with_k_success(secure_client, secure_client_headers, mocked_default_llm_answer_prompt):
    # send a few messages via chat
    num_messages = 6
    send_n_websocket_messages(num_messages, secure_client)

    user = crud_users.get_user_by_username(agent_id, "user")

    # recall at max k memories
    max_k = 2
    params = {"k": max_k, "text": "Red Queen"}
    response = secure_client.get(
        "/memory/recall/", params=params, headers={**secure_client_headers, **{"user_id": user["id"]}}
    )
    json = response.json()
    assert response.status_code == 200
    episodic_memories = json["vectors"]["collections"]["episodic"]
    assert len(episodic_memories) == max_k  # only 2 of 6 memories recalled
