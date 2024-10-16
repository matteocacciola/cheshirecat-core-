import os


def test_call(secure_client, secure_client_headers):
    response = secure_client.get("/static/", headers=secure_client_headers)
    assert response.status_code == 404


def test_call_specific_file(secure_client, secure_client_headers):
    static_file_name = "Meooow.txt"
    static_file_path = f"/app/cat/static/{static_file_name}"

    # ask for inexistent file
    response = secure_client.get(f"/static/{static_file_name}", headers=secure_client_headers)
    assert response.status_code == 404

    # insert file in static folder
    with open(static_file_path, "w") as f:
        f.write("Meow")

    response = secure_client.get(f"/static/{static_file_name}", headers=secure_client_headers)
    assert response.status_code == 200

    os.remove(static_file_path)
