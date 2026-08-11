def test_missing_api_key_is_rejected(client):
    response = client.get("/api/v1/courses")
    assert response.status_code == 401


def test_invalid_api_key_is_rejected(client):
    response = client.get("/api/v1/courses", headers={"X-API-Key": "wrong"})
    assert response.status_code == 401


def test_valid_api_key_is_accepted(client, auth_headers):
    response = client.get("/api/v1/courses", headers=auth_headers)
    assert response.status_code == 200

