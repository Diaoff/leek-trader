import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.user import User
from app.core.auth import get_password_hash





@pytest.fixture
def test_user(db: Session):
    """创建测试用户"""
    hashed_password = get_password_hash("pass")
    user = User(
        tenant_id="local",
        username="testuser",
        email="test@example.com",
        password_hash=hashed_password,
        full_name="Test User",
        is_active=True,
        is_superuser=False
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def test_superuser(db: Session):
    """创建测试超级用户"""
    hashed_password = get_password_hash("pass")
    user = User(
        tenant_id="local",
        username="admintest",
        email="admin@example.com",
        password_hash=hashed_password,
        full_name="Admin User",
        is_active=True,
        is_superuser=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_register(client: TestClient):
    """测试用户注册"""
    response = client.post(
        "/api/v1/auth/register",
        json={
            "username": "newuser",
            "email": "newuser@example.com",
            "password": "newpassword",
            "full_name": "New User"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "newuser"
    assert data["email"] == "newuser@example.com"
    assert data["full_name"] == "New User"
    assert "id" in data


def test_login(client: TestClient, test_user: User):
    """测试用户登录"""
    response = client.post(
        "/api/v1/auth/login",
        data={
            "username": "testuser",
            "password": "pass"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_login_invalid_credentials(client: TestClient):
    """测试无效登录凭证"""
    response = client.post(
        "/api/v1/auth/login",
        data={
            "username": "invaliduser",
            "password": "invalidpassword"
        }
    )
    assert response.status_code == 401


def test_get_me(client: TestClient, test_user: User):
    """测试获取当前用户信息"""
    # 先登录获取token
    login_response = client.post(
        "/api/v1/auth/login",
        data={
            "username": "testuser",
            "password": "pass"
        }
    )
    token = login_response.json()["access_token"]
    
    # 使用token获取用户信息
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "testuser"
    assert data["email"] == "test@example.com"


def test_update_me(client: TestClient, test_user: User):
    """测试更新当前用户信息"""
    # 先登录获取token
    login_response = client.post(
        "/api/v1/auth/login",
        data={
            "username": "testuser",
            "password": "pass"
        }
    )
    token = login_response.json()["access_token"]
    
    # 更新用户信息
    response = client.put(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "full_name": "Updated Test User",
            "email": "updated@example.com"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["full_name"] == "Updated Test User"
    assert data["email"] == "updated@example.com"


def test_get_users_superuser(client: TestClient, test_superuser: User):
    """测试超级用户获取用户列表"""
    # 先登录获取token
    login_response = client.post(
        "/api/v1/auth/login",
        data={
            "username": "admintest",
            "password": "pass"
        }
    )
    token = login_response.json()["access_token"]
    
    # 获取用户列表
    response = client.get(
        "/api/v1/auth/users",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_get_users_non_superuser(client: TestClient, test_user: User):
    """测试普通用户获取用户列表（应该失败）"""
    # 先登录获取token
    login_response = client.post(
        "/api/v1/auth/login",
        data={
            "username": "testuser",
            "password": "pass"
        }
    )
    token = login_response.json()["access_token"]
    
    # 尝试获取用户列表
    response = client.get(
        "/api/v1/auth/users",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 403
