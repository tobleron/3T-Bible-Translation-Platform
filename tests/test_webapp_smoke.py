from fastapi.testclient import TestClient

from ttt_webapp.app import app


def test_home_loads() -> None:
    with TestClient(app) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert "Tell The Truth Bible Translation Platform" in response.text
        assert response.headers.get("server-timing", "").startswith("app;dur=")
        assert response.headers.get("x-ttt-render-ms")


def test_settings_loads() -> None:
    with TestClient(app) as client:
        response = client.get("/settings")
        assert response.status_code == 200
        assert "Endpoint Configuration" in response.text


def test_static_interaction_layer_is_served() -> None:
    with TestClient(app) as client:
        response = client.get("/static/js/app_interactions.js")
        assert response.status_code == 200
        assert "TTTInteractions" in response.text

        bootstrap_response = client.get("/static/js/workspace_bootstrap.js")
        assert bootstrap_response.status_code == 200
        assert "TTTWorkspaceBootstrap" in bootstrap_response.text

        chat_response = client.get("/static/js/chat_stream_controller.js")
        assert chat_response.status_code == 200
        assert "TTTChatStreamController" in chat_response.text
