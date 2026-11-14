import pytest

from graveyard.ingestion.url import parse_repo_url
from graveyard.models import IngestError

ACCEPTED = [
    ("https://github.com/o/r", "o", "r"),
    ("http://github.com/o/r", "o", "r"),
    ("github.com/o/r", "o", "r"),
    ("www.github.com/o/r", "o", "r"),
    ("https://www.github.com/o/r", "o", "r"),
    ("https://github.com/o/r/", "o", "r"),
    ("https://github.com/o/r.git", "o", "r"),
    ("github.com/o/r.git/", "o", "r"),
    ("github.com/o/r/tree/dev/src", "o", "r"),
    ("https://github.com/o/r?tab=readme", "o", "r"),
    ("https://github.com/o/r#readme", "o", "r"),
    ("https://github.com/o/r.git?x=1#y", "o", "r"),
    ("git@github.com:o/r.git", "o", "r"),
    ("git@github.com:o/r", "o", "r"),
    ("  https://github.com/o/r \n", "o", "r"),
    ("HTTPS://GitHub.COM/Foo/Bar", "Foo", "Bar"),
    ("github.com/a-b/c.d_e-f", "a-b", "c.d_e-f"),
    ("github.com/o/.github", "o", ".github"),
]

REJECTED = [
    "https://gitlab.com/a/b",
    "https://github.com.evil.com/o/r",
    "https://evilgithub.com/o/r",
    "",
    "   ",
    "https://github.com/" + "a" * 300 + "/r",
    "github.com/-bad/r",
    "github.com/" + "a" * 40 + "/r",
    "github.com/o/..",
    "github.com/o/.",
    "github.com/o/.git",
    "github.com/o/a.git.git",
    "https://user:pw@github.com/o/r",
    "https://user@github.com/o/r",
    "https://github.com:8080/o/r",
    "github.com:443/o/r",
    "ftp://github.com/o/r",
    "ssh://git@github.com/o/r.git",
    "github.com/onlyowner",
    "github.com/onlyowner/",
    "github.com//r",
    "github.com/o/r r",
    "github .com/o/r",
    "github.com/o/r%20x",
    "git@gitlab.com:o/r.git",
    "https://[github.com/o/r",
    "https://github.com\\@evil.com/o/r",
]


@pytest.mark.parametrize(("raw", "owner", "repo"), ACCEPTED)
def test_accepts(raw, owner, repo):
    ref = parse_repo_url(raw)
    assert (ref.owner, ref.repo) == (owner, repo)
    assert ref.canonical_url == f"https://github.com/{owner}/{repo}"


@pytest.mark.parametrize("raw", REJECTED)
def test_rejects(raw):
    with pytest.raises(IngestError) as exc:
        parse_repo_url(raw)
    assert exc.value.code == "invalid_url"


def test_foreign_host_message_names_github():
    with pytest.raises(IngestError) as exc:
        parse_repo_url("https://gitlab.com/a/b")
    assert "GitHub" in exc.value.message


def test_repo_length_boundary():
    prefix = "github.com/o/"
    assert parse_repo_url(prefix + "r" * 100).repo == "r" * 100
    with pytest.raises(IngestError):
        parse_repo_url(prefix + "r" * 101)
