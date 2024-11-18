from tests.utils import agent_id, api_key, send_websocket_message, create_new_user, new_user_password


# episodic memories are saved having the correct user
def test_episodic_memory_by_user(secure_client, secure_client_headers, client):
    # create a new user with username CCC
    username = "CCC"
    data = create_new_user(secure_client, "/users", username=username, headers=secure_client_headers)

    # get the token, to be used in the websocket connection
    res = client.post(
        "/auth/token",
        json={"username": data["username"], "password": new_user_password},
        headers={"agent_id": agent_id}
    )
    received_token = res.json()["access_token"]

    # send websocket message from user CCC
    send_websocket_message({"text": f"I am user {username}"}, client, query_params={"token": received_token})

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
        headers={**secure_client_headers, **{"user_id": "not_existing"}}
    )
    assert response.status_code == 403

    # episodic recall (memories from user CCC)
    params = {"text": f"I am user {username}"}
    response = secure_client.get(
        "/memory/recall/", params=params, headers={**secure_client_headers, **{"user_id": data["id"]}}
    )
    json = response.json()
    assert response.status_code == 200
    episodic_memories = json["vectors"]["collections"]["episodic"]
    # There is no memory here, since we have not set a valid LLM
    assert len(episodic_memories) == 0
