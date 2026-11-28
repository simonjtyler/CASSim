# Requirements traced here: FR-PWA-003
"""The published site is installable and works offline (FR-PWA-001 to FR-PWA-004).

Builds the real site with `tools.publish` (needs network for the vendored packages the first time),
serves it below /CASSim/ as a GitHub Pages project site would, and drives it in a browser.
"""

from __future__ import annotations

import json
import os
import re
import tarfile
import time
import zipfile
from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

import pytest
from PIL import Image, ImageChops
from playwright.sync_api import Browser, Page, expect
from test_flows_browser import AppPage
from tools import publish
from tools.flows import flow_settings, matches

pytestmark = pytest.mark.e2e


def wait_for(page: Page, js: str, seconds: float = 240) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if page.evaluate(js):
            return True
        page.wait_for_timeout(500)
    return False


def test_manifest_and_icons(site: tuple[Path, str]) -> None:
    """FR-PWA-001: manifest names the app, is standalone, and its icons exist."""
    dist, _ = site
    manifest = json.loads((dist / "manifest.webmanifest").read_text(encoding="utf-8"))
    assert manifest["display"] == "standalone"
    assert {"192x192", "512x512"} <= {i["sizes"] for i in manifest["icons"]}
    assert all((dist / i["src"]).is_file() for i in manifest["icons"])
    assert (dist / "favicon.png").is_file()  # the same artwork, linked by index.html
    html = (dist / "index.html").read_text(encoding="utf-8")
    assert html.count('rel="manifest"') == 1
    assert 'href="manifest.webmanifest"' in html
    assert manifest["name"] == "CASSim"
    assert "<title>CASSim</title>" in html
    assert 'apple-mobile-web-app-title" content="CASSim"' in html
    assert not (dist / "manifest.json").exists()


def test_loads_and_works_offline(browser: Browser, site: tuple[Path, str]) -> None:
    """FR-PWA-002/003: boots with no external requests, then reloads with the network off."""
    dist, url = site
    ctx = browser.new_context()
    page = ctx.new_page()
    external: set[str] = set()
    missing: set[str] = set()
    errors: list[str] = []
    page.on(
        "request",
        lambda r: (
            external.add(urlparse(r.url).netloc)
            if not r.url.startswith(("http://127.0.0.1", "blob:", "data:"))
            else None
        ),
    )
    page.on("response", lambda r: missing.add(r.url) if r.status == 404 else None)
    page.on(
        "console",
        lambda m: (
            errors.append(m.text[:300]) if "Traceback" in m.text or "init error" in m.text else None
        ),
    )
    page.goto(url, wait_until="load")
    assert page.locator("#cassim-splash").count() == 1  # the loading screen shows first
    assert wait_for(page, "!document.getElementById('cassim-splash')"), "app never started"
    page.wait_for_timeout(20000)  # the Python worker starts after the first frame
    assert not errors, errors
    assert page.locator("#cassim-offline").is_hidden()
    n = len(json.loads((dist / "precache.json").read_text(encoding="utf-8")))
    assert wait_for(
        page,
        "caches.keys().then(async k => k.length"
        " ? (await (await caches.open(k[0])).keys()).length : 0)"
        f".then(c => c >= {n})",
        120,
    ), "precache did not complete"
    page.reload(wait_until="load")
    page.wait_for_timeout(1500)
    assert page.evaluate("!!navigator.serviceWorker.controller")
    ctx.set_offline(True)
    page.reload(wait_until="load")
    assert wait_for(page, "!document.getElementById('cassim-splash')"), "offline reload failed"
    page.wait_for_timeout(20000)
    assert not errors, errors
    assert not external, external
    assert not missing, missing
    ctx.close()


def test_root_hosted_site_works_offline(browser: Browser, root_site: tuple[Path, str]) -> None:
    """FR-PWA-002: root-hosted builds also install and calculate without a network."""
    _, url = root_site
    context = browser.new_context(viewport={"width": 1100, "height": 700})
    try:
        page = context.new_page()
        page.goto(url, wait_until="load")
        assert wait_for(page, "document.getElementById('cassim-offline').dataset.state === 'ready'")
        context.set_offline(True)
        page.close()
        app = AppPage(context.new_page(), url)
        app.type_text("2+3")
        app.press("Enter")
        app.wait(lambda: app.results, "root-hosted offline calculation")
        assert app.results[-1] == "5"
    finally:
        context.close()


def test_redirected_index_allows_online_and_offline_launch(
    browser: Browser, redirecting_site: str
) -> None:
    """FR-PWA-002: a redirected cached index remains usable for navigation."""
    context = browser.new_context(viewport={"width": 1100, "height": 700})
    try:
        response = context.request.get(f"{redirecting_site}index.html", max_redirects=0)
        assert response.status == 308
        page = context.new_page()
        page.goto(redirecting_site, wait_until="load")
        assert wait_for(page, "document.getElementById('cassim-offline').dataset.state === 'ready'")
        page.close()

        page = context.new_page()
        page.goto(redirecting_site, wait_until="load")
        assert wait_for(page, "!document.getElementById('cassim-splash')")
        assert page.evaluate(
            """async () => {
              const key = (await caches.keys()).find(k => k.startsWith("cassim-"));
              return (await caches.open(key)).delete("index.html");
            }"""
        )
        page.close()

        page = context.new_page()
        page.goto(redirecting_site, wait_until="load")
        assert wait_for(page, "document.getElementById('cassim-offline').dataset.state === 'ready'")
        page.close()

        context.set_offline(True)
        app = AppPage(context.new_page(), redirecting_site)
        app.type_text("2+3")
        app.press("Enter")
        app.wait(lambda: app.results, "calculation after redirected offline launch")
        assert app.results[-1] == "5"
    finally:
        context.close()


def test_cas_after_host_failure_and_offline(
    browser: Browser,
    site: tuple[Path, str],
    failing_site: tuple[str, list[str], Callable[[str], None]],
) -> None:
    """FR-PWA-002/004: a cached installation evaluates after a failed update and offline."""
    dist, _ = site
    url, requests, fail = failing_site
    path = urlparse(url).path
    context = browser.new_context(viewport={"width": 1100, "height": 700})
    external: set[str] = set()
    context.on(
        "request",
        lambda request: (
            external.add(request.url)
            if urlparse(request.url).scheme in {"http", "https"}
            and urlparse(request.url).netloc != urlparse(url).netloc
            else None
        ),
    )

    def calculate(app: AppPage, expression: str, expected: str) -> None:
        app.page.keyboard.press("Control+a")
        app.page.keyboard.press("Delete")
        app.logs.clear()
        app.type_text(expression)
        app.press("Enter")
        app.wait(lambda: app.results, f"calculation of {expression}")
        assert matches(expected, app.results[-1], flow_settings({}), "canonical", 1e-7)

    def reject_update(page: Page) -> None:
        assert page.evaluate(
            """async () => {
              try {
                await (await navigator.serviceWorker.getRegistration()).update();
                return false;
              } catch (error) {
                return true;
              }
            }"""
        ), "service-worker update unexpectedly succeeded"
        assert f"{path}flutter_service_worker.js" in requests
        assert path not in requests

    try:
        page = context.new_page()
        app = AppPage(page, url)
        calculate(app, "2+3", "5")
        precache = json.loads((dist / "precache.json").read_text(encoding="utf-8"))
        assert wait_for(
            page,
            "caches.keys().then(async keys => {"
            " const name = keys.find(k => k.startsWith('cassim-'));"
            " if (!name) return false;"
            " const cache = await caches.open(name);"
            f" return (await Promise.all({json.dumps(precache)}.map(path => cache.match(path))))"
            ".every(Boolean);"
            "})",
        ), "precache did not complete"
        assert wait_for(page, "!!navigator.serviceWorker.controller")
        page.close()

        requests.clear()
        fail("error")
        page = context.new_page()
        app = AppPage(page, url)
        reject_update(page)
        calculate(app, "factor(x^2{R}-1)", "(x-1)*(x+1)")
        page.close()

        requests.clear()
        fail("block")
        page = context.new_page()
        app = AppPage(page, url)
        reject_update(page)
        calculate(app, "2+3", "5")
        page.close()

        context.set_offline(True)
        page = context.new_page()
        app = AppPage(page, url)
        calculate(app, "solve(x+2=5,x)", "x=3")
        assert not external, external
    finally:
        context.close()


def test_version_is_published(site: tuple[Path, str]) -> None:
    """FR-PWA-004: the build writes a version, and the worker's cache name carries it."""
    dist, _ = site
    version = json.loads((dist / "version.json").read_text(encoding="utf-8"))["version"]
    assert version.startswith(publish.project_version())
    assert f'CACHE_PREFIX + "{version}"' in (dist / "flutter_service_worker.js").read_text(
        encoding="utf-8"
    )
    assert "reload_update" in (dist / "index.html").read_text(encoding="utf-8")


def test_published_keyboard_guard_suppresses_only_cassim_collisions(
    browser: Browser, site: tuple[Path, str]
) -> None:
    page = browser.new_page()
    page.goto(site[1], wait_until="load")
    cases = page.evaluate(
        """() => {
          const send = (key, modifiers, target = window) => {
            const event = new KeyboardEvent("keydown", {
              key, bubbles: true, cancelable: true, composed: true, ...modifiers
            });
            target.dispatchEvent(event);
            return event.defaultPrevented;
          };
          const input = document.createElement("input");
          document.body.appendChild(input);
          return [
            send("s", {ctrlKey: true}),
            send("s", {metaKey: true}),
            send("S", {ctrlKey: true, shiftKey: true}),
            send("r", {ctrlKey: true}),
            send("ArrowLeft", {altKey: true}),
            send("F1", {}),
            send("F10", {shiftKey: true}),
            send("=", {ctrlKey: true}),
            send("F5", {}),
            send("p", {ctrlKey: true}),
            send("c", {ctrlKey: true}, input),
            send("s", {ctrlKey: true}, input),
          ];
        }"""
    )
    assert cases == [True, True, True, True, True, True, True, True, False, False, False, True]
    page.close()


def test_cassim_menu_shows_browser_attention_without_overlay(
    browser: Browser, site: tuple[Path, str]
) -> None:
    """FR-PWA-002/004: browser status reaches the app's menu and its attention indicator."""
    _, url = site
    app = AppPage(browser.new_page(viewport={"width": 1100, "height": 700}), url)
    page = app.page
    assert wait_for(page, "document.getElementById('cassim-offline').dataset.state === 'ready'")
    page.locator("flt-semantics-placeholder").evaluate("(element) => element.click()")
    button = page.get_by_role("button", name=re.compile("CASSim menu"))
    expect(button).to_be_attached()
    page.evaluate("""() => {
      const channel = new BroadcastChannel("cassim");
      channel.postMessage({op: "status", state: "unavailable",
        message: "Offline files are incomplete.", retry: true, updateReady: false});
    }""")
    expect(
        page.get_by_role("button", name=re.compile("CASSim menu: offline setup failed"))
    ).to_be_attached()
    assert page.locator("#cassim-offline").is_hidden()
    button.click()
    expect(page.get_by_text("Offline: unavailable")).to_be_attached()
    page.evaluate("""() => {
      const channel = new BroadcastChannel("cassim");
      channel.postMessage({op: "update", result: "downloading"});
    }""")
    expect(page.get_by_text(re.compile("Fetching update…"))).to_be_attached()
    page.evaluate("""() => {
      const channel = new BroadcastChannel("cassim");
      channel.postMessage({op: "status", state: "ready",
        message: "Ready for offline use.", retry: false, updateReady: true});
    }""")
    expect(page.get_by_text(re.compile("Reload to update"))).to_be_attached()
    expect(page.get_by_text("Reload update…", exact=True)).not_to_be_attached()


def test_cached_navigation_offers_and_applies_update(
    browser: Browser, failing_site: tuple[str, list[str], Callable[[str], None]]
) -> None:
    """FR-PWA-004: cached navigation still discovers and activates a new service worker."""
    url, _, change = failing_site
    context = browser.new_context(viewport={"width": 1100, "height": 700})
    try:
        page = context.new_page()
        page.goto(url, wait_until="load")
        assert wait_for(page, "!!navigator.serviceWorker.controller")
        page.evaluate("""() => {
          window.testBus = new BroadcastChannel("cassim");
          window.testBus.onmessage = e => {
            if (e.data.op === "status") window.pwaStatus = e.data;
          };
          window.testBus.postMessage({op: "hello"});
        }""")
        page.evaluate("caches.open('cassim-%2Fother%2F-other-version')")
        change("update")
        page.evaluate("navigator.serviceWorker.getRegistration().then(reg => reg.update())")
        assert wait_for(page, "window.pwaStatus && window.pwaStatus.updateReady"), (
            "new version was not offered"
        )
        assert page.locator("#cassim-offline").is_hidden()
        with page.expect_navigation(wait_until="load", timeout=150000):
            page.evaluate("window.testBus.postMessage({op: 'reload_update'})")
        assert wait_for(
            page,
            "caches.keys().then(keys => keys.includes('cassim-%2FCASSim%2F-test-update')"
            " && keys.includes('cassim-%2Fother%2F-other-version'))",
        )
        page.close()
        app = AppPage(context.new_page(), url)
        app.page.wait_for_timeout(1000)
        app.page.mouse.click(600, 150)
        app.type_text("2+3")
        app.press("Enter")
        app.wait(lambda: app.results, "calculation after update")
        assert app.results[-1] == "5"
    finally:
        context.close()


@pytest.mark.parametrize("failure", ["install-broken", "install-interrupted"])
def test_failed_precache_is_reported_and_can_be_retried(
    browser: Browser, failing_site: tuple[str, list[str], Callable[[str], None]], failure: str
) -> None:
    """FR-PWA-002: corrupt or interrupted assets cannot produce a ready status."""
    url, _, fail = failing_site
    fail(failure)
    context = browser.new_context()
    try:
        page = context.new_page()
        page.goto(url, wait_until="load")
        assert wait_for(
            page, "document.getElementById('cassim-offline').dataset.state === 'unavailable'"
        )
        assert not page.evaluate("!!navigator.serviceWorker.controller")
        fail("")
        page.evaluate("new BroadcastChannel('cassim').postMessage({op: 'retry_offline'})")
        assert wait_for(page, "document.getElementById('cassim-offline').dataset.state === 'ready'")
        context.set_offline(True)
        page.reload(wait_until="load")
        assert wait_for(page, "document.getElementById('cassim-offline').dataset.state === 'ready'")
    finally:
        context.close()


@pytest.mark.parametrize("failure", ["update-broken", "update-interrupted"])
def test_incomplete_update_leaves_working_cache(
    browser: Browser, failing_site: tuple[str, list[str], Callable[[str], None]], failure: str
) -> None:
    """FR-PWA-002/004: an incomplete update must not replace the active version."""
    url, _, fail = failing_site
    context = browser.new_context(viewport={"width": 1100, "height": 700})
    try:
        page = context.new_page()
        page.goto(url, wait_until="load")
        assert wait_for(page, "document.getElementById('cassim-offline').dataset.state === 'ready'")
        fail(failure)
        state = page.evaluate(
            """async () => {
              const reg = await navigator.serviceWorker.getRegistration();
              await reg.update();
              const worker = reg.installing;
              if (!worker) throw new Error("No installing worker");
              return await new Promise(resolve => {
                if (worker.state === "redundant") return resolve(worker.state);
                worker.addEventListener("statechange", () => {
                  if (worker.state === "redundant" || worker.state === "installed")
                    resolve(worker.state);
                });
              });
            }"""
        )
        assert state == "redundant"
        assert wait_for(
            page,
            "document.querySelector('#cassim-offline span').textContent.includes('Update failed')",
        )
        # The browser only guarantees the failed install's cache is removed eventually.
        assert wait_for(
            page,
            "caches.keys().then(keys => !keys.includes('cassim-%2FCASSim%2F-test-update'))",
        ), "failed update left its staging cache behind"
        context.set_offline(True)
        page.close()
        app = AppPage(context.new_page(), url)
        app.type_text("2+3")
        app.press("Enter")
        app.wait(lambda: app.results, "calculation after interrupted update")
        assert app.results[-1] == "5"
    finally:
        context.close()


def test_missing_cached_file_is_reported_and_repaired(
    browser: Browser, site: tuple[Path, str]
) -> None:
    """FR-PWA-002: missing cache entries are not reported as offline ready."""
    _, url = site
    context = browser.new_context()
    try:
        page = context.new_page()
        page.add_init_script(
            """if (navigator.storage && navigator.storage.persist) {
              const persist = navigator.storage.persist.bind(navigator.storage);
              navigator.storage.persist = () => {
                window.persistenceRequested = true;
                return persist();
              };
            }"""
        )
        page.goto(url, wait_until="load")
        assert wait_for(page, "document.getElementById('cassim-offline').dataset.state === 'ready'")
        assert page.evaluate(
            "!navigator.storage || !navigator.storage.persist"
            " || window.persistenceRequested === true"
        )
        assert page.evaluate(
            """async () => {
              const key = (await caches.keys()).find(k => k.startsWith("cassim-"));
              return await (await caches.open(key)).delete("pyodide/python.bat");
            }"""
        )
        page.reload(wait_until="load")
        assert wait_for(
            page, "document.getElementById('cassim-offline').dataset.state === 'unavailable'"
        )
        page.evaluate("new BroadcastChannel('cassim').postMessage({op: 'retry_offline'})")
        assert wait_for(page, "document.getElementById('cassim-offline').dataset.state === 'ready'")
        assert page.locator("#cassim-offline").is_hidden()
    finally:
        context.close()


def test_the_build_records_the_versions_it_ships(site: tuple[Path, str]) -> None:
    """The About box's versions: the UI worker's `bundle.py` names what was shipped, SymPy
    included, though only the engine worker holds SymPy."""
    dist, _ = site
    lock = publish.lock_file(dist)
    with tarfile.open(dist / "app.tar.gz") as archive:
        member = archive.extractfile("cassim/bundle.py")
        assert member is not None
        text = member.read().decode("utf-8")
    assert f"'CASSim': '{publish.project_version()}'" in text
    assert f"'SymPy': '{lock['packages']['sympy']['version']}'" in text
    assert f"'Pyodide': '{publish.pyodide_version(dist)}'" in text
    with zipfile.ZipFile(dist / "cassim.zip") as archive:  # the SymPy the engine really loads
        assert any(
            name.startswith(f"sympy-{lock['packages']['sympy']['version']}.dist-info/")
            for name in archive.namelist()
        )


def test_the_mit_licence_goes_with_every_copy(site: tuple[Path, str]) -> None:
    """NFR-LEG-003 (decision 0042): the licence's full text is on the site and in both archives
    the workers unpack."""
    dist, _ = site

    def text(data: bytes) -> str:  # the same notice, whichever line endings the checkout has
        return "\n".join(data.decode("utf-8").splitlines())

    licence = text((publish.ROOT / "LICENSE").read_bytes())
    assert "MIT License" in licence
    assert text((dist / "LICENSE.txt").read_bytes()) == licence
    with tarfile.open(dist / "app.tar.gz") as archive:
        member = archive.extractfile("LICENSE")
        assert member is not None
        assert text(member.read()) == licence
    with zipfile.ZipFile(dist / "cassim.zip") as archive:
        assert text(archive.read("LICENSE")) == licence


def test_cancel_ends_a_long_calculation_and_keeps_variables(
    browser: Browser, site: tuple[Path, str]
) -> None:
    """The engine runs in its own worker: Esc terminates it and the state is rebuilt
    (decisions 0005 and 0016, NFR-PERF-004)."""
    _, url = site
    page = browser.new_page(viewport={"width": 1100, "height": 700})
    logs: list[str] = []
    page.on("console", lambda m: logs.append(m.text) if m.text.startswith("CASSIM:") else None)

    def count(word: str) -> int:
        return sum(word in line for line in logs)

    def wait(word: str, n: int = 1, seconds: float = 150) -> None:
        end = time.monotonic() + seconds
        while count(word) < n and time.monotonic() < end:
            page.wait_for_timeout(200)
        assert count(word) >= n, f"no {word!r} in {logs}"

    def enter(text: str) -> None:
        shifted = {"(": "Shift+9", ")": "Shift+0"}
        for char in text:
            if char in shifted:
                page.keyboard.press(shifted[char])
            else:
                page.keyboard.type(char)
        page.keyboard.press("Enter")

    page.goto(url + "#/debug", wait_until="load")
    wait("READY")
    page.mouse.click(600, 120)
    enter("a:=5")
    wait("RESULT", 1)
    enter("seq(k,k,1,99999999)")  # far too big to finish
    page.wait_for_timeout(2500)
    started = time.monotonic()
    page.keyboard.press("Escape")
    wait("CANCELLED", 1, 5)
    assert time.monotonic() - started < 1.5  # the run stops at once
    wait("RESTARTED", 1)
    page.keyboard.press("Control+a")
    page.keyboard.press("Delete")
    enter("a+1")
    wait("RESULT", 2, 60)
    assert logs[-1] == "CASSIM: RESULT 6"  # the variable survived the engine's replacement
    page.close()


def test_install_and_fullscreen_go_through_the_page(
    browser: Browser, site: tuple[Path, str]
) -> None:
    """FR-PWA-001: the app runs in a worker, so the page holds the install prompt and answers the
    app's requests over a BroadcastChannel."""
    _, url = site
    page = browser.new_page()
    page.goto(url, wait_until="load")
    result = page.evaluate(
        """async () => {
          const app = new BroadcastChannel('cassim');   // stands in for the Python worker
          const heard = [];
          app.onmessage = (m) => heard.push(m.data);
          const wait = () => new Promise((r) => setTimeout(r, 200));
          app.postMessage({op: 'hello'});
          await wait();
          let prompted = 0;
          const e = new Event('beforeinstallprompt', {cancelable: true});
          e.prompt = () => { prompted++; };
          window.dispatchEvent(e);
          await wait();
          const held = e.defaultPrevented;
          app.postMessage({op: 'install'});
          await wait();
          return {heard, held, prompted};
        }"""
    )
    assert result["held"]
    assert result["prompted"] == 1
    values = [m["value"] for m in result["heard"] if m["op"] == "installable"]
    assert values == [False, True, False]  # nothing offered, offered, used
    page.close()


def test_safe_area_is_reported_through_the_page(browser: Browser, site: tuple[Path, str]) -> None:
    """FR-DEV-004: the page reports all four measured insets and updates them after a resize."""
    _, url = site
    page = browser.new_page(viewport={"width": 390, "height": 844})
    page.goto(url, wait_until="load")
    values = page.evaluate(
        """async () => {
          const app = new BroadcastChannel('cassim');
          const heard = [];
          app.onmessage = (m) => { if (m.data.op === 'env') heard.push(m.data.safeArea); };
          const wait = () => new Promise((resolve) => setTimeout(resolve, 200));
          const probe = document.getElementById('cassim-safe-area');
          probe.style.padding = '30px 25px 10px 20px';
          app.postMessage({op: 'hello'});
          await wait();
          probe.style.padding = '5px 15px 0px 35px';
          window.dispatchEvent(new Event('resize'));
          await wait();
          app.close();
          return heard;
        }"""
    )
    assert values[0] == {"top": 30, "right": 25, "bottom": 10, "left": 20}
    assert values[-1] == {"top": 5, "right": 15, "bottom": 0, "left": 35}
    page.close()


@pytest.mark.parametrize("size", [(390, 844), (844, 390)])
def test_installed_phone_toggles_the_safe_area_in_the_running_app(
    browser: Browser, site: tuple[Path, str], size: tuple[int, int]
) -> None:
    """FR-DEV-004: the Doc item changes the rendered layout without leaving the installed app."""
    context = browser.new_context(viewport={"width": size[0], "height": size[1]})
    page = context.new_page()
    page.add_init_script(
        """(() => {
          const nativeMatchMedia = window.matchMedia.bind(window);
          window.matchMedia = (query) => query === '(display-mode: fullscreen)'
            ? nativeMatchMedia('(min-width: 0px)') : nativeMatchMedia(query);
        })()"""
    )
    AppPage(page, site[1])
    page.add_style_tag(content="#cassim-safe-area { padding: 50px 35px 10px 25px !important; }")
    page.evaluate("window.dispatchEvent(new Event('resize'))")
    page.wait_for_timeout(1000)
    page.mouse.click(100, 100)

    def top() -> Image.Image:
        image = Image.open(BytesIO(page.screenshot())).convert("RGB")
        return image.crop((0, 0, size[0], 40))

    def toggle() -> None:
        page.keyboard.press("F4")
        page.keyboard.press("ArrowUp")
        page.keyboard.press("ArrowUp")
        page.keyboard.press("Enter")
        page.wait_for_timeout(1000)

    covering = top()
    shots = os.environ.get("CASSIM_SHOTS")
    if shots:
        page.screenshot(path=str(Path(shots) / f"cutout-{size[0]}-use.png"))
    toggle()
    avoiding = top()
    if shots:
        page.screenshot(path=str(Path(shots) / f"cutout-{size[0]}-avoid.png"))
    assert ImageChops.difference(covering, avoiding).getbbox() is not None
    toggle()
    covering_again = top()
    assert ImageChops.difference(avoiding, covering_again).getbbox() is not None
    assert page.evaluate("matchMedia('(display-mode: fullscreen)').matches")
    context.close()


@pytest.mark.parametrize("size", [(1280, 720), (390, 844), (844, 390)])
def test_no_view_needs_the_network_for_fonts(
    browser: Browser, site: tuple[Path, str], size: tuple[int, int]
) -> None:
    """FR-PWA-002: every glyph on the Computer and Handheld views comes from a vendored font, so
    nothing is fetched (and nothing 404s) while offline."""
    _, url = site
    context = browser.new_context(viewport={"width": size[0], "height": size[1]})
    page = context.new_page()
    missing: list[str] = []
    page.on("response", lambda r: missing.append(r.url) if r.status == 404 else None)
    page.goto(url, wait_until="load")
    assert wait_for(page, "!document.getElementById('cassim-splash')")
    page.wait_for_timeout(15000)
    assert not [m for m in missing if "rive" not in m], missing
    context.close()
