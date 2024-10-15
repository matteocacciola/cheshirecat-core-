import shutil
from uuid import UUID, uuid4
from urllib.parse import urlencode
from concurrent.futures import ThreadPoolExecutor

from cat.auth.auth_utils import hash_password
from cat.auth.permissions import get_base_permissions
from cat.db import crud_users


def get_class_from_decorated_singleton(singleton):
    return singleton().__class__


# utility function to communicate with the cat via websocket
def send_websocket_message(msg, client, user_id="user", agent_id=None, query_params=None):
    url = f"/ws/{user_id}"

    if agent_id:
        url += f"/{agent_id}"

    if query_params:
        url += "?" + urlencode(query_params)

    with client.websocket_connect(url) as websocket:
        # sed ws message
        websocket.send_json(msg)
        # get reply
        reply = websocket.receive_json()

    return reply


# utility to send n messages via chat
def send_n_websocket_messages(num_messages, client, agent_id=None):
    responses = []

    url = "/ws"
    if agent_id:
        url += f"/user/{agent_id}"

    with client.websocket_connect(url) as websocket:
        for m in range(num_messages):
            message = {"text": f"Red Queen {m}"}
            # sed ws message
            websocket.send_json(message)
            # get reply
            reply = websocket.receive_json()
            responses.append(reply)

    return responses


def key_in_json(key, json):
    return key in json.keys()


# create a plugin zip out of the mock plugin folder.
# - Used to test plugin upload.
# - zip can be created flat (plugin files in root dir) or nested (plugin files in zipped folder)
def create_mock_plugin_zip(flat: bool):
    if flat:
        root_dir = "tests/mocks/mock_plugin"
        base_dir = "./"
    else:
        root_dir = "tests/mocks/"
        base_dir = "mock_plugin"

    return shutil.make_archive(
        base_name="tests/mocks/mock_plugin",
        format="zip",
        root_dir=root_dir,
        base_dir=base_dir,
    )


# utility to retrieve embedded tools from endpoint
def get_procedural_memory_contents(client, cheshire_cat, params=None):
    final_params = (params or {}) | {"text": "random"}
    response = client.get("/memory/recall/", params=final_params, headers={"agent_id": cheshire_cat.id})
    json = response.json()
    return json["vectors"]["collections"]["procedural"]


# utility to retrieve declarative memory contents
def get_declarative_memory_contents(client, cheshire_cat):
    params = {"text": "Something"}
    response = client.get("/memory/recall/", params=params, headers={"agent_id": cheshire_cat.id})
    assert response.status_code == 200
    json = response.json()
    declarative_memories = json["vectors"]["collections"]["declarative"]
    return declarative_memories


# utility to get collections and point count from `GET /memory/collections` in a simpler format
def get_collections_names_and_point_count(client, cheshire_cat):
    response = client.get("/memory/collections", headers={"agent_id": cheshire_cat.id})
    json = response.json()
    assert response.status_code == 200
    collections_n_points = {c["name"]: c["vectors_count"] for c in json["collections"]}
    return collections_n_points


def create_new_user(client, route: str, headers=None):
    new_user = {"username": "Alice", "password": "wandering_in_wonderland"}
    response = client.post(route, json=new_user, headers=headers)
    assert response.status_code == 200
    return response.json()


def check_user_fields(u):
    assert set(u.keys()) == {"id", "username", "permissions"}
    assert isinstance(u["username"], str)
    assert isinstance(u["permissions"], dict)
    try:
        # Attempt to create a UUID object from the string to validate it
        uuid_obj = UUID(u["id"], version=4)
        assert str(uuid_obj) == u["id"]
    except ValueError:
        # If a ValueError is raised, the UUID string is invalid
        assert False, "Not a UUID"


def run_job_in_thread(job, obj, loop):
    """
    Helper function to run job_on_idle_strays in a separate thread.
    """
    with ThreadPoolExecutor() as executor:
        future = executor.submit(job, obj, loop)
        return future.result()


async def async_run_job(job, obj, loop):
    """
    Asynchronously run job_on_idle_strays in a separate thread.
    """
    return await loop.run_in_executor(None, run_job_in_thread, job, obj, loop)


def create_basic_user(agent_id: str) -> None:
    user_id = str(uuid4())

    basic_user = {
        user_id: {
            "id": user_id,
            "username": "user",
            "password": hash_password("user"),
            # user has minor permissions
            "permissions": get_base_permissions(),
        }
    }

    crud_users.update_users(agent_id, basic_user)
