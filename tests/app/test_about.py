"""The About dialog's content and its menu entry (NFR-LEG-002, NFR-LEG-003, NFR-SEC-001)."""

from __future__ import annotations

import tomllib
from types import SimpleNamespace

import pytest
import sympy
from tools import publish, wiki_site

from cassim.app import about
from cassim.app.shell import BrowserOffers, Shell
from cassim.device.menu import MenuItem
from cassim.devices.nspire.ui import app as nspire
from cassim.devices.nspire.ui.app import cassim_items, nspire_menu
from cassim.devices.nspire.ui.state import AppState, Mode
from cassim.devices.pseudocode.ui import app as pseudocode


def test_disclaimer_says_what_nfr_leg_002_requires() -> None:
    """NFR-LEG-002 and NFR-LEG-005: not affiliated with or endorsed by any company (TI, Casio, HP
    included); not an approved exam calculator."""
    text = about.DISCLAIMER
    assert text.startswith("CASSim simulates handheld calculators")
    assert "not affiliated with, endorsed by or sponsored by any company" in text
    assert "curriculum authority" in text
    assert "not an approved exam calculator" in text


def test_privacy_and_licence_statements() -> None:
    """NFR-SEC-001: no telemetry. NFR-LEG-003: the MIT licence, with its copyright line."""
    assert "no server and collects nothing: no telemetry and no analytics" in about.PRIVACY
    assert "never runs Python or a program" in about.PRIVACY
    assert "is vibe-coded and is released" in about.LICENCE
    assert "MIT licence" in about.LICENCE
    assert "Unlicense" not in about.LICENCE
    assert about.COPYRIGHT == "Copyright (c) 2026 Simon Tyler and CASSim contributors"
    assert about.COPYRIGHT in about.LICENCE
    assert about.WIKI_URL in about.HELP


def test_source_and_beta_brand_follow_the_build_source(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(about.bundle, "SOURCE", "CASSim-calc")
    assert about.product_name() == "CASSimᵝ"
    assert about.build_info().startswith("Build: CASSim-calc\n")
    monkeypatch.setattr(about.bundle, "SOURCE", "CASSim-app")
    assert about.product_name() == "CASSim"


def test_the_about_box_says_which_edition_it_is(monkeypatch: pytest.MonkeyPatch) -> None:
    """The testing site says it is the beta and where the released one is; a single-app site
    names its one app; the released all-in-one site names every app."""
    monkeypatch.setattr(about.bundle, "SOURCE", "CASSim-calc")
    assert about.edition().startswith("Testing version (beta).")
    assert about.STABLE_URL in about.edition()
    monkeypatch.setattr(about.bundle, "SOURCE", "CASSim-app")
    assert about.edition() == (
        "Released version, with every app: TI-Nspire CX CAS, Pseudocode & Python and "
        "CASSim Scientific."
    )
    monkeypatch.setattr(about.bundle, "SOURCE", "Development")
    assert about.edition().startswith("Development copy")
    for bundle_name, source, device in (
        ("tin", "CASSim-TIN", ("nspire",)),
        ("pseudo", "CASSim-pseudo", ("pseudocode",)),
    ):
        monkeypatch.setattr(about.bundle, "NAME", bundle_name)
        monkeypatch.setattr(about.bundle, "DEVICES", device)
        monkeypatch.setattr(about.bundle, "SOURCE", source)
        assert about.edition().startswith("Single-app version: this copy has only ")
        assert about.STABLE_URL in about.edition()
    assert "Pseudocode & Python" in about.edition()


def test_notices_follow_the_build(monkeypatch: pytest.MonkeyPatch) -> None:
    """SymPy and mpmath are named only when a device in the build ships them."""
    names = {n.name for n in about.notices()}
    assert {"SymPy", "mpmath"} <= names
    monkeypatch.setattr(about.bundle, "DEVICES", ("pseudocode",))
    names = {n.name for n in about.notices()}
    assert "SymPy" not in names
    assert {"Flet", "Pyodide", "Roboto Mono"} <= names


def test_every_version_is_known() -> None:
    """The About box names a real version for CASSim, Python, Flet, SymPy and mpmath, and CASSim's
    and SymPy's are the ones this checkout uses."""
    shown = dict(about.versions())
    assert list(shown) == ["CASSim", "Python", "Flet", "SymPy", "mpmath"]
    assert about.UNKNOWN not in shown.values(), shown
    pyproject = tomllib.loads((publish.ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert shown["CASSim"] == pyproject["project"]["version"]
    assert shown["SymPy"] == sympy.__version__


def test_a_build_shows_the_versions_it_ships() -> None:
    """In the browser the versions come from the build's `bundle.VERSIONS`, which `tools.publish`
    takes from pyproject.toml and Pyodide's lock file."""
    lock = {"packages": {"sympy": {"version": "1.14.0"}, "mpmath": {"version": "1.4.1"}}}
    shipped = publish.shipped_versions(lock, "0.29.0", publish.bundles()["all"])
    assert shipped == {
        "CASSim": publish.project_version(),
        "Pyodide": "0.29.0",
        "Flet": publish.flet_version(),
        "SymPy": "1.14.0",
        "mpmath": "1.4.1",
    }
    shown = dict(about.versions(shipped))
    assert list(shown) == ["CASSim", "Python", "Pyodide", "Flet", "SymPy", "mpmath"]
    assert (shown["SymPy"], shown["Pyodide"]) == ("1.14.0", "0.29.0")


def test_notices_cover_the_shipped_third_party_parts() -> None:
    """NFR-LEG-003: Flet, Pyodide, SymPy, mpmath and the vendored fonts are named with a
    licence. SciPy and NumPy are not shipped (decision 0031), so they are not named."""
    names = {notice.name for notice in about.NOTICES}
    assert {"Flet", "Pyodide", "SymPy", "mpmath", "Noto Sans, Math, Symbols 2 and SC"} <= names
    assert "CodeMirror" in names  # the Pseudocode editor
    assert any(name.startswith("Flutter") for name in names)
    assert not {"SciPy", "NumPy"} & names
    assert all(notice.licence for notice in about.NOTICES)


def test_versions_include_cassim_and_python() -> None:
    names = [name for name, _ in about.versions()]
    assert names[:2] == ["CASSim", "Python"]
    assert "CASSim " in about.build_info()
    assert "SymPy " in about.build_info()
    assert f"Build: {about.bundle.SOURCE}" in about.build_info()


def test_about_is_in_the_cassim_menu() -> None:
    """CASSim > About asks for the about dialog."""
    state = AppState()
    state.cassim_menu = lambda: MenuItem(
        "CASSim", items=cassim_items(BrowserOffers(), nspire_menu(view=Mode.HANDHELD))
    )
    asked: list[str] = []
    state.show_dialog = asked.append
    state.run_action("open_menu", "cassim")
    assert state.menu is not None
    state.key_event(state.menu.keys()[-1])
    assert asked == ["about"]


def test_help_menu_item_opens_the_wiki() -> None:
    """CASSim > Help asks for the help dialog, which opens the wiki."""
    assert about.WIKI_URL == "https://cassim-wiki.pages.dev/"
    state = AppState()
    state.cassim_menu = lambda: MenuItem(
        "CASSim", items=cassim_items(BrowserOffers(), nspire_menu(view=Mode.HANDHELD))
    )
    asked: list[str] = []
    state.show_dialog = asked.append
    state.run_action("open_menu", "cassim")
    assert state.menu is not None
    state.key_event(state.menu.keys()[-2])
    assert asked == ["help"]


def test_help_opens_the_current_apps_page_on_the_wiki() -> None:
    """Help in each app opens that app's own help page; Home opens the help home."""
    opened: list[str] = []
    shell = SimpleNamespace(
        page=SimpleNamespace(run_task=lambda _launch, url: opened.append(url)),
        launcher=SimpleNamespace(launch_url=None),
    )
    for page in ("", nspire.HELP_PAGE, pseudocode.HELP_PAGE):
        Shell.help(shell, page)  # ty: ignore[invalid-argument-type]
    assert opened == [
        about.WIKI_URL,
        about.WIKI_URL + "Nspire.html",
        about.WIKI_URL + "Pseudocode.html",
    ]
    for page in (nspire.HELP_PAGE, pseudocode.HELP_PAGE):
        assert (wiki_site.SOURCE / page.replace(".html", ".md")).exists()
