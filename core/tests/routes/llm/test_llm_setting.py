from json import dumps
from fastapi.encoders import jsonable_encoder

from cat.factory.llm import LLMFactory

from tests.utils import create_new_user, new_user_password, agent_id


def test_get_all_llm_settings(secure_client, secure_client_headers, cheshire_cat):
    llms_schemas = LLMFactory(cheshire_cat.mad_hatter).get_schemas()

    response = secure_client.get("/llm/settings", headers=secure_client_headers)
    json = response.json()

    assert response.status_code == 200
    assert isinstance(json["settings"], list)
    assert len(json["settings"]) == len(llms_schemas)

    for setting in json["settings"]:
        assert setting["name"] in llms_schemas.keys()
        assert setting["value"] == {}
        expected_schema = llms_schemas[setting["name"]]
        assert dumps(jsonable_encoder(expected_schema)) == dumps(setting["scheme"])

    assert json["selected_configuration"] == "LLMDefaultConfig"


def test_get_llm_settings_non_existent(secure_client, secure_client_headers):
    non_existent_llm_name = "LLMNonExistentConfig"
    response = secure_client.get(f"/llm/settings/{non_existent_llm_name}", headers=secure_client_headers)
    json = response.json()

    assert response.status_code == 400
    assert f"{non_existent_llm_name} not supported" in json["detail"]["error"]


def test_get_llm_settings(secure_client, secure_client_headers):
    llm_name = "LLMDefaultConfig"
    response = secure_client.get(f"/llm/settings/{llm_name}", headers=secure_client_headers)
    json = response.json()

    assert response.status_code == 200
    assert json["name"] == llm_name
    assert json["value"] == {}
    assert json["scheme"]["languageModelName"] == llm_name
    assert json["scheme"]["type"] == "object"


def test_upsert_llm_settings_success(secure_client, secure_client_headers):
    # set a different LLM
    new_llm = "LLMCustomConfig"
    invented_url = "https://example.com"
    payload = {"url": invented_url, "options": {}}
    response = secure_client.put(f"/llm/settings/{new_llm}", json=payload, headers=secure_client_headers)

    # check immediate response
    json = response.json()
    assert response.status_code == 200
    assert json["name"] == new_llm
    assert json["value"]["url"] == invented_url

    # retrieve all LLMs settings to check if it was saved in DB
    response = secure_client.get("/llm/settings", headers=secure_client_headers)
    json = response.json()
    assert response.status_code == 200
    assert json["selected_configuration"] == new_llm
    saved_config = [c for c in json["settings"] if c["name"] == new_llm]
    assert saved_config[0]["value"]["url"] == invented_url

    # check also specific LLM endpoint
    response = secure_client.get(f"/llm/settings/{new_llm}", headers=secure_client_headers)
    assert response.status_code == 200
    json = response.json()
    assert json["name"] == new_llm
    assert json["value"]["url"] == invented_url
    assert json["scheme"]["languageModelName"] == new_llm


def test_forbidden_access_no_auth(client):
    response = client.get("/llm/settings")
    assert response.status_code == 403


def test_granted_access_on_permissions(secure_client, secure_client_headers, client):
    # create user
    data = create_new_user(secure_client, "/users", headers=secure_client_headers, permissions={"LLM": ["LIST"]})

    creds = {"username": data["username"], "password": new_user_password}

    res = client.post("/auth/token", json=creds, headers={"agent_id": agent_id})
    received_token = res.json()["access_token"]

    response = client.get("/llm/settings", headers={"Authorization": f"Bearer {received_token}", "agent_id": agent_id})
    assert response.status_code == 200


def test_forbidden_access_no_permission(secure_client, secure_client_headers, client):
    # create user
    data = create_new_user(secure_client, "/users", headers=secure_client_headers)

    creds = {"username": data["username"], "password": new_user_password}

    res = client.post("/auth/token", json=creds, headers={"agent_id": agent_id})
    received_token = res.json()["access_token"]

    response = client.get("/llm/settings", headers={"Authorization": f"Bearer {received_token}", "agent_id": agent_id})
    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "Invalid Credentials"


def test_forbidden_access_wrong_permissions(secure_client, secure_client_headers, client):
    # create user
    data = create_new_user(secure_client, "/users", headers=secure_client_headers, permissions={"LLM": ["READ"]})

    creds = {"username": data["username"], "password": new_user_password}

    res = client.post("/auth/token", json=creds, headers={"agent_id": agent_id})
    received_token = res.json()["access_token"]

    response = client.get("/llm/settings", headers={"Authorization": f"Bearer {received_token}", "agent_id": agent_id})
    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "Invalid Credentials"
