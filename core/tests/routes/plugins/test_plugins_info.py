def test_list_plugins(secure_client, secure_client_headers):
    response = secure_client.get("/plugins", headers=secure_client_headers)
    json = response.json()

    assert response.status_code == 200
    for key in ["filters", "installed", "registry"]:
        assert key in json.keys()

    # query
    for key in ["query"]:  # ["query", "author", "tag"]:
        assert key in json["filters"].keys()

    # installed
    assert json["installed"][0]["id"] == "core_plugin"
    assert isinstance(json["installed"][0]["active"], bool)
    assert json["installed"][0]["active"]

    # registry (see more registry tests in `./test_plugins_registry.py`)
    assert isinstance(json["registry"], list)
    assert len(json["registry"]) > 0
