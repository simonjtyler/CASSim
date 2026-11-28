"""The text of the About dialog (NFR-LEG-002, NFR-LEG-003, NFR-SEC-001). Plain data, no Flet."""

from __future__ import annotations

import platform
from dataclasses import dataclass
from importlib import metadata

from cassim import bundle, devices

DISCLAIMER = (
    "CASSim simulates handheld calculators, including computer algebra systems (CAS), for "
    "teaching and learning. It is not affiliated with, endorsed by or sponsored by any company "
    "or curriculum authority.\n"
    "It is not an approved exam calculator: do not use it in an assessment that requires an "
    "approved device."
)

PRIVACY = (
    "CASSim has no server and collects nothing: no telemetry and no analytics. Your documents "
    "are kept on this device, and leave it only in a link or file you choose to share. Opening a "
    "shared link or file never runs Python or a program by itself."
)

COPYRIGHT = "Copyright (c) 2026 Simon Tyler and CASSim contributors"
LICENCE = (
    "CASSim is vibe-coded and is released under the MIT licence: anyone may use, copy, change "
    "and share it, keeping the copyright notice. It comes with no warranty. " + COPYRIGHT + "."
)

# The help pages: `docs/wiki/`, built by `tools.wiki_site` and deployed to their own site.
WIKI_URL = "https://cassim-wiki.pages.dev/"
HELP = f"Help, and the list of CASSim sites: {WIKI_URL}"

# The released all-in-one site, which the testing and single-app editions point to.
STABLE_URL = "https://cassim-app.pages.dev/"


def edition() -> str:
    """Which edition this build is: testing (beta), released, single-app or a development copy.
    The source is what `tools.publish --source` wrote into `cassim/bundle.py`."""
    if bundle.SOURCE == "CASSim-calc":
        return (
            "Testing version (beta). It has the newest changes before they are released, so "
            "expect bugs, and things may change or break without notice. The released version "
            f"is at {STABLE_URL}"
        )
    titles = [devices.load(device_id).title for device_id in bundle.DEVICES]
    if bundle.NAME != "all":
        return (
            f"Single-app version: this copy has only {titles[0]}. CASSim with every app is at "
            f"{STABLE_URL}"
        )
    apps = ", ".join(titles[:-1]) + f" and {titles[-1]}" if len(titles) > 1 else titles[0]
    if bundle.SOURCE == "CASSim-app":
        return f"Released version, with every app: {apps}."
    return f"Development copy, run from the source code, with {apps}."


@dataclass(frozen=True)
class Notice:
    name: str
    licence: str
    use: str
    package: str = ""  # an engine package: shown only when a device in the build needs it


# Third-party parts that ship with the build (NFR-LEG-003).
NOTICES = (
    Notice("Flet", "Apache-2.0", "the user interface"),
    Notice("Pyodide", "MPL-2.0", "Python in the browser"),
    Notice("SymPy", "BSD-3-Clause", "computer algebra", "sympy"),
    Notice("mpmath", "BSD-3-Clause", "numerical methods", "mpmath"),
    Notice("openpyxl and et-xmlfile", "MIT", "spreadsheet files"),
    Notice("msgpack, PyYAML, repath and six", "Apache-2.0 and MIT", "supporting libraries"),
    Notice("Noto Sans, Math, Symbols 2 and SC", "SIL OFL 1.1", "symbols the browser lacks"),
    Notice("Roboto Mono", "Apache-2.0", "the code editor and the Scientific display"),
    Notice("CodeMirror", "MIT", "the code editor"),
    Notice(
        "Flutter and its packages (KaTeX fonts, Material icons)",
        "BSD-3-Clause, SIL OFL 1.1 and others: the full list is assets/NOTICES on the site",
        "drawing the app",
    ),
)


def notices() -> list[Notice]:
    """The notices for this build: SymPy and mpmath only when a device's engine ships them."""
    shipped = {
        package
        for device_id in bundle.DEVICES
        if (engine := devices.load(device_id).engine) is not None
        for package in engine.packages
    }
    return [n for n in NOTICES if not n.package or n.package in shipped]


UNKNOWN = "not available"

# Shown in this order; the distribution each is read from when the build did not record it.
SHOWN = (("CASSim", "cassim"), ("Flet", "flet"), ("SymPy", "sympy"), ("mpmath", "mpmath"))


def product_name() -> str:
    """The all-in-one testing site marks its product as beta; stable/device sites do not."""
    return "CASSimᵝ" if bundle.SOURCE == "CASSim-calc" else "CASSim"


def _version(package: str) -> str:
    try:
        return metadata.version(package)
    except metadata.PackageNotFoundError:
        return UNKNOWN


def versions(shipped: dict[str, str] | None = None) -> list[tuple[str, str]]:
    """Name and version pairs for the About dialog: what the build recorded (`bundle.VERSIONS`),
    else the installed packages (the desktop app and the tests)."""
    shipped = bundle.VERSIONS if shipped is None else shipped
    found = [("CASSim", shipped.get("CASSim") or _version("cassim"))]
    found.append(("Python", platform.python_version()))
    if "Pyodide" in shipped:
        found.append(("Pyodide", shipped["Pyodide"]))
    found += [(name, shipped.get(name) or _version(dist)) for name, dist in SHOWN[1:]]
    return found


def build_info() -> str:
    return f"Build: {bundle.SOURCE}\n" + "\n".join(
        f"{name} {version}" for name, version in versions()
    )
