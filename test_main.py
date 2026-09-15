from fastapi.testclient import TestClient

from main import app

# Create a test client using your FastAPI app
client = TestClient(app)


def test_read_root():
    # Simulate a GET request to the root endpoint
    response = client.get("/")

    # Assert the HTTP status code is 200 (OK)
    assert response.status_code == 200

    # Assert the JSON response matches exactly what we expect
    assert response.json() == {"message": "Hello, telemetry!"}
