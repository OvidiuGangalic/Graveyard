import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from graveyard.ingestion.url import parse_repo_url
from graveyard.models import IngestError

OWNERS = st.from_regex(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})", fullmatch=True)
REPOS = st.from_regex(r"[A-Za-z0-9._-]{1,100}", fullmatch=True).filter(
    lambda r: r not in (".", "..") and not r.endswith(".git")
)
PREFIXES = st.sampled_from(
    [
        "https://github.com/",
        "http://github.com/",
        "github.com/",
        "www.github.com/",
        "HTTPS://WWW.GitHub.com/",
    ]
)
SUFFIXES = st.sampled_from(
    ["", "/", ".git", ".git/", "/tree/dev/src", "?tab=x", "#frag", ".git?a=b"]
)
HOST_LABEL = st.from_regex(r"[a-z][a-z0-9]{0,10}", fullmatch=True)
TLD = st.sampled_from(["com", "org", "io", "net"])


@pytest.mark.property
@settings(max_examples=100)
@given(OWNERS, REPOS, PREFIXES, SUFFIXES)
def test_p10_url_normalisation(owner, repo, prefix, suffix):
    """P10 (URL normalisation is idempotent). Parsing any accepted wrapper form of a valid
    (owner, repo) yields exactly that owner and repo, and re-parsing the canonical URL is stable.

    **Validates: Requirements 1.1, 1.4, 1.6.**
    """
    for raw in (prefix + owner + "/" + repo + suffix, f"git@github.com:{owner}/{repo}.git"):
        ref = parse_repo_url(raw)
        assert (ref.owner, ref.repo) == (owner, repo)
        assert parse_repo_url(ref.canonical_url) == ref


@pytest.mark.property
@settings(max_examples=100)
@given(st.text(max_size=80))
def test_p10_idempotent_on_arbitrary_strings(s):
    """P10 (URL normalisation is idempotent). For any string that parses, the canonical URL
    parses back to the same ref; all other strings fail with `invalid_url`.

    **Validates: Requirements 1.1, 1.4, 1.6.**
    """
    try:
        ref = parse_repo_url(s)
    except IngestError as e:
        assert e.code == "invalid_url"
        return
    assert parse_repo_url(ref.canonical_url) == ref


@pytest.mark.property
@settings(max_examples=100)
@given(HOST_LABEL, TLD, OWNERS, REPOS, st.sampled_from(["https://", "http://", ""]))
def test_p10b_foreign_hosts_rejected(label, tld, owner, repo, scheme):
    """P10b (foreign hosts are rejected). For any host other than `github.com` or
    `www.github.com`, parsing fails with `invalid_url`.

    **Validates: Requirement 1.3.**
    """
    with pytest.raises(IngestError) as exc:
        parse_repo_url(f"{scheme}{label}.{tld}/{owner}/{repo}")
    assert exc.value.code == "invalid_url"
