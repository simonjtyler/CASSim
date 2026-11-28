# Requirements traced here: FR-DEV-002, FR-DOC-001, FR-DEV-006
"""Computer mode's resizable, movable columns and compact controls."""

import asyncio
from collections.abc import Callable
from types import SimpleNamespace
from typing import cast

import flet as ft
import pytest

from cassim import bundle
from cassim.app.shell import BrowserOffers, Shell
from cassim.devices.nspire import DEVICE
from cassim.devices.nspire.pages.calculator import calculator_of
from cassim.devices.nspire.ui.app import App
from cassim.devices.nspire.ui.state import AppState, Mode
from cassim.devices.nspire.ui.views import system_settings_dialog


class FakePage(SimpleNamespace):
    def __init__(self, width: float = 1280, height: float = 800) -> None:
        super().__init__(width=width, height=height, url="", services=[], updates=0, tasks=[])

    def update(self) -> None:
        self.updates += 1

    def run_task(self, handler: object, *args: object) -> None:
        self.tasks.append((handler, args))


def computer_app(width: float = 1280) -> tuple[App, FakePage]:
    page = FakePage(width)
    app = App(Shell(cast("ft.Page", page), DEVICE), AppState())
    app.arrange()
    return app, page


def descendants(control: ft.Control) -> list[ft.Control]:
    found = [control]
    children = getattr(control, "controls", None)
    if children is not None:
        for child in children:
            found.extend(descendants(child))
    content = getattr(control, "content", None)
    if isinstance(content, ft.Control):
        found.extend(descendants(content))
    return found


def text_chip(controls: list[ft.Control], label: str) -> ft.Container:
    return next(
        control
        for root in controls
        for control in descendants(root)
        if isinstance(control, ft.Container)
        and isinstance(control.content, ft.Text)
        and control.content.value == label
    )


def test_computer_layout_defaults_to_sidebar_workspace_and_optional_keypad() -> None:
    app, _ = computer_app()
    assert app.frame.controls == [app.layout]
    row = app.layout.content
    assert isinstance(row, ft.Row)
    targets = [control for control in row.controls if isinstance(control, ft.DragTarget)]
    assert len(targets) == 2
    assert list(app.computer_panels) == ["sidebar", "workspace"]
    sidebar_content = app.computer_panels["sidebar"].content
    assert isinstance(sidebar_content, ft.Column)
    content = sidebar_content.controls[0]  # no header by default
    assert isinstance(content, ft.Column)
    assert content.controls[0] is app.toolbar

    app.toggle_keypad()
    row = app.layout.content
    assert isinstance(row, ft.Row)
    assert list(app.computer_panels) == ["sidebar", "workspace", "keypad"]
    assert app.keypad.control in descendants(app.computer_panels["keypad"])


def test_graph_plot_fits_inside_the_padded_workspace() -> None:
    """FR-GRAPH-006: the graph scene fits inside the computer workspace."""
    app, _ = computer_app()
    app.state.run_action("add_page", "graphs")
    app.view.refresh()
    workspace = app.computer_panels["workspace"]
    assert isinstance(workspace.padding, int)
    assert isinstance(workspace.width, int | float)
    assert app.view.graphs_view._width == workspace.width - 2 * workspace.padding


def test_handheld_graph_plot_uses_the_whole_screen_width() -> None:
    """FR-GRAPH-006: computer-column padding does not shrink handheld graphs."""
    app, _ = computer_app()
    app.set_mode(Mode.HANDHELD)
    app.state.run_action("add_page", "graphs")
    app.view.refresh()
    assert app.view.graphs_view._width == app.body_size()[0]


def test_computer_columns_can_be_resized_and_swapped() -> None:
    app, _ = computer_app()
    app.toggle_keypad()
    app._resize_boundary("sidebar", "workspace", 40)
    assert app.state.system.computer_sidebar_width == 340
    assert app.computer_panels["sidebar"].width == 340

    app._move_column("keypad", -1)
    assert app.state.system.computer_column_order == ["sidebar", "keypad", "workspace"]
    assert list(app.computer_panels) == ["sidebar", "keypad", "workspace"]


def test_computer_toolbar_removes_page_arrows_and_keeps_undo_redo() -> None:
    app, _ = computer_app()
    controls = app.toolbar_controls()
    tips = {
        control.tooltip
        for root in controls
        for control in descendants(root)
        if isinstance(control, ft.Container | ft.IconButton) and control.tooltip
    }
    assert "Undo (Ctrl+Z)" in tips
    assert "Redo (Ctrl+Y)" in tips
    labels = {
        control.content.value
        for root in controls
        for control in descendants(root)
        if isinstance(control, ft.Container)
        and isinstance(control.content, ft.Text)
        and control.content.value
    }
    assert "◀ page" not in labels
    assert "page ▶" not in labels


def test_computer_toolbar_groups_actions_and_uses_keypad_theme() -> None:
    app, _ = computer_app()
    rows = app.toolbar_controls()
    assert len(rows) == 4
    assert all(isinstance(row, ft.Row) for row in rows)
    labels = [
        [
            control.content.value
            for control in row.controls
            if isinstance(control, ft.Container) and isinstance(control.content, ft.Text)
        ]
        for row in rows
        if isinstance(row, ft.Row)
    ]
    assert labels == [
        ["Keypad"],
        ["CASSim", "Doc", "Document settings"],
        ["Menu"],
        ["Page manager", "+ Page", "+ Problem"],
    ]
    assert text_chip(rows, "CASSim").bgcolor == app.theme.accent
    assert text_chip(rows, "Doc").bgcolor == app.theme.key_colours("nav")[0]
    assert text_chip(rows, "Document settings").bgcolor == app.theme.key


def test_computer_toolbar_keeps_beta_brand_with_attention(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(bundle, "SOURCE", "CASSim-calc")
    app, _ = computer_app()
    assert text_chip(app.toolbar_controls(), "CASSimᵝ")
    monkeypatch.setattr(Shell, "offers", property(lambda _: BrowserOffers(update_ready=True)))
    assert any(
        isinstance(control, ft.Text) and control.value == "CASSimᵝ"
        for root in app.toolbar_controls()
        for control in descendants(root)
    )


def test_arrows_on_each_resize_bar_move_the_columns_across_it() -> None:
    """< | > in the middle of each resize bar: < moves the column right of it left, > the one
    left of it right. They take no keyboard focus (Tab and Enter are calculator keys) unless
    the keyboard column controls are on, which also add the bars' resize buttons. No headers
    unless Settings asks for them."""
    app, _ = computer_app()
    assert app.computer_row is not None
    controls = descendants(app.computer_row)
    arrows = [c for c in controls if isinstance(c, ft.Container) and c.width == 11]
    assert [a.tooltip for a in arrows] == ["Move calculation left", "Move controls and pages right"]
    assert all(a.ink is False for a in arrows)  # not focusable
    assert not [c for c in controls if isinstance(c, (ft.IconButton, ft.Draggable))]
    handler = cast("Callable[[object], object]", arrows[0].on_click)
    handler(None)
    assert list(app.computer_panels) == ["workspace", "sidebar"]

    app.state.system.computer_column_controls = True
    app.arrange()
    assert app.computer_row is not None
    buttons = [c for c in descendants(app.computer_row) if isinstance(c, ft.IconButton)]
    tips = {b.tooltip for b in buttons}
    assert {"Move controls and pages left", "Move calculation right"} <= tips  # Tab reaches them
    assert "Narrow the column on the left" in tips

    app.toggle_keypad()
    assert app.computer_row is not None
    arrows = [c for c in descendants(app.computer_row) if isinstance(c, ft.IconButton)]
    assert len([a for a in arrows if str(a.tooltip).startswith("Move ")]) == 4  # two bars


def test_column_headers_are_a_setting_for_dragging_a_column() -> None:
    app, _ = computer_app()
    app.state.system.computer_column_headers = True
    app.arrange()
    assert app.computer_row is not None
    controls = descendants(app.computer_row)
    assert len([c for c in controls if isinstance(c, ft.Draggable)]) == 2  # one per column
    tips = {c.tooltip for c in controls if isinstance(c.tooltip, str)}
    assert {"Drag to move controls and pages", "Drag to move calculation"} <= tips


def test_a_dropped_column_takes_the_targets_place() -> None:
    """Dragged to the right it goes after the column it is dropped on, to the left before it,
    and a bar on that side shows where it will go."""
    app, _ = computer_app()
    app.toggle_keypad()
    assert list(app.computer_panels) == ["sidebar", "workspace", "keypad"]
    app.dragged_column = "sidebar"
    app._mark_drop("keypad")
    border = app.computer_panels["keypad"].border
    assert isinstance(border, ft.Border)
    assert border.right is not None  # after the keypad
    app._mark_drop("keypad", over=False)
    assert app.computer_panels["keypad"].border is None
    app._drop_column("keypad")
    assert list(app.computer_panels) == ["workspace", "keypad", "sidebar"]
    app.dragged_column = "sidebar"
    app._mark_drop("workspace")
    border = app.computer_panels["workspace"].border
    assert isinstance(border, ft.Border)
    assert border.left is not None  # before the workspace
    app._drop_column("workspace")
    assert list(app.computer_panels) == ["sidebar", "workspace", "keypad"]
    app._drop_column("keypad")  # nothing is being dragged
    assert list(app.computer_panels) == ["sidebar", "workspace", "keypad"]


def test_system_settings_enables_column_controls() -> None:
    class DialogPage:
        dialog: ft.AlertDialog

        def show_dialog(self, dialog: ft.AlertDialog) -> None:
            self.dialog = dialog

        def pop_dialog(self) -> None:
            pass

    page = DialogPage()
    state = AppState()
    changed: list[bool] = []
    system_settings_dialog(cast("ft.Page", page), state, lambda: changed.append(True))
    content = page.dialog.content
    assert isinstance(content, ft.Column)
    checkbox = next(control for control in content.controls if isinstance(control, ft.Checkbox))
    assert not checkbox.value
    checkbox.value = True
    ok = page.dialog.actions[-1]
    assert isinstance(ok, ft.TextButton)
    assert ok.on_click is not None
    handler = cast("Callable[[], object]", ok.on_click)
    handler()
    assert state.system.computer_column_controls
    assert changed == [True]


def test_computer_mode_and_keypad_controls_have_toggle_states() -> None:
    app, _ = computer_app()
    controls = app.toolbar_controls()
    mode_toggle = next(
        control
        for root in controls
        for control in descendants(root)
        if isinstance(control, ft.SegmentedButton)
    )
    assert [segment.value for segment in mode_toggle.segments] == ["handheld", "tablet", "computer"]
    assert mode_toggle.selected == ["computer"]
    assert not mode_toggle.show_selected_icon
    assert not mode_toggle.allow_empty_selection
    assert not mode_toggle.allow_multiple_selection
    assert text_chip(controls, "Keypad").bgcolor == app.theme.key
    app.state.system.computer_keypad = True
    assert text_chip(app.toolbar_controls(), "Keypad").bgcolor == app.theme.accent


def test_selecting_handheld_on_mode_toggle_switches_view() -> None:
    app, _ = computer_app()
    toggle = next(
        control
        for root in app.toolbar_controls()
        for control in descendants(root)
        if isinstance(control, ft.SegmentedButton)
    )
    toggle.selected = ["handheld"]
    assert toggle.on_change is not None
    handler = cast("Callable[[ft.Event[ft.SegmentedButton]], object]", toggle.on_change)
    handler(ft.Event("change", toggle))
    assert app.state.mode is Mode.HANDHELD


def test_handheld_still_uses_the_same_keypad_control() -> None:
    app, _ = computer_app()
    keypad = app.keypad.control
    app.set_mode(Mode.HANDHELD)
    assert keypad in descendants(app.layout)
    app.state.system.computer_keypad = True
    app.set_mode(Mode.COMPUTER)
    assert keypad in descendants(app.layout)


def test_variable_delete_can_be_undone_and_redone(monkeypatch: pytest.MonkeyPatch) -> None:
    app, _ = computer_app()

    def no_refresh() -> None:
        pass

    def no_flash(text: str) -> None:
        pass

    monkeypatch.setattr(app, "refresh", no_refresh)
    monkeypatch.setattr(app, "flash", no_flash)
    session = app.state.document.problems[0].session
    session.eval("a:=5")
    session.eval("f(x):=x^2")
    rows = tuple(session.variables())
    calculator = calculator_of(app.state.document.current)
    assert calculator is not None

    asyncio.run(
        app._delete_variables(
            calculator,
            tuple(row.name for row in rows),
            tuple(row.source for row in rows),
        )
    )
    assert not session.is_defined("a")
    assert not session.is_defined("f")

    asyncio.run(app._apply_variable_history("undo"))
    assert session.eval("a").text == "5"
    assert session.eval("f(3)").text == "9"
    asyncio.run(app._apply_variable_history("redo"))
    assert not session.is_defined("a")
    assert not session.is_defined("f")


def texts_in(control: ft.Control) -> list[ft.Text]:
    return [c for c in descendants(control) if isinstance(c, ft.Text) and isinstance(c.value, str)]


def test_computer_menus_keep_syntax_hints_under_the_menu_and_shortcuts_beside() -> None:
    """A command's syntax goes in the line under the menu, as in Tablet and Handheld, so the
    menu stays narrow; a keyboard shortcut still sits beside its item."""
    app, _ = computer_app()
    for key in ("menu", "5", "5"):  # Menu > Probability > Distributions
        app.state.press_keypad(key) if key == "menu" else app.state.key_event(key)
    app.refresh()
    menu = app.state.screen().menu
    assert menu is not None
    hint = menu.hint
    assert hint.startswith("normPdf(")
    shown = [t for t in texts_in(app.view.control) if t.value == hint]
    assert len(shown) == 1  # only under the menu
    assert shown[0].italic
    app.state.key_event("Escape")
    app.state.key_event("Escape")
    app.state.key_event("Escape")
    app.state.run_action("open_menu", "cassim")
    app.refresh()
    assert any(t.value == "Alt+Shift+C" and not t.italic for t in texts_in(app.view.control))


def test_a_menu_hint_is_a_shortcut_only_when_it_names_keys() -> None:
    """SDD-15 section 9.1: shortcuts (capitalised) beside the item; anything else under it."""
    from cassim.devices.nspire.ui.views import is_shortcut  # noqa: PLC0415

    for hint in (
        "Ctrl+C",
        "Ctrl+◀",
        "Ctrl+▲",
        "Alt+Shift+H",
        "Ctrl+Shift+Z",
        "F1",
        "Esc",
        "Delete",
    ):
        assert is_shortcut(hint), hint
    for hint in ("F", "c", "normPdf(XVal,μ,σ)", "Not in CASSim yet", "Fraction (ctrl+÷)", "ctrl+C"):
        assert not is_shortcut(hint), hint
