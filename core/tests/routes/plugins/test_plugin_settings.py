# endpoint to get settings and settings schema
def test_get_all_plugin_settings(secure_client, secure_client_headers, just_installed_plugin):
    response = secure_client.get("/plugins/settings", headers=secure_client_headers)
    json = response.json()

    installed_plugins = ["core_plugin", "mock_plugin"]

    assert response.status_code == 200
    assert isinstance(json["settings"], list)
    assert len(json["settings"]) == len(installed_plugins)

    for setting in json["settings"]:
        assert setting["name"] in installed_plugins
        assert setting["value"] == {}
        assert setting["schema"] == {}


def test_get_plugin_settings_non_existent(secure_client, secure_client_headers, just_installed_plugin):
    non_existent_plugin = "ghost_plugin"
    response = secure_client.get(f"/plugins/settings/{non_existent_plugin}", headers=secure_client_headers)
    json = response.json()

    assert response.status_code == 404
    assert "not found" in json["detail"]["error"]


# endpoint to get settings and settings schema
def test_get_plugin_settings(secure_client, secure_client_headers, just_installed_plugin):
    response = secure_client.get("/plugins/settings/mock_plugin", headers=secure_client_headers)
    response_json = response.json()

    assert response.status_code == 200
    assert response_json["name"] == "mock_plugin"
    assert response_json["value"] == {}
    assert response_json["schema"] == {}


# endpoint to save settings
def test_save_plugin_settings(secure_client, secure_client_headers, just_installed_plugin):
    # write a new setting, and then overwrite it
    for fake_value in ["a", "b"]:
        # save settings
        fake_settings = {"fake_setting": fake_value}
        response = secure_client.put("/plugins/settings/mock_plugin", json=fake_settings, headers=secure_client_headers)

        # check immediate response
        assert response.status_code == 200
        json = response.json()
        assert json["name"] == "mock_plugin"
        assert json["value"]["fake_setting"] == fake_value

        # retrieve all plugins settings to check if it was saved in DB
        response = secure_client.get("/plugins/settings", headers=secure_client_headers)
        json = response.json()
        assert response.status_code == 200
        saved_config = [c for c in json["settings"] if c["name"] == "mock_plugin"]
        assert saved_config[0]["value"]["fake_setting"] == fake_value

        # get settings back for this specific plugin
        response = secure_client.get("/plugins/settings/mock_plugin", headers=secure_client_headers)
        json = response.json()
        assert response.status_code == 200
        assert json["name"] == "mock_plugin"
        assert json["value"]["fake_setting"] == fake_value


# core_plugin has no settings and ignores them when saved (for the moment)
def test_core_plugin_settings(secure_client, secure_client_headers):
    # write a new setting, and then overwrite it (core_plugin should ignore this)
    for fake_value in ["a", "b"]:
        # save settings
        fake_settings = {"fake_setting": fake_value}
        response = secure_client.put("/plugins/settings/core_plugin", json=fake_settings, headers=secure_client_headers)

        # check immediate response
        json = response.json()
        assert response.status_code == 200
        assert json["name"] == "core_plugin"
        assert json["value"] == {}

        # get settings back (should be empty as core_plugin does not (yet) accept settings
        response = secure_client.get("/plugins/settings/core_plugin", headers=secure_client_headers)
        json = response.json()
        assert response.status_code == 200
        assert json["name"] == "core_plugin"
        assert json["value"] == {}
        assert json["schema"] == {}
