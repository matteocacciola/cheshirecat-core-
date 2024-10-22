from tests.utils import agent_id, api_key, send_websocket_message


# episodic memories are saved having the correct user
def test_episodic_memory_by_user(secure_client, secure_client_headers):
    # send websocket message from user C
    send_websocket_message(
        {
            "text": "I am user C",
        },
        secure_client,
        user_id="C",
    )

    # episodic recall (no user)
    params = {"text": "I am user"}
    response = secure_client.get("/memory/recall/", params=params, headers=secure_client_headers)
    json = response.json()
    assert response.status_code == 200
    episodic_memories = json["vectors"]["collections"]["episodic"]
    assert len(episodic_memories) == 0

    # episodic recall (memories from non-existing user)
    params = {"text": "I am user not existing"}
    response = secure_client.get(
        "/memory/recall/",
        params=params,
        headers={"user_id": "not_existing", "agent_id": agent_id, "access_token": api_key}
    )
    json = response.json()
    assert response.status_code == 200
    episodic_memories = json["vectors"]["collections"]["episodic"]
    assert len(episodic_memories) == 0

    # episodic recall (memories from user C)
    params = {"text": "I am user C"}
    response = secure_client.get(
        "/memory/recall/", params=params, headers={"user_id": "C", "agent_id": agent_id, "access_token": api_key}
    )
    json = response.json()
    assert response.status_code == 200
    episodic_memories = json["vectors"]["collections"]["episodic"]
    assert len(episodic_memories) == 1
    assert episodic_memories[0]["metadata"]["source"] == "C"
