"""Exemption rules TS-E1..TS-E6: framework entry points are never reported."""

from __future__ import annotations

import posixpath

from graveyard.analyzers.typescript.packages import PackageIndex
from graveyard.analyzers.typescript.records import TsClass, TsFunction

_NEXT_FILES = frozenset(
    "page layout template loading error global-error not-found default route middleware "
    "instrumentation sitemap robots manifest opengraph-image twitter-image icon "
    "apple-icon".split()
)
_NEXT_NAMES = frozenset(
    "GET POST PUT PATCH DELETE HEAD OPTIONS generateMetadata generateStaticParams "
    "generateViewport generateImageMetadata generateSitemaps middleware register "
    "onRequestError".split()
)
_PAGES_NAMES = frozenset(
    "getServerSideProps getStaticProps getStaticPaths getInitialProps reportWebVitals".split()
)
_ROUTES_NAMES = frozenset(
    "loader action meta links headers handle shouldRevalidate ErrorBoundary HydrateFallback "
    "clientLoader clientAction".split()
)
_SVELTE_FILES = frozenset({"+page", "+layout", "+server", "+page.server", "+layout.server"})
_SVELTE_NAMES = frozenset({"load", "actions", "prerender", "entries"})
_DEFAULT_DIRS = ("routes", "api", "functions", "netlify/functions", "supabase/functions")
_ENTRY_FILES = frozenset(
    "main index server app worker sw service-worker background content".split()
)
_METHODS = frozenset(
    "render componentDidMount componentDidUpdate componentWillUnmount shouldComponentUpdate "
    "getSnapshotBeforeUpdate componentDidCatch getDerivedStateFromProps getDerivedStateFromError "
    "ngOnInit ngOnDestroy ngOnChanges ngAfterViewInit ngAfterContentInit ngDoCheck "
    "connectedCallback disconnectedCallback attributeChangedCallback adoptedCallback "
    "onModuleInit onModuleDestroy onApplicationBootstrap canActivate intercept transform use "
    "catch toJSON toString valueOf then".split()
)


def _in_dir(dirs: list[str], wanted: str) -> bool:
    """True if `wanted` (one or more segments) is a whole-segment run in the directory path."""
    want = wanted.split("/")
    return any(dirs[i : i + len(want)] == want for i in range(len(dirs) - len(want) + 1))


def _export_rule(func: TsFunction, file_path: str, packages: PackageIndex) -> str | None:
    """Rules about exports; only exported, non-method functions qualify."""
    if func.is_method or not (func.is_exported or func.is_default):
        return None
    dirs = posixpath.dirname(file_path).split("/") if "/" in file_path else []
    base = posixpath.basename(file_path)
    stem = posixpath.splitext(base)[0]  # `+page.server.ts` -> `+page.server`
    named = func.name if func.is_exported and not func.is_default else None
    if func.is_default:
        if stem in _NEXT_FILES or _in_dir(dirs, "pages"):
            return "TS-E1"
    elif stem in _NEXT_FILES and named in _NEXT_NAMES:
        return "TS-E1"
    elif _in_dir(dirs, "pages") and named in _PAGES_NAMES:
        return "TS-E1"
    if named in _ROUTES_NAMES and _in_dir(dirs, "routes"):
        return "TS-E2"
    if named in _SVELTE_NAMES and stem in _SVELTE_FILES:
        return "TS-E2"
    if func.is_default and any(_in_dir(dirs, d) for d in _DEFAULT_DIRS):
        return "TS-E2"
    if func.is_default and stem in _ENTRY_FILES:
        pkg = packages.package_for(file_path)
        root = pkg.dir if pkg is not None else ""
        if posixpath.dirname(file_path) in {root, posixpath.join(root, "src")}:
            return "TS-E3"
    return None


def exempt_rule(
    func: TsFunction, cls: TsClass | None, file_path: str, packages: PackageIndex
) -> str | None:
    """The first TS-E rule exempting `func` (defined in `cls` if a method), or None."""
    if func.body_kind == "stub" or func.is_abstract:
        return "TS-E6"
    rule = _export_rule(func, file_path, packages)
    if rule is not None:
        return rule
    if func.is_method:
        if func.name in _METHODS:
            return "TS-E4"
        if func.decorators or (cls is not None and cls.decorators):
            return "TS-E5"
    return None
