import os


# NOTE: here we test zip upload and install
# install from registry is in `./test_plugins_registry.py`
def test_plugin_install_from_zip(secure_client, secure_client_headers, just_installed_plugin):
    # during tests, the cat uses a different folder for plugins
    mock_plugin_final_folder = "tests/mocks/mock_plugin_folder/mock_plugin"

    #### PLUGIN IS ALREADY ACTIVE

    # GET plugin endpoint responds
    response = secure_client.get("/admins/plugins/mock_plugin", headers=secure_client_headers)
    assert response.status_code == 200
    json = response.json()
    assert json["data"]["id"] == "mock_plugin"
    assert isinstance(json["data"]["active"], bool)
    assert json["data"]["active"]

    # GET plugins endpoint lists the plugin
    response = secure_client.get("/admins/plugins", headers=secure_client_headers)
    installed_plugins = response.json()["installed"]
    installed_plugins_names = list(map(lambda p: p["id"], installed_plugins))
    assert "mock_plugin" in installed_plugins_names
    # both core_plugin and mock_plugin are active
    for p in installed_plugins:
        assert isinstance(p["active"], bool)
        assert p["active"]

    # plugin has been actually extracted in (mock) plugins folder
    assert os.path.exists(mock_plugin_final_folder)

    # GET single plugin info, plugin is active
    response = secure_client.get("/admins/plugins/mock_plugin", headers=secure_client_headers)
    assert isinstance(response.json()["data"]["active"], bool)
    assert response.json()["data"]["active"]


def test_plugin_uninstall(secure_client, secure_client_headers, just_installed_plugin):
    # during tests, the cat uses a different folder for plugins
    mock_plugin_final_folder = "tests/mocks/mock_plugin_folder/mock_plugin"

    # remove plugin via endpoint (will delete also plugin folder in mock_plugin_folder)
    response = secure_client.delete("/admins/plugins/mock_plugin", headers=secure_client_headers)
    assert response.status_code == 200

    # mock_plugin is not installed in the cat (check both via endpoint and filesystem)
    response = secure_client.get("/admins/plugins", headers=secure_client_headers)
    installed_plugins_names = list(map(lambda p: p["id"], response.json()["installed"]))
    assert "mock_plugin" not in installed_plugins_names
    assert not os.path.exists(
        mock_plugin_final_folder
    )  # plugin folder removed from disk

    # GET single plugin info, plugin is not active
    response = secure_client.get("/admins/plugins/mock_plugin", headers=secure_client_headers)
    assert response.json()["detail"]["error"] == "Plugin not found"
