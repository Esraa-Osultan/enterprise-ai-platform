def test_register_new_user(client):
    response = client.post(
        "/auth/register",
        json={"username": "alice", "email": "alice@valeo.com", "password": "password1"},
    )
    assert response.status_code == 201


def test_register_duplicate_username_fails(client):
    payload = {"username": "bob", "email": "bob@valeo.com", "password": "password1"}
    client.post("/auth/register", json=payload)
    response = client.post("/auth/register", json=payload)
    assert response.status_code == 400


def test_login_success_returns_token(client):
    client.post(
        "/auth/register",
        json={"username": "carol", "email": "carol@valeo.com", "password": "password1"},
    )
    response = client.post("/auth/login", data={"username": "carol", "password": "password1"})
    assert response.status_code == 200
    assert "access_token" in response.json()


def test_login_wrong_password_fails(client):
    client.post(
        "/auth/register",
        json={"username": "dave", "email": "dave@valeo.com", "password": "password1"},
    )
    response = client.post("/auth/login", data={"username": "dave", "password": "wrong"})
    assert response.status_code == 401


def test_protected_endpoint_requires_token(client):
    response = client.get("/documents")
    assert response.status_code == 401


def test_protected_endpoint_works_with_token(client, auth_headers):
    response = client.get("/documents", headers=auth_headers)
    assert response.status_code == 200
