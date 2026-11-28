# Requirements traced here: FR-DEV-004
"""A phone has only Handheld view: Computer view leaves no room for the on-screen keyboard. The
view is picked before the first draw, so the page does not show Computer view and then swap."""

import asyncio
from collections.abc import Callable
from types import SimpleNamespace
from typing import cast

import flet as ft
from tests.app.test_computer_columns import descendants
from tests.app.test_splitter_drag import handheld_app

from cassim.devices.nspire.ui.state import Mode, System


def test_a_phone_stays_in_handheld() -> None:
    app, _ = handheld_app(412, 915)
    app.set_mode(Mode.COMPUTER)
    assert app.state.mode is Mode.HANDHELD
    app.show_dialog("view:computer")
    assert app.state.mode is Mode.HANDHELD


def test_a_window_shrunk_to_phone_size_goes_to_handheld() -> None:
    app, page = handheld_app(1200, 800)
    app.set_mode(Mode.COMPUTER)
    assert app.state.mode is Mode.COMPUTER
    page.width, page.height = 412, 915
    app.on_resize(cast("ft.PageResizeEvent", SimpleNamespace(width=412, height=915)))
    assert app.state.mode is Mode.HANDHELD


def recovered_mode(width: float, height: float, saved: Mode | None) -> Mode:
    app, _ = handheld_app(width, height)
    app.state.mode = Mode.COMPUTER  # the default before anything is read

    async def read(key: str) -> str | None:
        return System(start_mode=saved).dumps() if saved and key == "system" else None

    async def nothing_shared(_key: str) -> str | None:
        return None  # no shared theme (SDD-15 section 7) saved either

    app.shell.read = read  # ty: ignore[invalid-assignment]
    app.shell.read_global = nothing_shared  # ty: ignore[invalid-assignment]
    asyncio.run(app.recover_system())
    return app.state.mode


def test_the_view_is_chosen_before_the_first_draw() -> None:
    assert recovered_mode(412, 915, Mode.COMPUTER) is Mode.HANDHELD  # a phone, whatever is saved
    assert recovered_mode(412, 915, None) is Mode.HANDHELD
    assert recovered_mode(1200, 800, Mode.HANDHELD) is Mode.HANDHELD
    assert recovered_mode(1200, 800, None) is Mode.COMPUTER


def test_a_phone_follows_its_orientation() -> None:
    """SDD-15 section 8.2: Handheld upright, Tablet on its side, as the phone turns."""
    app, page = handheld_app(412, 915)
    for width, height, mode in ((915, 412, Mode.TABLET), (412, 915, Mode.HANDHELD)):
        page.width, page.height = width, height
        app.on_resize(cast("ft.PageResizeEvent", SimpleNamespace(width=width, height=height)))
        assert app.state.mode is mode
    assert recovered_mode(915, 412, Mode.COMPUTER) is Mode.TABLET


def test_tablet_puts_the_keypad_beside_the_screen_and_handheld_under_it() -> None:
    """SDD-15 section 8.1, in the same window: the view decides, not the window's shape."""
    app, _ = handheld_app(1200, 800)
    for mode, beside in ((Mode.TABLET, True), (Mode.HANDHELD, False)):
        app.set_mode(mode)
        assert app.plan is not None
        assert app.plan.side_by_side is beside
        assert app.state.mode is mode


def test_tablet_view_has_its_shortcut_and_menu_item() -> None:
    app, _ = handheld_app(1200, 800)
    app.set_mode(Mode.COMPUTER)
    app.show_dialog("view:tablet")  # CASSim > Tablet view, Alt+Shift+T
    assert app.state.mode is Mode.TABLET


def test_a_chosen_view_stays_when_a_phone_resizes_without_turning() -> None:
    """SDD-15 section 8.4: a browser bar coming and going resizes the window; the view the
    person chose stays until the phone turns."""
    app, page = handheld_app(412, 915)
    app.set_mode(Mode.TABLET)
    page.width, page.height = 412, 860  # the address bar came back
    app.on_resize(cast("ft.PageResizeEvent", SimpleNamespace(width=412, height=860)))
    assert app.state.mode is Mode.TABLET
    page.width, page.height = 860, 412  # turned
    app.on_resize(cast("ft.PageResizeEvent", SimpleNamespace(width=860, height=412)))
    assert app.state.mode is Mode.TABLET  # on its side: Tablet anyway


def test_tablets_bar_resizes_and_its_arrows_swap_the_keypad_and_screen() -> None:
    """Tablet: < | > round the bar's grip put the keypad on the other side of the screen, which
    is kept, and dragging the bar still resizes the keypad."""
    app, _ = handheld_app(1200, 800)
    app.set_mode(Mode.TABLET)
    row = app.layout.content
    assert isinstance(row, ft.Row)
    assert row.controls[0] is app.view.control
    arrows = {
        c.tooltip: c
        for c in descendants(row)
        if isinstance(c, ft.Container)
        and isinstance(c.tooltip, str)
        and c.tooltip.startswith("Move")
    }
    assert set(arrows) == {"Move the keypad left", "Move the screen right"}
    cast("Callable[[object], object]", arrows["Move the keypad left"].on_click)(None)
    assert app.state.system.keypad_first
    row = app.layout.content
    assert isinstance(row, ft.Row)
    assert row.controls[-1] is app.view.control  # the keypad now on the left


def test_tablets_bar_fits_its_arrows_and_follows_the_keyboard_setting() -> None:
    from cassim.devices.nspire.ui.app import COLUMN_ARROW_W  # noqa: PLC0415
    from cassim.devices.nspire.ui.layout import SIDE_SPLITTER  # noqa: PLC0415

    assert SIDE_SPLITTER >= 2 * COLUMN_ARROW_W + 4  # < and > either side of the 4 px grip
    app, _ = handheld_app(1200, 800)
    app.set_mode(Mode.TABLET)
    app.state.system.computer_column_controls = True
    app.on_system_change()
    row = app.layout.content
    assert row is not None
    buttons = [c for c in descendants(row) if isinstance(c, ft.IconButton)]
    assert {b.tooltip for b in buttons} == {"Move the keypad left", "Move the screen right"}


def test_a_phone_never_shows_the_keypad_moved_left() -> None:
    """A phone has no bar to move it back, so the saved choice waits for a larger window."""
    app, _ = handheld_app(915, 412)
    app.state.system.keypad_first = True
    app.set_mode(Mode.TABLET)
    row = app.layout.content
    assert isinstance(row, ft.Row)
    assert row.controls[0] is app.view.control
