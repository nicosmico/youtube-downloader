from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import HOST


def test_root_serves_the_shell(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "shell" in response.text


def test_static_assets_are_served(client: TestClient) -> None:
    response = client.get("/main-abc.js")

    assert response.status_code == 200
    assert "console.log" in response.text


def test_client_side_routes_fall_back_to_index(client: TestClient) -> None:
    response = client.get("/historial/abc")

    assert response.status_code == 200
    assert "shell" in response.text


def test_path_traversal_does_not_leak_files(client: TestClient) -> None:
    response = client.get("/..%2fsecret.txt")

    assert "outside of static" not in response.text


def test_missing_build_explains_what_to_do(data_dir: Path, tmp_path: Path) -> None:
    app = create_app(data_dir=data_dir, port=54321, static_dir=tmp_path / "missing")
    client = TestClient(app, base_url=f"http://{HOST}")

    response = client.get("/")

    assert response.status_code == 503
    assert "npm run build" in response.text
