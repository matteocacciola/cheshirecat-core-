import os
import pytest

from cat.env import get_env
from tests.utils import send_websocket_message


# utility to make http requests with some headers
def http_request(client, cheshire_cat, headers=None):
    headers = (headers or {}) | {"agent_id": cheshire_cat.id}
    response = client.get("/", headers=headers)
    return response.status_code, response.json()


def set_api_key(key: str, value: str) -> str | None:
    current_api_key = get_env(key)
    # set CCAT_API_KEY
    os.environ[key] = value

    return current_api_key


def reset_api_key(key, value: str | None) -> None:
    # remove CCAT_API_KEY
    if value:
        os.environ[key] = value
    else:
        del os.environ[key]


@pytest.mark.parametrize("header_name", ["Authorization", "access_token"])
def test_api_key_http(client, header_name, cheshire_cat):
    current_api_key = set_api_key("CCAT_API_KEY", "meow_http")

    # add "Bearer: " when using `Authorization` header
    key_prefix = ""
    if header_name == "Authorization":
        key_prefix = "Bearer "

    wrong_headers = [
        {}, # no key
        {header_name: f"{key_prefix}wrong"}, # wrong key
        {header_name: f"{key_prefix}meow_ws"}, # websocket key
    ]

    # all the previous headers result in a 403
    for headers in wrong_headers:
        status_code, json = http_request(client, cheshire_cat, headers)
        assert status_code == 403
        assert json["detail"]["error"] == "Invalid Credentials"

    # allow access if CCAT_API_KEY is right
    headers = {header_name: f"{key_prefix}meow_http"}
    status_code, json = http_request(client, cheshire_cat, headers)
    assert status_code == 200
    assert json["status"] == "We're all mad here, dear!"

    # allow websocket access without any key
    mex = {"text": "Where do I go?"}
    res = send_websocket_message(mex, client, agent_id=cheshire_cat.id)
    assert "You did not configure" in res["content"]

    reset_api_key("CCAT_API_KEY", current_api_key)


def test_api_key_ws(client, cheshire_cat):
    # set CCAT_API_KEY_WS
    current_api_key = set_api_key("CCAT_API_KEY_WS", "meow_ws")

    mex = {"text": "Where do I go?"}

    wrong_query_params = [
        {}, # no key
        {"token": "wrong"}, # wrong key
    ]

    for params in wrong_query_params:
        with pytest.raises(Exception) as e_info:
            send_websocket_message(mex, client, agent_id=cheshire_cat.id, query_params=params)
        assert str(e_info.type.__name__) == "WebSocketDisconnect"

    # allow access if CCAT_API_KEY_WS is right
    query_params = {"token": "meow_ws"}
    res = send_websocket_message(mex, client, agent_id=cheshire_cat.id, query_params=query_params)
    assert "You did not configure" in res["content"]

    # allow http access without any key
    status_code, json = http_request(client, cheshire_cat)
    assert status_code == 200
    assert json["status"] == "We're all mad here, dear!"

    reset_api_key("CCAT_API_KEY_WS", current_api_key)
