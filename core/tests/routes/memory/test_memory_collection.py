from tests.utils import send_websocket_message, get_collections_names_and_point_count


def test_memory_collections_created(secure_client, secure_client_headers):
    # get collections
    response = secure_client.get("/memory/collections", headers=secure_client_headers)
    json = response.json()
    assert response.status_code == 200

    # check default collections are created
    default_collections = ["episodic", "declarative", "procedural"]
    assert len(json["collections"]) == len(default_collections)

    # check correct number of default points
    collections_n_points = {c["name"]: c["vectors_count"] for c in json["collections"]}
    # there is at least an embedded tool in procedural collection
    assert collections_n_points["procedural"] == 3
    # all other collections should be empty
    assert collections_n_points["episodic"] == 0
    assert collections_n_points["declarative"] == 0


def test_memory_collection_episodic_stores_messages(secure_client, secure_client_headers):
    # before sending messages, episodic memory should be empty
    collections_n_points = get_collections_names_and_point_count(secure_client, secure_client_headers)
    assert collections_n_points["episodic"] == 0

    # send message via websocket
    message = {"text": "Meow"}
    res = send_websocket_message(message, secure_client)
    assert isinstance(res["content"], str)

    # episodic memory should now contain one point
    collections_n_points = get_collections_names_and_point_count(secure_client, secure_client_headers)
    assert collections_n_points["episodic"] == 1

    # TOODO: check point metadata


def test_memory_collection_non_existent_clear(secure_client, secure_client_headers):
    non_existent_collection = "nonexistent"
    response = secure_client.delete(f"/memory/collections/{non_existent_collection}", headers=secure_client_headers)
    json = response.json()
    assert response.status_code == 404
    assert "Collection does not exist" in json["detail"]["error"]


def test_memory_collection_episodic_cleared(secure_client, secure_client_headers):
    # send message via websocket
    message = {"text": "Meow"}
    res = send_websocket_message(message, secure_client)
    assert isinstance(res["content"], str)

    # episodic memory should now contain one point
    collections_n_points = get_collections_names_and_point_count(secure_client, secure_client_headers)
    assert collections_n_points["episodic"] == 1

    # delete episodic memory
    response = secure_client.delete("/memory/collections/episodic", headers=secure_client_headers)
    assert response.status_code == 200

    # episodic memory should be empty
    collections_n_points = get_collections_names_and_point_count(secure_client, secure_client_headers)
    assert collections_n_points["episodic"] == 0


def test_memory_collection_procedural_has_tools_after_clear(secure_client, secure_client_headers):
    # procedural memory contains one tool (get_the_time)
    collections_n_points = get_collections_names_and_point_count(secure_client, secure_client_headers)
    assert collections_n_points["procedural"] == 3

    # delete procedural memory
    response = secure_client.delete("/memory/collections/procedural", headers=secure_client_headers)
    assert response.status_code == 200

    # tool should be automatically re-embedded after memory deletion
    collections_n_points = get_collections_names_and_point_count(secure_client, secure_client_headers)
    assert collections_n_points["procedural"] == 3  # still 1!


def test_memory_collections_wipe(secure_client, secure_client_headers):
    # create episodic memory
    message = {"text": "Meow"}
    send_websocket_message(message, secure_client)

    # create declarative memories
    file_name = "sample.txt"
    file_path = f"tests/mocks/{file_name}"
    with open(file_path, "rb") as f:
        files = {"file": (file_name, f, "text/plain")}
        secure_client.post("/rabbithole/", files=files, headers=secure_client_headers)

    collections_n_points = get_collections_names_and_point_count(secure_client, secure_client_headers)
    assert collections_n_points["procedural"] == 3  # default tool
    assert collections_n_points["episodic"] == 1  # websocket msg
    assert collections_n_points["declarative"] > 1  # several chunks

    # wipe out all memories
    response = secure_client.delete("/memory/collections", headers=secure_client_headers)
    assert response.status_code == 200

    collections_n_points = get_collections_names_and_point_count(secure_client, secure_client_headers)
    assert collections_n_points["procedural"] == 3  # default tool is re-embedded
    assert collections_n_points["episodic"] == 0
    assert collections_n_points["declarative"] == 0
