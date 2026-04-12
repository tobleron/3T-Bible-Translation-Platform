from fastapi.testclient import TestClient

from ttt_webapp.app import app


def test_home_loads() -> None:
    with TestClient(app) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert "TTT Browser Workbench" in response.text


def test_settings_loads() -> None:
    with TestClient(app) as client:
        response = client.get("/settings")
        assert response.status_code == 200
        assert "Endpoint and prompt control" in response.text
