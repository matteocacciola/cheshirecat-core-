import json

from tests.utils import get_declarative_memory_contents


def test_rabbithole_upload_txt(secure_client, secure_client_headers):
    content_type = "text/plain"
    file_name = "sample.txt"
    file_path = f"tests/mocks/{file_name}"
    with open(file_path, "rb") as f:
        files = {"file": (file_name, f, content_type)}
        response = secure_client.post("/rabbithole/", files=files, headers=secure_client_headers)

    # check response
    assert response.status_code == 200
    json = response.json()
    assert json["filename"] == file_name
    assert json["content_type"] == content_type
    assert "File is being ingested" in json["info"]

    # check memory contents
    # check declarative memory is empty
    declarative_memories = get_declarative_memory_contents(secure_client, secure_client_headers)
    assert (
        len(declarative_memories) == 3
    )  # TODO: why txt produces one chunk less than pdf?


def test_rabbithole_upload_pdf(secure_client, secure_client_headers):
    content_type = "application/pdf"
    file_name = "sample.pdf"
    file_path = f"tests/mocks/{file_name}"
    with open(file_path, "rb") as f:
        files = {"file": (file_name, f, content_type)}
        response = secure_client.post("/rabbithole/", files=files, headers=secure_client_headers)

    # check response
    assert response.status_code == 200
    json = response.json()
    assert json["filename"] == file_name
    assert json["content_type"] == content_type
    assert "File is being ingested" in json["info"]

    # check memory contents
    # check declarative memory is empty
    declarative_memories = get_declarative_memory_contents(secure_client, secure_client_headers)
    assert len(declarative_memories) == 4


def test_rabbithole_upload_batch_one_file(secure_client, secure_client_headers):
    content_type = "application/pdf"
    file_name = "sample.pdf"
    file_path = f"tests/mocks/{file_name}"
    with open(file_path, "rb") as f:
        files = [("files", (file_name, f, content_type))]
        response = secure_client.post("/rabbithole/batch", files=files, headers=secure_client_headers)

    # check response
    assert response.status_code == 200
    json = response.json()
    assert len(json) == 1
    assert file_name in json
    assert json[file_name]["filename"] == file_name
    assert json[file_name]["content_type"] == content_type
    assert "File is being ingested" in json[file_name]["info"]

    # check memory contents
    # check declarative memory is empty
    declarative_memories = get_declarative_memory_contents(secure_client, secure_client_headers)
    assert len(declarative_memories) == 4


def test_rabbithole_upload_batch_multiple_files(secure_client, secure_client_headers):
    files = []
    files_to_upload = {"sample.pdf": "application/pdf", "sample.txt": "application/txt"}
    for file_name in files_to_upload:
        content_type = files_to_upload[file_name]
        file_path = f"tests/mocks/{file_name}"
        files.append(("files", (file_name, open(file_path, "rb"), content_type)))

    response = secure_client.post("/rabbithole/batch", files=files, headers=secure_client_headers)

    # check response
    assert response.status_code == 200
    json = response.json()
    assert len(json) == len(files_to_upload)
    for file_name in files_to_upload:
        assert file_name in json
        assert json[file_name]["filename"] == file_name
        assert json[file_name]["content_type"] == files_to_upload[file_name]
        assert "File is being ingested" in json[file_name]["info"]

    # check memory contents
    # check declarative memory is empty
    declarative_memories = get_declarative_memory_contents(secure_client, secure_client_headers)
    assert len(declarative_memories) == 7


def test_rabbithole_chunking(secure_client, secure_client_headers):
    content_type = "application/pdf"
    file_name = "sample.pdf"
    file_path = f"tests/mocks/{file_name}"
    with open(file_path, "rb") as f:
        files = {"file": (file_name, f, content_type)}
        payload = {
            "chunk_size": 128,
            "chunk_overlap": 32,
        }

        response = secure_client.post("/rabbithole/", files=files, data=payload, headers=secure_client_headers)

    # check response
    assert response.status_code == 200

    # check memory contents
    declarative_memories = get_declarative_memory_contents(secure_client, secure_client_headers)
    assert len(declarative_memories) == 7


def test_rabbithole_upload_doc_with_metadata(secure_client, secure_client_headers):
    content_type = "application/pdf"
    file_name = "sample.pdf"
    file_path = f"tests/mocks/{file_name}"
    with open(file_path, "rb") as f:
        files = {"file": (file_name, f, content_type)}
        metadata = {
            "source": "sample.pdf",
            "title": "Test title",
            "author": "Test author",
            "year": 2020,
        }
        # upload file endpoint only accepts form-encoded data
        payload = {"metadata": json.dumps(metadata)}
        response = secure_client.post("/rabbithole/", files=files, data=payload, headers=secure_client_headers)

    # check response
    assert response.status_code == 200

    # check memory contents
    declarative_memories = get_declarative_memory_contents(secure_client, secure_client_headers)
    assert len(declarative_memories) == 4
    for dm in declarative_memories:
        for k, v in metadata.items():
            assert "when" in dm["metadata"]
            assert "source" in dm["metadata"]
            assert dm["metadata"][k] == v


def test_rabbithole_upload_docs_batch_with_metadata(secure_client, secure_client_headers):
    files = []
    files_to_upload = {"sample.pdf": "application/pdf", "sample.txt": "application/txt"}
    for file_name in files_to_upload:
        content_type = files_to_upload[file_name]
        file_path = f"tests/mocks/{file_name}"
        files.append(("files", (file_name, open(file_path, "rb"), content_type)))

    metadata = {
        "sample.pdf": {
            "source": "sample.pdf",
            "title": "Test title",
            "author": "Test author",
            "year": 2020
        },
        "sample.txt": {
            "source": "sample.txt",
            "title": "Test title",
            "author": "Test author",
            "year": 2021
        }
    }

    # upload file endpoint only accepts form-encoded data
    payload = {
        "metadata": json.dumps(metadata)
    }

    response = secure_client.post("/rabbithole/batch", files=files, data=payload, headers=secure_client_headers)

    # check response
    assert response.status_code == 200

    # check memory contents
    declarative_memories = get_declarative_memory_contents(secure_client, secure_client_headers)
    assert len(declarative_memories) == 7
    for dm in declarative_memories:
        assert "when" in dm["metadata"]
        assert "source" in dm["metadata"]
        # compare with the metadata of the file
        for k, v in metadata[dm["metadata"]["source"]].items():
            assert dm["metadata"][k] == v
