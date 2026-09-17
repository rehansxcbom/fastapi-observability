from unittest.mock import AsyncMock, MagicMock

import pytest

# FIX: Import ASGITransport to properly wrap the ASGI application
from httpx2 import ASGITransport, AsyncClient
from sqlalchemy.exc import OperationalError

from main import app, get_session


@pytest.fixture
async def async_client():
    """
    Creates a reusable asynchronous test client.
    Bypasses the network and calls the FastAPI app directly in memory.
    """
    # FIX: Wrap the FastAPI app using ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.mark.asyncio
async def test_read_root(async_client: AsyncClient):
    """Test the standard GET health endpoint"""
    response = await async_client.get("/")

    assert response.status_code == 200
    assert response.json() == {"message": "Hello, telemetry!"}


@pytest.mark.asyncio
async def test_record_metrics_success(async_client: AsyncClient):
    """Test the POST endpoint and verify database interactions"""
    mock_session = AsyncMock()
    mock_session.add_all = MagicMock()

    app.dependency_overrides[get_session] = lambda: mock_session

    response = await async_client.post(
        "/metrics/", json=[{"server_id": "api-node-01", "cpu_utilization": 50.0}]
    )

    assert response.status_code == 201
    assert response.json() == {"status": "1 metrics recorded successfully"}

    mock_session.add_all.assert_called_once()
    mock_session.commit.assert_called_once()
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_record_metrics_db_failure_is_masked(async_client: AsyncClient):
    """Test that underlying database crashes do not leak sensitive SQL data to users"""
    mock_session = AsyncMock()
    mock_session.add_all = MagicMock()
    mock_session.commit.side_effect = OperationalError("DB is down", [], None)

    app.dependency_overrides[get_session] = lambda: mock_session

    response = await async_client.post(
        "/metrics/", json=[{"server_id": "api-node-01", "cpu_utilization": 50.0}]
    )

    assert response.status_code == 500
    assert "Internal server error" in response.json()["detail"]
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_record_metrics_validation_error(async_client: AsyncClient):
    """Test that Pydantic properly blocks physically impossible CPU metrics"""
    mock_session = AsyncMock()
    mock_session.add_all = MagicMock()
    app.dependency_overrides[get_session] = lambda: mock_session

    # We trigger a 422 by sending an impossible CPU percentage (150.0)
    response = await async_client.post(
        "/metrics/", json=[{"server_id": "api-node-01", "cpu_utilization": 150.0}]
    )

    assert response.status_code == 422
    assert "cpu_utilization" in response.text
    app.dependency_overrides.clear()
