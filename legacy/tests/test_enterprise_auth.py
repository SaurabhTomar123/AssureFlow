import pytest
from fastapi.testclient import TestClient
from src.api.main import app
from src.auth.jwt_handler import (
    get_password_hash,
    verify_password,
    create_access_token,
    decode_access_token,
    RoleChecker,
)
from src.db.models import OrganizationUser

client = TestClient(app)


def test_password_hashing_and_verification():
    raw_pass = "SecurePass123"
    hashed = get_password_hash(raw_pass)
    assert hashed != raw_pass
    assert verify_password(raw_pass, hashed) is True
    assert verify_password("WrongPass", hashed) is False


def test_jwt_creation_and_decoding():
    payload = {"sub": "user-test-123", "tenant_id": "tenant-abc", "role": "STORE_MANAGER"}
    token = create_access_token(payload)
    assert isinstance(token, str)

    decoded = decode_access_token(token)
    assert decoded["sub"] == "user-test-123"
    assert decoded["tenant_id"] == "tenant-abc"
    assert decoded["role"] == "STORE_MANAGER"


def test_auth_login_seeded_admin():
    response = client.post(
        "/api/auth/login",
        json={"email": "admin@munimji.ai", "password": "MunimJi@2026"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["email"] == "admin@munimji.ai"
    assert data["role"] == "TENANT_ADMIN"
    assert data["tenant_id"] == "tenant-sharma-group"


def test_auth_login_invalid_credentials():
    response = client.post(
        "/api/auth/login",
        json={"email": "admin@munimji.ai", "password": "IncorrectPassword"},
    )
    assert response.status_code == 401
    assert "Invalid email or password" in response.json()["detail"]


def test_auth_register_new_tenant_and_user():
    register_payload = {
        "tenant_name": "Agrawal Hardware & Mills",
        "pan": "AGRAW1234F",
        "gstin": "07AGRAW1234F1Z5",
        "admin_email": "owner@agrawalmills.in",
        "admin_password": "AgrawalSecure2026",
        "admin_full_name": "Suresh Agrawal",
    }
    response = client.post("/api/auth/register", json=register_payload)
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "owner@agrawalmills.in"
    assert data["tenant_name"] == "Agrawal Hardware & Mills"
    assert data["role"] == "TENANT_ADMIN"
    assert "access_token" in data

    token = data["access_token"]
    me_resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["email"] == "owner@agrawalmills.in"
    assert me_data["full_name"] == "Suresh Agrawal"
    assert me_data["tenant_id"] == data["tenant_id"]


def test_auth_register_duplicate_email():
    register_payload = {
        "tenant_name": "Duplicate Test Co",
        "admin_email": "admin@munimji.ai",
        "admin_password": "Password123",
        "admin_full_name": "Duplicate Tester",
    }
    response = client.post("/api/auth/register", json=register_payload)
    assert response.status_code == 400
    assert "already exists" in response.json()["detail"]


def test_auth_me_unauthorized():
    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_role_checker_guard():
    checker = RoleChecker(["TENANT_ADMIN", "SENIOR_CA"])
    admin_user = OrganizationUser(id="1", role="TENANT_ADMIN")
    staff_user = OrganizationUser(id="2", role="STORE_STAFF")

    assert checker(admin_user) == admin_user
    with pytest.raises(Exception):
        checker(staff_user)
