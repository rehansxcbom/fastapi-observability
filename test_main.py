from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx2 import ASGITransport, AsyncClient
from sqlalchemy.exc import OperationalError

from main import app, get_session


@pytest.fixture(autouse=True)
def mock_db_connections():
    with (
        patch("sqlalchemy.ext.asyncio.AsyncEngine.begin") as mock_begin,
        patch("main.AsyncSession") as mock_async_session,
    ):
        mock_begin.return_value.__aenter__.return_value = AsyncMock()

        mock_session_instance = AsyncMock()
        mock_session_instance.add = MagicMock()
        mock_async_session.return_value.__aenter__.return_value = mock_session_instance

        yield


@pytest.fixture
async def async_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.mark.asyncio
async def test_read_root(async_client: AsyncClient):
    response = await async_client.get("/")

    assert response.status_code == 200
    assert response.json() == {"message": "Hello, telemetry!"}


@pytest.mark.asyncio
async def test_record_server_metrics_success(async_client: AsyncClient):
    mock_session = AsyncMock()
    mock_session.add_all = MagicMock()

    app.dependency_overrides[get_session] = lambda: mock_session

    response = await async_client.post(
        "/server-metrics/",
        json=[{"user_id": "api-node-01", "user_token": 50.0}],
    )

    assert response.status_code == 201
    assert response.json() == {"status": "1 server metrics recorded successfully"}

    mock_session.add_all.assert_called_once()
    mock_session.commit.assert_called_once()
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_record_server_metrics_db_failure_is_masked(async_client: AsyncClient):
    """Test that underlying database crashes do not leak sensitive SQL data to users"""
    mock_session = AsyncMock()
    mock_session.add_all = MagicMock()
    mock_session.commit.side_effect = OperationalError("DB is down", [], None)

    app.dependency_overrides[get_session] = lambda: mock_session

    response = await async_client.post(
        "/server-metrics/",
        json=[{"user_id": "api-node-01", "user_token": 50.0}],
    )

    assert response.status_code == 500
    assert "Internal server error" in response.json()["detail"]
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_record_server_metrics_validation_error(async_client: AsyncClient):
    """Test that Pydantic properly blocks physically impossible user_token metrics"""
    mock_session = AsyncMock()
    mock_session.add_all = MagicMock()
    app.dependency_overrides[get_session] = lambda: mock_session

    response = await async_client.post(
        "/server-metrics/",
        json=[{"user_id": "api-node-01", "user_token": 150.0}],
    )

    assert response.status_code == 422
    assert "user_token" in response.text
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_record_request_metrics_success(async_client: AsyncClient):
    """Test that the new request-metrics endpoint correctly accepts valid payloads"""
    mock_session = AsyncMock()
    mock_session.add_all = MagicMock()

    app.dependency_overrides[get_session] = lambda: mock_session

    response = await async_client.post(
        "/request-metrics/",
        json=[
            {
                "user_id": "user-123",
                "request_code": 200,
                "request_duration_ms": 45.2,
                "method": "GET",
                "path": "/api/v1/data",
            }
        ],
    )

    assert response.status_code == 201
    assert response.json() == {"status": "1 request metrics recorded successfully"}

    mock_session.add_all.assert_called_once()
    mock_session.commit.assert_called_once()
    app.dependency_overrides.clear()
