import os
from json import dumps
from fastapi.encoders import jsonable_encoder

from cat.factory.plugin_uploader import PluginUploaderFactory
import cat.utils as utils


def test_get_all_plugin_uploader_settings(secure_client, secure_client_headers, lizard):
    uploader_schemas = PluginUploaderFactory(lizard.march_hare).get_schemas()
    response = secure_client.get("/plugin_uploader/settings", headers=secure_client_headers)
    json = response.json()

    assert response.status_code == 200
    assert isinstance(json["settings"], list)
    assert len(json["settings"]) == len(uploader_schemas)

    for setting in json["settings"]:
        assert setting["name"] in uploader_schemas.keys()
        assert setting["value"] == (
            {"storage_dir": utils.get_plugins_path()} if setting["name"] == "LocalPluginUploaderConfig" else {}
        )
        expected_schema = uploader_schemas[setting["name"]]
        assert dumps(jsonable_encoder(expected_schema)) == dumps(setting["scheme"])

    # automatically selected uploader
    assert json["selected_configuration"] == "LocalPluginUploaderConfig"


def test_get_plugin_uploader_settings_non_existent(secure_client, secure_client_headers):
    non_existent_uploader_name = "PluginUploaderNonExistentConfig"
    response = secure_client.get(
        f"/plugin_uploader/settings/{non_existent_uploader_name}", headers=secure_client_headers
    )
    json = response.json()

    assert response.status_code == 400
    assert f"{non_existent_uploader_name} not supported" in json["detail"]["error"]


def test_get_uploader_settings(secure_client, secure_client_headers):
    plugin_uploader_name = "LocalPluginUploaderConfig"
    response = secure_client.get(f"/plugin_uploader/settings/{plugin_uploader_name}", headers=secure_client_headers)
    json = response.json()

    assert response.status_code == 200
    assert json["name"] == plugin_uploader_name
    assert json["value"] == {"storage_dir": utils.get_plugins_path()}  # local uploader
    assert json["scheme"]["pluginUploaderName"] == plugin_uploader_name
    assert json["scheme"]["type"] == "object"


def test_upsert_plugin_uploader_settings(secure_client, secure_client_headers):
    plugins_folder = "tests/mocks/mock_plugin_folder/"

    # set the same Plugin Uploader with a different folder name as `storage_dir`
    new_plugin_uploader = "LocalPluginUploaderConfig"
    plugin_uploader_config = {"storage_dir": "tests/mocks/mock_plugin_folder_new/"}
    response = secure_client.put(
        f"/plugin_uploader/settings/{new_plugin_uploader}", json=plugin_uploader_config, headers=secure_client_headers
    )
    json = response.json()

    # verify success
    assert response.status_code == 200
    assert json["name"] == new_plugin_uploader
    assert json["value"]["storage_dir"] == plugin_uploader_config["storage_dir"]

    # retrieve all embedders settings to check if it was saved in DB
    response = secure_client.get("/plugin_uploader/settings", headers=secure_client_headers)
    json = response.json()
    assert response.status_code == 200
    assert json["selected_configuration"] == new_plugin_uploader
    saved_config = [c for c in json["settings"] if c["name"] == new_plugin_uploader]
    assert saved_config[0]["value"]["storage_dir"] == plugin_uploader_config["storage_dir"]

    # check also specific embedder endpoint
    response = secure_client.get(f"/plugin_uploader/settings/{new_plugin_uploader}", headers=secure_client_headers)
    assert response.status_code == 200
    json = response.json()
    assert json["name"] == new_plugin_uploader
    assert json["value"]["storage_dir"] == plugin_uploader_config["storage_dir"]
    assert json["scheme"]["pluginUploaderName"] == new_plugin_uploader

    # restore the original folder
    os.system(f"cp -r tests/mocks/mock_plugin_folder_new/ {plugins_folder}")
    os.system(f"chown -R 1000:1000 {plugins_folder}")
    os.system(f"chmod g+rwx,u+rwx,o+rx,o-w {plugins_folder}")
