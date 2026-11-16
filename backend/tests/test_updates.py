"""Notice of a newer app version: no network, a fake Fetcher stands in for GitHub."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.updates import LATEST_PAGE, UpdateNotice, is_newer, parse_latest_version
from tests.conftest import HOST, PORT
from tests.fakes import FakeFetcher

TAG_URL = "https://github.com/nicosmico/youtube-downloader/releases/tag"


def published(tag: str) -> FakeFetcher:
    fetcher = FakeFetcher()
    fetcher.add(LATEST_PAGE, f"{TAG_URL}/{tag}".encode())
    return fetcher


class Published:
    def __init__(self) -> None:
        self.events: list[tuple[str, object]] = []

    def __call__(self, name: str, data: object) -> None:
        self.events.append((name, data))


# -- versions and Location ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("published_version", "current", "newer"),
    [
        ("0.2.2", "0.2.1", True),
        ("0.10.0", "0.9.0", True),
        ("1.0.0", "0.99.99", True),
        ("0.2.1", "0.2.1", False),
        ("0.2.0", "0.2.1", False),
        ("0.9.0", "0.10.0", False),
    ],
)
def test_versions_compare_numerically(published_version: str, current: str, newer: bool) -> None:
    assert is_newer(published_version, current) is newer


def test_parses_the_tag_of_the_location() -> None:
    assert parse_latest_version(f"{TAG_URL}/v0.2.2") == "0.2.2"
    assert parse_latest_version(f"{TAG_URL}/v0.10.0") == "0.10.0"


@pytest.mark.parametrize(
    "location",
    [
        f"{TAG_URL}/0.2.2",  # no `v`
        f"{TAG_URL}/v0.2",
        f"{TAG_URL}/v0.2.2-beta",
        f"{TAG_URL}/latest",
        "https://github.com/someone-else/youtube-downloader/releases/tag/v9.9.9",
        "https://github.com/nicosmico/youtube-downloader/releases",
        "https://github.com/login?return_to=%2Fnicosmico",
        "",
    ],
)
def test_rejects_an_unexpected_location(location: str) -> None:
    with pytest.raises(ValueError):
        parse_latest_version(location)


# -- the checker --------------------------------------------------------------------------------


def check(tag: str, current: str = "0.2.1") -> tuple[UpdateNotice, Published]:
    out = Published()
    notice = UpdateNotice(fetcher=published(tag), publish=out, current_version=current)
    notice.check()
    return notice, out


def test_a_newer_release_is_remembered_and_published() -> None:
    notice, out = check("v0.2.2")

    expected = {"version": "0.2.2", "url": f"{TAG_URL}/v0.2.2"}
    assert notice.update == expected
    assert out.events == [("app.update", expected)]


def test_the_url_is_built_from_the_tag_not_copied_from_the_location() -> None:
    fetcher = FakeFetcher()
    fetcher.add(LATEST_PAGE, f"{TAG_URL}/v0.3.0?utm=x#frag".encode())
    notice = UpdateNotice(fetcher=fetcher, publish=Published(), current_version="0.2.1")
    notice.check()

    assert notice.update == {"version": "0.3.0", "url": f"{TAG_URL}/v0.3.0"}


@pytest.mark.parametrize(("tag", "current"), [("v0.2.1", "0.2.1"), ("v0.2.0", "0.2.1")])
def test_no_notice_when_the_release_is_equal_or_older(tag: str, current: str) -> None:
    notice, out = check(tag, current)

    assert notice.update is None
    assert out.events == []


def test_ten_is_newer_than_nine() -> None:
    notice, _ = check("v0.10.0", current="0.9.0")

    assert notice.update is not None


def test_a_network_failure_shows_nothing_and_does_not_raise(
    caplog: pytest.LogCaptureFixture,
) -> None:
    fetcher = FakeFetcher()
    fetcher.failing.add(LATEST_PAGE)
    out = Published()
    notice = UpdateNotice(fetcher=fetcher, publish=out, current_version="0.2.1")

    with caplog.at_level(logging.INFO, logger="app.updates"):
        notice.check()

    assert notice.update is None
    assert out.events == []
    assert "sin conexión" in caplog.text


def test_an_unexpected_redirect_shows_nothing_and_does_not_raise() -> None:
    fetcher = FakeFetcher()
    fetcher.add(LATEST_PAGE, b"https://github.com/login")
    out = Published()
    notice = UpdateNotice(fetcher=fetcher, publish=out, current_version="0.2.1")

    notice.check()

    assert notice.update is None
    assert out.events == []


def test_a_failure_while_publishing_is_swallowed() -> None:
    def broken(name: str, data: object) -> None:
        raise RuntimeError("boom")

    notice = UpdateNotice(fetcher=published("v0.2.2"), publish=broken, current_version="0.2.1")

    notice.check()  # must not raise


# -- wiring -------------------------------------------------------------------------------------


@pytest.fixture
def make_update_client(data_dir: Path, download_dir: Path, static_dir: Path, engine, events):
    def factory(fetcher: FakeFetcher, **kwargs) -> TestClient:
        options = {
            "data_dir": data_dir,
            "port": PORT,
            "static_dir": static_dir,
            "engine": engine,
            "download_dir": download_dir,
            "broadcaster": events,
            "app_version": "0.2.1",
            "update_fetcher": fetcher,
            "spawn_update_check": lambda fn: fn(),
        }
        app = create_app(**{**options, **kwargs})
        return TestClient(app, base_url=f"http://{HOST}")

    return factory


def test_health_has_no_update_by_default(client: TestClient) -> None:
    assert client.get("/api/health").json()["update"] is None


def test_health_includes_the_update_and_the_event_is_published(make_update_client, events) -> None:
    fetcher = published("v0.2.2")

    with make_update_client(fetcher, update_check=True) as client:
        update = client.get("/api/health").json()["update"]

    expected = {"version": "0.2.2", "url": f"{TAG_URL}/v0.2.2"}
    assert update == expected
    assert events.named("app.update") == [expected]
    assert fetcher.requests == [LATEST_PAGE]


def test_health_has_no_update_when_up_to_date(make_update_client, events) -> None:
    with make_update_client(published("v0.2.1"), update_check=True) as client:
        assert client.get("/api/health").json()["update"] is None

    assert events.named("app.update") == []


def test_a_failing_check_does_not_get_in_the_way_of_the_app(make_update_client) -> None:
    fetcher = FakeFetcher()
    fetcher.failing.add(LATEST_PAGE)

    with make_update_client(fetcher, update_check=True) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["update"] is None


def test_the_check_runs_in_the_background_not_in_the_startup(make_update_client) -> None:
    spawned = []
    fetcher = published("v0.2.2")

    with make_update_client(fetcher, update_check=True, spawn_update_check=spawned.append):
        assert fetcher.requests == []  # handed to the background, not run by the startup
        assert len(spawned) == 1


def test_a_disabled_check_makes_no_request(make_update_client, events) -> None:
    fetcher = published("v0.2.2")

    with make_update_client(fetcher, update_check=False) as client:
        assert client.get("/api/health").json()["update"] is None

    assert fetcher.requests == []
    assert events.named("app.update") == []


# -- UPDATE_CHECK -------------------------------------------------------------------------------


def test_update_check_is_on_by_default_and_off_with_zero() -> None:
    base = {"DATA_DIR": "/tmp/x"}
    assert Settings.from_env(base).update_check is True
    assert Settings.from_env({**base, "UPDATE_CHECK": "1"}).update_check is True
    assert Settings.from_env({**base, "UPDATE_CHECK": "0"}).update_check is False
