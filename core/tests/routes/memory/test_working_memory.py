import time

from cat.convo.messages import Role

from tests.utils import send_websocket_message, agent_id, api_key


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
    send_websocket_message({"text": message}, secure_client)

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
    assert isinstance(json["history"][0]["when"], float)  # timestamp


def test_convo_history_reset(secure_client, secure_client_headers):
    # send websocket messages
    send_websocket_message({"text": "It's late! It's late!"}, secure_client)

    # delete convo history
    response = secure_client.delete("/memory/conversation_history", headers=secure_client_headers)
    assert response.status_code == 200

    # check working memory update
    response = secure_client.get("/memory/conversation_history", headers=secure_client_headers)
    json = response.json()
    assert response.status_code == 200
    assert "history" in json
    assert len(json["history"]) == 0


# TODO: should be tested also with concurrency!
def test_convo_history_by_user(secure_client, secure_client_headers):
    convos = {
        # user_id: n_messages
        "White Rabbit": 2,
        "Alice": 3,
    }

    # send websocket messages
    for user_id, n_messages in convos.items():
        for m in range(n_messages):
            time.sleep(0.1)
            send_websocket_message({"text": f"Mex n.{m} from {user_id}"}, secure_client, user_id=user_id)

    # check working memories
    for user_id, n_messages in convos.items():
        response = secure_client.get(
            "/memory/conversation_history/",
            headers={"user_id": user_id, "agent_id": agent_id, "access_token": api_key},
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
                assert m["message"] == f"Mex n.{m_number_from_user} from {user_id}"
            else:
                assert m["who"] == str(Role.AI)

    # delete White Rabbit convo
    response = secure_client.delete(
        "/memory/conversation_history/",
        headers={"user_id": "White Rabbit", "agent_id": agent_id, "access_token": api_key},
    )
    assert response.status_code == 200

    # check convo deletion per user
    ### White Rabbit convo is empty
    response = secure_client.get(
        "/memory/conversation_history/",
        headers={"user_id": "White Rabbit", "agent_id": agent_id, "access_token": api_key},
    )
    json = response.json()
    assert len(json["history"]) == 0
    ### Alice convo still the same
    response = secure_client.get(
        "/memory/conversation_history/",
        headers={"user_id": "Alice", "agent_id": agent_id, "access_token": api_key},
    )
    json = response.json()
    assert len(json["history"]) == convos["Alice"] * 2
