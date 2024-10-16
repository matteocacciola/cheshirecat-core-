from tests.utils import get_declarative_memory_contents


def test_rabbithole_upload_invalid_url(secure_client, secure_client_headers):
    payload = {"url": "https://www.example.sbadabim"}
    response = secure_client.post("/rabbithole/web/", json=payload, headers=secure_client_headers)

    # check response
    assert response.status_code == 400
    json = response.json()
    assert json["detail"]["error"] == "Unable to reach the URL"

    # check declarative memory is still empty
    declarative_memories = get_declarative_memory_contents(secure_client, secure_client_headers)
    assert len(declarative_memories) == 0


def test_rabbithole_upload_url(secure_client, secure_client_headers):
    payload = {"url": "https://www.example.com"}
    response = secure_client.post("/rabbithole/web/", json=payload, headers=secure_client_headers)

    # check response
    assert response.status_code == 200
    json = response.json()
    assert json["info"] == "URL is being ingested asynchronously"
    assert json["url"] == payload["url"]

    # check declarative memories have been stored
    declarative_memories = get_declarative_memory_contents(secure_client, secure_client_headers)
    assert len(declarative_memories) == 1


def test_rabbithole_upload_url_with_metadata(secure_client, secure_client_headers):
    metadata = {
        "domain": "example.com",
        "scraped_with": "scrapy",
        "categories": ["example", "test"],
    }
    payload = {"url": "https://www.example.com", "metadata": metadata}

    response = secure_client.post("/rabbithole/web/", json=payload, headers=secure_client_headers)

    # check response
    assert response.status_code == 200
    json = response.json()
    assert json["info"] == "URL is being ingested asynchronously"
    assert json["url"] == payload["url"]

    # check declarative memories have been stored
    declarative_memories = get_declarative_memory_contents(secure_client, secure_client_headers)
    assert len(declarative_memories) == 1
    assert "when" in declarative_memories[0]["metadata"]
    assert "source" in declarative_memories[0]["metadata"]
    assert "title" in declarative_memories[0]["metadata"] # TODO: should we take this away?
    for key, value in metadata.items():
        assert declarative_memories[0]["metadata"][key] == value
