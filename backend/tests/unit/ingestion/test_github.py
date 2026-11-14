import httpx
import pytest

from graveyard import config
from graveyard.ingestion import github
from graveyard.models import IngestError, RepoRef

REF = RepoRef("o", "r")


def client_for(handler, seen: list[httpx.Request]) -> httpx.Client:
    def wrapped(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    return httpx.Client(transport=httpx.MockTransport(wrapped))


@pytest.fixture(autouse=True)
def no_token(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)


def fetch(handler):
    seen: list[httpx.Request] = []
    size = github.fetch_repo_size_kb(REF, client_for(handler, seen))
    assert len(seen) == 1
    return size, seen[0]


def test_ok_small():
    size, req = fetch(lambda r: httpx.Response(200, json={"size": 1234}))
    assert size == 1234
    assert str(req.url) == "https://api.github.com/repos/o/r"
    assert req.headers["user-agent"] == "graveyard"
    assert req.headers["accept"] == "application/vnd.github+json"
    assert "authorization" not in req.headers
    assert github.check_size(REF, size) == []


def test_over_limit(monkeypatch):
    monkeypatch.setattr(config, "MAX_REPO_SIZE_KB", 100 * 1024)
    size, _ = fetch(lambda r: httpx.Response(200, json={"size": 840 * 1024}))
    with pytest.raises(IngestError) as exc:
        github.check_size(REF, size)
    assert exc.value.code == "repo_too_large"
    assert "840 MB" in exc.value.message and "100 MB" in exc.value.message


def test_no_limit_means_no_error(monkeypatch):
    monkeypatch.setattr(config, "MAX_REPO_SIZE_KB", None)
    assert github.check_size(REF, 10**9) == []


@pytest.mark.parametrize("status", [403, 429, 404, 500])
def test_bad_status(status):
    size, _ = fetch(lambda r: httpx.Response(status, json={"message": "no"}))
    assert size is None
    assert github.check_size(REF, size) == ["Size pre-check skipped: GitHub API unavailable"]


def test_timeout():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    size, _ = fetch(handler)
    assert size is None


def test_bad_json():
    assert fetch(lambda r: httpx.Response(200, content=b"not json"))[0] is None
    assert fetch(lambda r: httpx.Response(200, json={"size": "big"}))[0] is None


def test_token_header(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    _, req = fetch(lambda r: httpx.Response(200, json={"size": 1}))
    assert req.headers["authorization"] == "Bearer tok"
