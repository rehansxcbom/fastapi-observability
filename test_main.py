from unittest.mock import patch

from fastapi.testclient import TestClient

# 1. Mock the database engine and session BEFORE importing the app.
# This prevents the FastAPI 'lifespan' from crashing when it tries
# to connect to TimescaleDB during the test setup.
with patch("main.engine"), patch("main.Session"):
    from main import app

client = TestClient(app)


def test_read_item():
    """Test the standard GET endpoint"""
    response = client.get("/items/42")

    assert response.status_code == 200
    assert response.json() == {"item_id": 42, "status": "Found"}


@patch("main.Session")
def test_record_metric(mock_session):
    """Test the POST endpoint and verify database interactions"""

    # Setup our fake database session
    mock_db = mock_session.return_value.__enter__.return_value

    # Test payload
    payload = {"server_id": "test-node-01", "cpu_utilization": 55.5}

    # Make the request
    response = client.post("/metrics/", json=payload)

    # Assert the API returned the correct response
    assert response.status_code == 200
    assert response.json() == {"status": "Metric recorded successfully"}

    # Assert our code actually attempted to save the data to the database!
    mock_db.add.assert_called_once()
    mock_db.commit.assert_called_once()
