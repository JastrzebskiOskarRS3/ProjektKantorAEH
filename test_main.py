from fastapi.testclient import TestClient
import respx
import httpx
import pytest
from main import app
from database import engine
from sqlmodel import SQLModel

@pytest.fixture(autouse=True)
def clean_db():
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    yield
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)

client = TestClient(app)

def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200

@respx.mock
def test_nbp_integration():
    respx.get("https://api.nbp.pl/api/exchangerates/rates/a/USD/?format=json").mock(
        return_value=httpx.Response(200, json={
            "currency": "dolar amerykański",
            "code": "USD",
            "rates": [{"mid": 4.05}]
        })
    )
    response = client.get("/rates/USD")
    assert response.status_code == 200
    assert "mid" in response.json()

def test_register_user():
    response = client.post("/users/", json={"username": "testuser", "password": "testpass"})
    assert response.status_code == 201
    assert response.json()["message"] == "Użytkownik stworzony"

def test_register_duplicate_user():
    client.post("/users/", json={"username": "dupuser", "password": "testpass"})
    response = client.post("/users/", json={"username": "dupuser", "password": "testpass"})
    assert response.status_code == 400
    assert response.json()["detail"] == "Użytkownik już istnieje"

def test_login_success():
    client.post("/users/", json={"username": "loginuser", "password": "testpass"})
    response = client.post("/token", data={"username": "loginuser", "password": "testpass"})
    assert response.status_code == 200
    assert "access_token" in response.json()

def test_login_wrong_password():
    client.post("/users/", json={"username": "wrongpass", "password": "correctpass"})
    response = client.post("/token", data={"username": "wrongpass", "password": "wrongpass"})
    assert response.status_code == 401

def test_deposit_limit():
    client.post("/users/", json={"username": "deposituser", "password": "testpass"})
    token = client.post("/token", data={"username": "deposituser", "password": "testpass"}).json()["access_token"]
    response = client.post("/deposit?amount=99999", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 400
    assert "10 000" in response.json()["detail"]