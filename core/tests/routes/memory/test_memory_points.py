import pytest

from cat.db.cruds import users as crud_users

from tests.utils import (
    send_websocket_message,
    get_declarative_memory_contents,
    agent_id,
    fake_timestamp,
    api_key_ws,
)


def test_create_point_wrong_collection(secure_client, secure_client_headers, cheshire_cat):
    user = crud_users.get_user_by_username(agent_id, "user")
    headers = secure_client_headers | {"user_id": user["id"]}

    req_json = {"content": "Hello dear"}

    # wrong collection
    res = secure_client.post("/memory/collections/wrongcollection/points", json=req_json, headers=headers)
    assert res.status_code == 404
    assert "Collection does not exist" in res.json()["detail"]["error"]

    # cannot write procedural point
    res = secure_client.post("/memory/collections/procedural/points", json=req_json, headers=headers)
    assert res.status_code == 400
    assert "Procedural memory is read-only" in res.json()["detail"]["error"]


@pytest.mark.parametrize("collection", ["episodic", "declarative"])
def test_create_memory_point(secure_client, secure_client_headers, cheshire_cat, patch_time_now, collection):
    user = crud_users.get_user_by_username(agent_id, "user")
    headers = secure_client_headers | {"user_id": user["id"]}

    # create a point
    content = "Hello dear"
    metadata = {"custom_key": "custom_value"}
    req_json = {"content": content, "metadata": metadata}
    res = secure_client.post(f"/memory/collections/{collection}/points", json=req_json, headers=headers)
    assert res.status_code == 200
    json = res.json()
    assert json["content"] == content
    expected_metadata = {"when": fake_timestamp, "source": headers["user_id"], **metadata}
    assert json["metadata"] == expected_metadata
    assert "id" in json
    assert "vector" in json
    assert isinstance(json["vector"], list)
    assert isinstance(json["vector"][0], float)

    # check memory contents
    params = {"text": "dear, hello"}
    response = secure_client.get("/memory/recall/", params=params, headers=headers)
    json = response.json()
    assert response.status_code == 200
    assert len(json["vectors"]["collections"][collection]) == 1
    memory = json["vectors"]["collections"][collection][0]
    assert memory["page_content"] == content
    assert memory["metadata"] == expected_metadata


def test_point_deleted(secure_client, secure_client_headers, mocked_default_llm_answer_prompt):
    # send websocket message
    send_websocket_message({"text": "Hello Mad Hatter"}, secure_client, {"apikey": api_key_ws})

    # get point back
    params = {"text": "Mad Hatter"}
    response = secure_client.get("/memory/recall/", params=params, headers=secure_client_headers)
    json = response.json()
    assert response.status_code == 200
    assert len(json["vectors"]["collections"]["episodic"]) == 1
    mem = json["vectors"]["collections"]["episodic"][0]
    assert mem["page_content"] == "Hello Mad Hatter"

    # delete point (wrong collection)
    res = secure_client.delete(f"/memory/collections/wrongcollection/points/{mem['id']}", headers=secure_client_headers)
    assert res.status_code == 404
    assert res.json()["detail"]["error"] == "Collection does not exist."

    # cannot write procedural point
    res = secure_client.delete("/memory/collections/procedural/points/{mem['id']}", headers=secure_client_headers)
    assert res.status_code == 400
    assert "Procedural memory is read-only" in res.json()["detail"]["error"]

    # delete point (wrong id)
    res = secure_client.delete("/memory/collections/episodic/points/wrong_id", headers=secure_client_headers)
    assert res.status_code == 404
    assert res.json()["detail"]["error"] == "Point does not exist."

    # delete point (all right)
    res = secure_client.delete(f"/memory/collections/episodic/points/{mem['id']}", headers=secure_client_headers)
    assert res.status_code == 200
    assert res.json()["deleted"] == mem["id"]

    # there is no point now
    params = {"text": "Mad Hatter"}
    response = secure_client.get("/memory/recall/", params=params, headers=secure_client_headers)
    json = response.json()
    assert response.status_code == 200
    assert len(json["vectors"]["collections"]["episodic"]) == 0

    # delete again the same point (should not be found)
    res = secure_client.delete(f"/memory/collections/episodic/points/{mem['id']}", headers=secure_client_headers)
    assert res.status_code == 404
    assert res.json()["detail"]["error"] == "Point does not exist."


# test delete points by filter
def test_points_deleted_by_metadata(secure_client, secure_client_headers):
    expected_chunks = 4

    # upload to rabbithole a document
    content_type = "application/pdf"
    file_name = "sample.pdf"
    file_path = f"tests/mocks/{file_name}"
    with open(file_path, "rb") as f:
        files = {"file": (file_name, f, content_type)}
        response = secure_client.post("/rabbithole/", files=files, headers=secure_client_headers)

    # check response
    assert response.status_code == 200
    # check memory contents
    declarative_memories = get_declarative_memory_contents(secure_client, secure_client_headers)
    assert len(declarative_memories) == expected_chunks

    # upload another document
    with open(file_path, "rb") as f:
        files = {"file": ("sample2.pdf", f, content_type)}
        response = secure_client.post("/rabbithole/", files=files, headers=secure_client_headers)

    # check response
    assert response.status_code == 200
    # check memory contents
    declarative_memories = get_declarative_memory_contents(secure_client, secure_client_headers)
    assert len(declarative_memories) == expected_chunks * 2

    # delete nothing
    metadata = {"source": "invented.pdf"}
    res = secure_client.request(
        "DELETE", "/memory/collections/declarative/points", json=metadata, headers=secure_client_headers
    )
    # check memory contents
    assert res.status_code == 200
    declarative_memories = get_declarative_memory_contents(secure_client, secure_client_headers)
    assert len(declarative_memories) == expected_chunks * 2

    # delete first document
    metadata = {"source": "sample.pdf"}
    res = secure_client.request(
        "DELETE", "/memory/collections/declarative/points", json=metadata, headers=secure_client_headers
    )
    # check memory contents
    assert res.status_code == 200
    json = res.json()
    assert isinstance(json["deleted"], dict)
    # assert len(json["deleted"]) == expected_chunks
    declarative_memories = get_declarative_memory_contents(secure_client, secure_client_headers)
    assert len(declarative_memories) == expected_chunks

    # delete second document
    metadata = {"source": "sample2.pdf"}
    res = secure_client.request(
        "DELETE", "/memory/collections/declarative/points", json=metadata, headers=secure_client_headers
    )
    # check memory contents
    assert res.status_code == 200
    declarative_memories = get_declarative_memory_contents(secure_client, secure_client_headers)
    assert len(declarative_memories) == 0


def test_get_collection_points_wrong_collection(secure_client, secure_client_headers):
    # unexisting collection
    res = secure_client.get("/memory/collections/unexistent/points", headers=secure_client_headers)
    assert res.status_code == 404
    assert "Collection does not exist" in res.json()["detail"]["error"]

    # reserved procedural collection
    res = secure_client.get("/memory/collections/procedural/points", headers=secure_client_headers)
    assert res.status_code == 400
    assert "Procedural memory is read-only." in res.json()["detail"]["error"]


@pytest.mark.parametrize("collection", ["episodic", "declarative"])
def test_get_collection_points(secure_client, secure_client_headers, cheshire_cat, patch_time_now, collection):
    user = crud_users.get_user_by_username(agent_id, "user")
    headers = secure_client_headers | {"user_id": user["id"]}

    # create 100 points
    n_points = 100
    new_points = [{"content": f"MIAO {i}!", "metadata": {"custom_key": f"custom_key_{i}"}} for i in range(n_points)]

    # Add points
    for req_json in new_points:
        res = secure_client.post(f"/memory/collections/{collection}/points", json=req_json, headers=headers)
        assert res.status_code == 200

    # get all the points no limit, by default is 100
    res = secure_client.get(f"/memory/collections/{collection}/points", headers=headers)
    assert res.status_code == 200
    json = res.json()

    points = json["points"]
    offset = json["next_offset"]

    assert offset is None  # the result should contain all the points so no offset

    expected_payloads = [
        {
            "page_content": p["content"],
            "metadata": {
                "when": fake_timestamp,
                "source": headers["user_id"],
                **p["metadata"]
            },
            "group_id": agent_id,
        } for p in new_points
    ]

    assert len(points) == len(new_points)
    # check all the points contains id and vector
    for point in points:
        assert "id" in point
        assert "vector" in point

    # check points payload
    points_payloads = [p["payload"] for p in points]
    # sort the list and compare payload
    points_payloads.sort(key=lambda p: p["page_content"])
    expected_payloads.sort(key=lambda p: p["page_content"])
    assert points_payloads == expected_payloads


@pytest.mark.parametrize("collection", ["episodic", "declarative"])
def test_get_collection_points_offset(secure_client, secure_client_headers, cheshire_cat, patch_time_now, collection):
    user = crud_users.get_user_by_username(agent_id, "user")
    headers = secure_client_headers | {"user_id": user["id"]}

    # create 200 points
    n_points = 200
    new_points = [{"content": f"MEOW {i}!", "metadata": {"custom_key": f"custom_key_{i}"}} for i in range(n_points)]

    # Add points
    for req_json in new_points:
        res = secure_client.post(f"/memory/collections/{collection}/points", json=req_json, headers=headers)
        assert res.status_code == 200

    # get all the points with limit 10
    limit = 10
    next_offset = ""
    all_points = []

    while True:
        res = secure_client.get(
            f"/memory/collections/{collection}/points?limit={limit}&offset={next_offset}",
            headers = headers
        )
        assert res.status_code == 200
        json = res.json()
        points = json["points"]
        next_offset = json["next_offset"]
        assert len(points) == limit

        for point in points:
            all_points.append(point)

        if next_offset is None:  # break if no new data
            break

    # create the expected payloads for all the points
    expected_payloads = [
        {
            "page_content": p["content"],
            "metadata": {
                "when": fake_timestamp,
                "source": headers["user_id"],
                **p["metadata"]
            },
            "group_id": agent_id,
        } for p in new_points
    ]

    assert len(all_points) == len(new_points)
    # check all the points contains id and vector
    for point in all_points:
        assert "id" in point
        assert "vector" in point

    # check points payload
    points_payloads = [p["payload"] for p in all_points]
    # sort the list and compare payload
    points_payloads.sort(key=lambda p: p["page_content"])
    expected_payloads.sort(key=lambda p: p["page_content"])
    assert points_payloads == expected_payloads


def test_edit_point_wrong_collection_and_not_exist(secure_client, secure_client_headers, cheshire_cat):
    user = crud_users.get_user_by_username(agent_id, "user")
    headers = secure_client_headers | {"user_id": user["id"]}

    req_json = {"content": "Hello dear"}

    point_id = 100

    # wrong collection
    res = secure_client.put(f"/memory/collections/wrongcollection/points/{point_id}", json=req_json, headers=headers)
    assert res.status_code == 404
    assert "Collection does not exist" in res.json()["detail"]["error"]

    # cannot write procedural point
    res = secure_client.put("/memory/collections/procedural/points/{point_id}", json=req_json, headers=headers)
    assert res.status_code == 400
    assert "Procedural memory is read-only" in res.json()["detail"]["error"]

    # point do not exist
    res = secure_client.put("/memory/collections/declarative/points/{point_id}", json=req_json, headers=headers)
    assert res.status_code == 404
    assert res.json()["detail"]["error"] == "Point does not exist."


@pytest.mark.parametrize("collection", ["episodic", "declarative"])
def test_edit_memory_point(secure_client, secure_client_headers, cheshire_cat, patch_time_now, collection):
    user = crud_users.get_user_by_username(agent_id, "user")
    headers = secure_client_headers | {"user_id": user["id"]}

    # create a point
    content = "Hello dear"
    metadata = {"custom_key": "custom_value"}
    req_json = {"content": content, "metadata": metadata}
    # create a point
    res = secure_client.post(f"/memory/collections/{collection}/points", json=req_json, headers=headers)
    assert res.status_code == 200
    json = res.json()
    assert json["id"]

    point_id = json["id"]
    # new point values
    content = "MEOW MEOW!"
    metadata = {"custom_key": "new_custom_value"}
    req_json = {"content": content, "metadata": metadata}

    res = secure_client.put(f"/memory/collections/{collection}/points/{point_id}", json=req_json, headers=headers)
    # check response
    assert res.status_code == 200
    json = res.json()
    assert json["content"] == content
    expected_metadata = {"when":fake_timestamp, "source": headers["user_id"], **metadata}
    assert json["metadata"] == expected_metadata
    assert "id" in json
    assert "vector" in json
    assert isinstance(json["vector"], list)
    assert isinstance(json["vector"][0], float)

    # check memory contents
    params = {"text": "dear, hello"}
    response = secure_client.get("/memory/recall/", params=params, headers=headers)
    json = response.json()
    assert response.status_code == 200
    assert len(json["vectors"]["collections"][collection]) == 1
    memory = json["vectors"]["collections"][collection][0]
    assert memory["page_content"] == content
    assert memory["metadata"] == expected_metadata
