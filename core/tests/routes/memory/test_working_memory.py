import time

from cat.convo.messages import Role

from tests.utils import send_websocket_message, agent_id, api_key, create_new_user, new_user_password, api_key_ws


def test_convo_history_absent(secure_client, secure_client_headers):
    # no ws connection, so no convo history available
    response = secure_client.get("/memory/conversation_history", headers=secure_client_headers)
    json = response.json()
    assert response.status_code == 200
    assert "history" in json
    assert len(json["history"]) == 0


def test_convo_history_update(secure_client, secure_client_headers):
    message = "It's late! It's late!"

    # send websocket messages
    send_websocket_message({"text": message}, secure_client, {"apikey": api_key_ws})

    # check working memory update
    response = secure_client.get("/memory/conversation_history", headers=secure_client_headers)
    json = response.json()
    assert response.status_code == 200
    assert "history" in json
    assert len(json["history"]) == 2  # mex and reply

    picked_history = json["history"][0]

    assert picked_history["who"] == str(Role.HUMAN)
    assert picked_history["message"] == message
    assert picked_history["why"] is None
    assert isinstance(picked_history["when"], float)  # timestamp


def test_convo_history_reset(secure_client, secure_client_headers):
    # send websocket messages
    send_websocket_message({"text": "It's late! It's late!"}, secure_client, {"apikey": api_key_ws})

    # delete convo history
    response = secure_client.delete("/memory/conversation_history", headers=secure_client_headers)
    assert response.status_code == 200

    # check working memory update
    response = secure_client.get("/memory/conversation_history", headers=secure_client_headers)
    json = response.json()
    assert response.status_code == 200
    assert "history" in json
    assert len(json["history"]) == 0


def test_convo_history_by_user(secure_client, secure_client_headers, client):
    convos = {
        # user_id: n_messages
        "White Rabbit": 2,
        "Alice": 3,
    }

    tokens = {}
    users = {}
    # send websocket messages
    for username, n_messages in convos.items():
        data = create_new_user(secure_client, "/users", username=username, headers=secure_client_headers)
        res = client.post(
            "/auth/token",
            json={"username": data["username"], "password": new_user_password},
            headers={"agent_id": agent_id}
        )
        received_token = res.json()["access_token"]
        tokens[username] = received_token
        users[username] = data

        for m in range(n_messages):
            time.sleep(0.1)
            send_websocket_message(
                {"text": f"Mex n.{m} from {username}"}, client, query_params={"token": received_token}
            )

    # check working memories
    for username, n_messages in convos.items():
        response = client.get(
            "/memory/conversation_history/",
            headers={"agent_id": agent_id, "Authorization": f"Bearer {tokens[username]}"},
        )
        json = response.json()
        assert response.status_code == 200
        assert "history" in json
        assert len(json["history"]) == n_messages * 2  # mex and reply
        for m_idx, m in enumerate(json["history"]):
            assert "who" in m
            assert "message" in m
            if m_idx % 2 == 0:  # even message
                m_number_from_user = int(m_idx / 2)
                assert m["who"] == str(Role.HUMAN)
                assert m["message"] == f"Mex n.{m_number_from_user} from {username}"
            else:
                assert m["who"] == str(Role.AI)

    # delete White Rabbit convo
    response = client.delete(
        "/memory/conversation_history/",
        headers={"agent_id": agent_id, "Authorization": f"Bearer {tokens['White Rabbit']}"},
    )
    assert response.status_code == 403  # user has no permission
    response = secure_client.delete(
        "/memory/conversation_history/",
        headers={"user_id": users["White Rabbit"]["id"], "agent_id": agent_id, "Authorization": f"Bearer {api_key}"},
    )
    assert response.status_code == 200

    # check convo deletion per user
    ### White Rabbit convo is empty
    response = secure_client.get(
        "/memory/conversation_history/",
        headers=secure_client_headers | {"user_id": users["White Rabbit"]["id"]},
    )
    json = response.json()
    assert len(json["history"]) == 0
    ### Alice convo still the same
    response = secure_client.get(
        "/memory/conversation_history/",
        headers=secure_client_headers | {"user_id": users["Alice"]["id"]},
    )
    json = response.json()
    assert len(json["history"]) == convos["Alice"] * 2
