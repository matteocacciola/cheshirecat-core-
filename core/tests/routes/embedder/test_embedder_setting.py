from json import dumps
from fastapi.encoders import jsonable_encoder

from cat.factory.embedder import get_embedders_schemas
from cat.looking_glass.cheshire_cat_manager import CheshireCatManager
from tests.utils import get_procedural_memory_contents


def test_get_all_embedder_settings(client):
    cheshire_cat_manager: CheshireCatManager = client.app.state.cheshire_cat_manager
    cheshire_cat = cheshire_cat_manager.get_or_create_cheshire_cat("test")

    embedder_schemas = get_embedders_schemas(cheshire_cat.id)
    response = client.get("/embedder/settings")
    json = response.json()

    assert response.status_code == 200
    assert isinstance(json["settings"], list)
    assert len(json["settings"]) == len(embedder_schemas)

    for setting in json["settings"]:
        assert setting["name"] in embedder_schemas.keys()
        assert setting["value"] == {}
        expected_schema = embedder_schemas[setting["name"]]
        assert dumps(jsonable_encoder(expected_schema)) == dumps(setting["schema"])

    # automatically selected embedder
    assert json["selected_configuration"] == "EmbedderDumbConfig"


def test_get_embedder_settings_non_existent(client):
    non_existent_embedder_name = "EmbedderNonExistentConfig"
    response = client.get(f"/embedder/settings/{non_existent_embedder_name}")
    json = response.json()

    assert response.status_code == 400
    assert f"{non_existent_embedder_name} not supported" in json["detail"]["error"]


def test_get_embedder_settings(client):
    embedder_name = "EmbedderDumbConfig"
    response = client.get(f"/embedder/settings/{embedder_name}")
    json = response.json()

    assert response.status_code == 200
    assert json["name"] == embedder_name
    assert json["value"] == {}  # Dumb Embedder has indeed an empty config (no options)
    assert json["schema"]["languageEmbedderName"] == embedder_name
    assert json["schema"]["type"] == "object"


def test_upsert_embedder_settings(client):
    # set a different embedder from default one (same class different size # TODO: have another fake/test embedder class)
    new_embedder = "EmbedderFakeConfig"
    embedder_config = {"size": 64}
    response = client.put(f"/embedder/settings/{new_embedder}", json=embedder_config)
    json = response.json()

    # verify success
    assert response.status_code == 200
    assert json["name"] == new_embedder
    assert json["value"]["size"] == embedder_config["size"]

    # retrieve all embedders settings to check if it was saved in DB
    response = client.get("/embedder/settings")
    json = response.json()
    assert response.status_code == 200
    assert json["selected_configuration"] == new_embedder
    saved_config = [c for c in json["settings"] if c["name"] == new_embedder]
    assert saved_config[0]["value"]["size"] == embedder_config["size"]

    # check also specific embedder endpoint
    response = client.get(f"/embedder/settings/{new_embedder}")
    assert response.status_code == 200
    json = response.json()
    assert json["name"] == new_embedder
    assert json["value"]["size"] == embedder_config["size"]
    assert json["schema"]["languageEmbedderName"] == new_embedder


def test_upsert_embedder_settings_updates_collections(client):
    procedures = get_procedural_memory_contents(client)
    assert len(procedures) == 3
    assert len(procedures[0]["vector"]) == 2367  # default embedder

    # set a different embedder from default one (same class different size)
    embedder_config = {"size": 64}
    response = client.put("/embedder/settings/EmbedderFakeConfig", json=embedder_config)
    assert response.status_code == 200

    procedures = get_procedural_memory_contents(client)
    assert len(procedures) == 3
    for vec in procedures:
        assert len(vec["vector"]) == embedder_config["size"]
