from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.conftest import APP_HEADERS, PORT


class TestHostValidation:
    @pytest.mark.parametrize(
        "host", [f"127.0.0.1:{PORT}", f"localhost:{PORT}", f"LOCALHOST:{PORT}"]
    )
    def test_accepts_local_hosts_with_the_bound_port(self, client: TestClient, host: str) -> None:
        response = client.get("/api/health", headers={"Host": host})

        assert response.status_code == 200

    @pytest.mark.parametrize(
        "host",
        [
            "evil.example.com",
            f"evil.example.com:{PORT}",
            "192.168.1.20:54321",
            "127.0.0.1",
            f"127.0.0.1:{PORT + 1}",
            "[::1]:54321",
            "",
        ],
    )
    def test_rejects_any_other_host(self, client: TestClient, host: str) -> None:
        response = client.get("/api/health", headers={"Host": host})

        assert response.status_code == 403
        assert response.json()["code"] == "invalid_host"

    def test_applies_to_the_spa_too(self, client: TestClient) -> None:
        response = client.get("/", headers={"Host": "evil.example.com"})

        assert response.status_code == 403


class TestMutationProtection:
    @pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
    def test_mutations_require_the_app_header(self, client: TestClient, method: str) -> None:
        response = client.request(method, "/api/system/shutdown")

        assert response.status_code == 403
        assert response.json()["code"] == "missing_app_header"

    def test_a_wrong_header_value_is_rejected(self, client: TestClient) -> None:
        response = client.post(
            "/api/system/shutdown", headers={"X-Requested-With": "XMLHttpRequest"}
        )

        assert response.status_code == 403

    def test_reads_do_not_need_the_header(self, client: TestClient) -> None:
        assert client.get("/api/health").status_code == 200

    @pytest.mark.parametrize("origin", [f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}"])
    def test_local_origin_is_accepted(self, client: TestClient, origin: str) -> None:
        response = client.post("/api/system/shutdown", headers={**APP_HEADERS, "Origin": origin})

        assert response.status_code == 202

    @pytest.mark.parametrize(
        "origin",
        [
            "https://evil.example.com",
            "null",
            f"http://localhost:{PORT + 1}",
            f"https://127.0.0.1:{PORT}",
        ],
    )
    def test_foreign_origin_is_rejected(self, client: TestClient, origin: str) -> None:
        response = client.post("/api/system/shutdown", headers={**APP_HEADERS, "Origin": origin})

        assert response.status_code == 403
        assert response.json()["code"] == "invalid_origin"
