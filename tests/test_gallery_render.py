"""Every gallery page must actually render in a browser.

``AppTest`` cannot do this: it has no browser, and a Streamlit custom component call
simply returns its default there, so a component that throws in JavaScript or paints
nothing at all still passes. This module drives a real Chromium against a running
gallery, which is the only layer that can catch a blank or broken component.

It also writes a screenshot per page, which doubles as the gallery's own imagery.

Skipped unless Playwright is installed:
    pip install playwright && playwright install chromium
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
GALLERY_DIR = REPO_ROOT / "gallery"
CONTENT_DIR = GALLERY_DIR / "content"
SCREENSHOT_DIR = Path(
    os.environ.get("GALLERY_SCREENSHOT_DIR", REPO_ROOT / "screenshots")
)

sync_playwright = pytest.importorskip(
    "playwright.sync_api", reason="Playwright not installed"
).sync_playwright

# Streamlit derives a page's URL slug from its filename; "home" is the default page.
PAGE_SLUGS: list[str] = sorted(
    p.stem for p in CONTENT_DIR.glob("*.py") if p.stem != "home"
)

# Console noise that is not a defect.
IGNORED_CONSOLE = (
    "Failed to load resource",  # favicon and similar
    "use_container_width",
    "deprecat",
    # Tabulator warns *and* rejects when asked to scroll to a row that is not currently
    # in the rendered viewport, which happens on pages where a table auto-selects a row
    # on first load. The table still renders and the selection still applies. It arrives
    # as an unhandled rejection rather than a console error, hence `record` below.
    "Scroll Error - Row not visible",
)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_painted_component(page, timeout_ms: int) -> bool:
    """Poll the component iframes until one has drawn something.

    Components render inside their own iframe and draw asynchronously, so there is no
    single selector on the host page to wait for. Polling the child frames is what
    distinguishes "the component drew" from "Streamlit laid out an empty box".
    """
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        for frame in page.frames:
            if frame == page.main_frame:
                continue
            try:
                if frame.locator("canvas, svg, table, .tabulator").count() > 0:
                    return True
            except Exception:  # noqa: BLE001 - frames detach as Streamlit re-renders
                continue
        page.wait_for_timeout(500)
    return False


@pytest.fixture(scope="module")
def gallery_server(tmp_path_factory) -> Iterator[str]:
    """Run the real gallery app and yield its base URL."""
    port = _free_port()
    cache = tmp_path_factory.mktemp("gallery-cache")
    env = {
        **os.environ,
        "GALLERY_CACHE_DIR": str(cache),
        "STREAMLIT_BROWSER_GATHER_USAGE_STATS": "false",
        "STREAMLIT_SERVER_HEADLESS": "true",
    }
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(GALLERY_DIR / "app.py"),
            "--server.port",
            str(port),
            "--server.address",
            "127.0.0.1",
            "--server.headless",
            "true",
        ],
        cwd=str(REPO_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    base_url = f"http://127.0.0.1:{port}"
    try:
        import urllib.error
        import urllib.request

        for _ in range(120):
            if process.poll() is not None:
                output = (process.stdout.read() or b"").decode(errors="replace")
                pytest.fail(f"Gallery server exited early:\n{output[-4000:]}")
            try:
                with urllib.request.urlopen(
                    f"{base_url}/_stcore/health", timeout=2
                ) as r:
                    if r.status == 200:
                        break
            except (urllib.error.URLError, OSError):
                time.sleep(1)
        else:
            pytest.fail("Gallery server did not become healthy within 120s")

        yield base_url
    finally:
        process.terminate()
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:  # pragma: no cover
            process.kill()


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as playwright:
        instance = playwright.chromium.launch()
        yield instance
        instance.close()


def _load_and_check(browser, base_url: str, slug: str, screenshot: bool):
    """Load one page once. Returns (painted, console errors)."""
    page = browser.new_page(viewport={"width": 1440, "height": 1200})
    errors: list[str] = []

    def record(text: str) -> None:
        """Keep one message unless it is known noise.

        Both channels filter through the same list. An unhandled promise rejection
        reaches Playwright as a ``pageerror`` rather than a console message, so a
        filter applied only to the console lets exactly the library's own known
        rejections through -- which is the opposite of what the list is for.
        """
        if not any(ignored in text for ignored in IGNORED_CONSOLE):
            errors.append(text)

    page.on(
        "console",
        lambda message: record(message.text) if message.type == "error" else None,
    )
    page.on("pageerror", lambda exc: record(str(exc)))

    try:
        # Never wait for "networkidle": Streamlit holds a websocket open for the
        # session's lifetime, so the network is never idle and the wait burns its
        # whole timeout on every page.
        page.goto(f"{base_url}/{slug}", wait_until="domcontentloaded", timeout=60_000)

        # Wait on things that actually settle: the page heading, then a component
        # iframe that has painted something.
        page.wait_for_selector("h1", timeout=60_000)
        # "attached", not "visible": a user click costs two Streamlit runs, and the
        # component iframe is remounted at zero height in between. Its visibility is
        # transient noise -- whether it painted is the signal, checked below.
        page.wait_for_selector("iframe", state="attached", timeout=60_000)

        painted = _wait_for_painted_component(page, timeout_ms=60_000)
        if screenshot and painted:
            page.screenshot(path=str(SCREENSHOT_DIR / f"{slug}.png"), full_page=True)
        return painted, errors
    finally:
        page.close()


@pytest.mark.parametrize("slug", PAGE_SLUGS)
def test_page_renders_without_console_errors(
    browser, gallery_server, slug: str
) -> None:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

    # Load twice before failing. Under load, a page occasionally emits a transient
    # error while Streamlit's websocket settles; genuine breakage reproduces on every
    # load, a flake does not. Retrying keeps a red build meaningful.
    attempts = 2
    for attempt in range(1, attempts + 1):
        painted, errors = _load_and_check(
            browser, gallery_server, slug, screenshot=True
        )
        if painted and not errors:
            return
        if attempt == attempts:
            assert painted, f"{slug}: component iframe rendered nothing visible"
            assert not errors, (
                f"{slug}: browser console errors on {attempts} consecutive loads: "
                f"{errors[:5]}"
            )


def test_pages_were_discovered() -> None:
    assert PAGE_SLUGS, "No gallery pages found to render"
