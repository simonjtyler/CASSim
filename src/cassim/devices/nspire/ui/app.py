"""The Nspire's app: its state joined to its views, inside the shell (decision 0032 item 5).

Everything that belongs to the browser (storage, files, the clipboard, links, notices, install
and full screen, the engine worker) is reached through the `Shell` it is mounted with.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, replace

import flet as ft

from cassim.app import about
from cassim.app.appearance import Appearance, appearance_dialog
from cassim.app.cassim_menu import (
    MARKS,
    STANDARD_VIEWS,
    AppMenu,
    Panel,
    cassim_sections,
    needs_attention_tooltip,
)
from cassim.app.keyboard import (
    ARROW_KEYS,
    REPEAT_DELAY,
    key_name,
    repeat_interval,
)
from cassim.app.saved import SavedDocuments
from cassim.app.shell import BrowserOffers, Shell
from cassim.app.sizes import is_landscape, page_is_phone, repick_view
from cassim.core.results import VariableInfo
from cassim.core.settings import Settings, next_choice
from cassim.device.editor import Editor
from cassim.device.engine import LocalEngine, RemoteSession, local_session
from cassim.device.keys import Action, Binding, keypad_units
from cassim.device.menu import MenuItem
from cassim.device.pointer import Pointer
from cassim.device.wizard import Wizard
from cassim.devices.nspire.document import loads
from cassim.devices.nspire.pages import PAGES
from cassim.devices.nspire.pages.calculator import Calculator, Pending, calculator_of
from cassim.devices.nspire.runner import Runner, Status
from cassim.devices.nspire.ui.keypad import STICK_KEY, Keypad
from cassim.devices.nspire.ui.layout import (
    COMPUTER_COLUMN_PADDING,
    COMPUTER_SPLITTER,
    FULL_RESERVE,
    GAP,
    MARGIN,
    PHONE_MARGIN,
    SCREEN_H,
    SCREEN_W,
    SIDE_SPLITTER,
    SPLITTER,
    STATUS_H,
    HandheldPlan,
    Sizing,
    clamp_share,
    computer_columns,
    computer_screen_height,
    full_screen_height,
    handheld_plan,
    keypad_size,
    starting_mode,
)
from cassim.devices.nspire.ui.sidebar import Sidebar
from cassim.devices.nspire.ui.soft_keys import SENTINEL, TYPING_ACTIONS, keys_for
from cassim.devices.nspire.ui.state import (
    COMPUTER_MAX_SIDEBAR,
    COMPUTER_MIN_SIDEBAR,
    SORTER,
    AppState,
    Mode,
    System,
)
from cassim.devices.nspire.ui.views import (
    POINTER_TICK,
    SYMBOL_FONT,
    SYMBOL_FONT_FILE,
    CalculatorView,
    label_text,
    settings_dialog,
    system_settings_dialog,
    wizard_dialog,
)
from cassim.doc.document import Document
from cassim.doc.library import (
    CURRENT_KEY,
    UNTITLED,
    Current,
    document_fingerprint,
    fingerprint,
    title,
)
from cassim.doc.serialize import (
    OPEN_EXTENSIONS,
    DocumentFileError,
    dumps,
    file_name,
    parse,
    to_dict,
)
from cassim.doc.share import LinkTooLongError, encode, unpack
from cassim.sheet.fileio import read_csv, read_xlsx, write_csv, write_xlsx

# TODO(M2b): a first visit should pick Handheld below about 700 px (decision 0013 item 3).
# Flet fires no resize event at start-up, so this needs a different hook.


TITLE_H = 20  # the screen's title bar, in the handheld's pixels
TYPEAHEAD = 64  # keys kept while the engine works
COLUMN_HEADER_H = 32  # a column's header, if shown: its name, to drag
# < and > either side of a resize bar: they fit the bar's width, and are tall for a finger
COLUMN_ARROW_W, COLUMN_ARROW_H = 11, 40
COMPUTER_PANEL_NAMES = {
    "sidebar": "Controls and pages",
    "workspace": "Calculation",
    "keypad": "Keypad",
}

# The keys of the two texts kept in browser storage, after the device's prefix (`cassim.`).
AUTOSAVE_KEY = "autosave"
HELP_PAGE = "Nspire.html"  # the Nspire's page on the help site
SYSTEM_KEY = "system"
# The document is saved this long after the last change, not on every key (decision 0031): saving
# writes the whole document, and with sheet data that is too slow to do per key.
AUTOSAVE_DELAY = 0.5  # seconds
FLASH_SECONDS = 2.0  # how long a note such as "Saved" stays in the status line


@dataclass(frozen=True)
class VariableDeletion:
    calculator: Calculator
    sources: tuple[str, ...]
    names: tuple[str, ...]


NSPIRE_VIEWS = STANDARD_VIEWS


def nspire_menu(
    *,
    view: Mode,
    phone: bool = False,
    use_cutout: bool = True,
    home: bool = False,
    keypad: bool = False,
) -> AppMenu:
    """What the Nspire puts in the CASSim menu: its three views, the Keypad (a panel only in
    Computer view; Tablet and Handheld always have it), and the cutout on an installed phone."""
    handheld = view.device
    return AppMenu(
        home=home,
        views=NSPIRE_VIEWS,
        view=view.value,
        panels=(
            Panel(
                "keypad",
                "Keypad",
                shown=keypad or handheld,
                enabled=not handheld,
                hint="In Computer view" if handheld else "",
            ),
        ),
        phone=phone,
        cutout=use_cutout if handheld else None,
    )


def cassim_items(offers: BrowserOffers, app: AppMenu) -> tuple[MenuItem, ...]:
    """The CASSim menu's shared sections (SDD-15 section 4) as the Nspire's numbered panel: a
    section after the first starts with a rule, and ✓ and ● mark what is on."""
    return tuple(
        MenuItem(
            item.label,
            "dialog",
            item.action,
            hint=item.shortcut or item.hint,
            enabled=item.enabled,
            mark=MARKS[item.mark] if item.mark and item.on else "",
            rule=number > 0 and index == 0,
        )
        for number, section in enumerate(cassim_sections(offers, app))
        for index, item in enumerate(section)
    )


class App:
    """Wires the state to the views: the top bar, the screen, the keypad and the sidebar."""

    draining = False  # running the keys typed while the engine worked
    landscape: bool | None = None  # the window's shape at the last resize

    def __init__(self, shell: Shell, state: AppState, runner: Runner | None = None) -> None:
        page = shell.page
        self.shell = shell
        self.page = page
        self.state = state
        shell.changed = self.on_bridge  # the browser's offers changed
        self.runner = runner  # None: the maths runs in this process, synchronously
        self.status = ft.Text("", size=13, color=shell.theme.status_text)
        self.debug = "debug" in (page.url or "")  # `#/debug` prints results for the e2e tests
        self.shown: tuple[int, int] | None = None  # the page last drawn, for the debug PAGE line
        # `#/debug/keytime` shows what each redraw cost in the status line, to measure typing on a
        # Chromebook or phone with no tools (decision 0035 stage 4)
        self.keytime = "keytime" in (page.url or "")
        self.sheet_line = ""  # the debug SHEET line last printed
        self.sheet_selection_line = ""
        self.plan: HandheldPlan | None = None  # the last Handheld arrangement
        self.shape: tuple[Mode, bool, bool, bool, bool, bool, bool] | None = (
            None  # what the layout is built from
        )
        self.holder: ft.Container | None = None  # the splitter's box in a portrait layout
        self.resizing = False  # a splitter redraw is queued: further drag steps only add up
        self.first_visit = False  # nothing saved yet: the window size picks the mode
        self.use_cutout = True
        self.starting = False  # loading the autosave through a remote engine
        self.sheet_file_busy = False
        self.theme = shell.theme
        self.shift = False  # Flet sends no modifiers with a click, so remember the key
        self.arrow_event: ft.KeyboardEvent | None = None
        self.pad_hold: str | None = None
        self.pad_hold_generation = 0
        self.view = CalculatorView(
            state, self.theme, self.act, lambda: self.shift, self.cycle_setting
        )
        self.view.body_size = self.body_size
        self.pointer = Pointer()  # steered by the keypad's centre key
        self.ticking = False  # the pointer's timer is running
        self.keypad = Keypad(
            state,
            self.press,
            self.theme,
            on_cassim=self.press_cassim,
            on_stick=self.on_stick,
        )
        self.keypad.on_arrow_hold = self.hold_keypad_arrow
        self.keypad.refresh()
        self.sidebar = Sidebar(
            state,
            self.refresh,
            self.theme,
            on_delete=self.delete_variables,
        )
        self.toolbar = ft.Column(spacing=4)
        self.layout = ft.Container(expand=True)
        self.computer_panels: dict[str, ft.Container] = {}
        self.computer_row: ft.Row | None = None
        self.dragged_column: str | None = None  # a column whose header is being dragged
        # Keys typed while the engine works: run in order once it is free, as a handheld keeps
        # them, instead of lost (a key typed just after adding a page or pressing Enter)
        self.typeahead: deque[Binding | str] = deque()
        # Computer view on a phone or tablet: a hidden text box in the toolbar row takes the
        # focus when typing is expected, so the on-screen keyboard opens (see soft_keys)
        self.sink = ft.TextField(
            value=SENTINEL,
            autocorrect=False,
            enable_suggestions=False,
            on_change=self.on_sink,
            on_submit=self.on_sink_submit,
            on_focus=lambda _: setattr(self, "sink_focused", True),
            on_blur=lambda _: setattr(self, "sink_focused", False),
        )
        self.sink_focused = False
        self.sink_box = ft.Container(self.sink, width=1, height=1, opacity=0)
        self.frame = ft.Column([self.toolbar, self.layout], expand=True)
        # Handheld in full screen or the installed app: the screen fills the height, there is no
        # toolbar row, and a status message (Calculating..., Saved) shows in the title bar
        self.full = False
        # The margin round everything. Not `page.padding`: a change to that after start-up does
        # not reach the page, and a phone needs a thinner margin than a computer.
        self.outer = ft.Container(self.frame, padding=MARGIN, expand=True)
        self._wire_state(shell, state)
        self.variable_undo: list[VariableDeletion] = []
        self.variable_redo: list[VariableDeletion] = []
        state.ask_discard = self.ask_discard
        state.on_new_document = self.on_new_document

    def unmount(self) -> None:
        """Save the current document and release the page owned by this device."""
        self.save_now()
        self.shell.changed = lambda: None
        self.shell.has_unsaved = lambda: False
        self.page.on_keyboard_event = None
        self.page.on_resize = None
        self.page.on_app_lifecycle_state_change = None
        self.page.controls.clear()

    def _wire_state(self, shell: Shell, state: AppState) -> None:
        state.clipboard_out = shell.copy  # copy and cut also fill the system clipboard
        state.show_dialog = self.show_dialog
        state.cassim_menu = self.cassim_menu
        shell.has_unsaved = self.has_unsaved  # a reload for an update asks first
        state.show_wizard = self.show_wizard
        state.request_paste = self.request_paste
        self.typing_dialog: ft.AlertDialog | None = None  # its text boxes take the keyboard
        self.appearance_error = ""  # a saved theme that could not be read
        self.saved = ""  # the last text autosaved, so an idle refresh writes nothing
        self.save_at = 0.0  # when the waiting autosave runs (time.monotonic)
        self.save_waiting = False  # a save task is waiting for that time
        # Documents saved by name in this app (FR-DOC-010), with every app's Open and Save
        # (`app/saved.py`, SDD-15 section 9.3), and the open one's link to them
        self.documents = SavedDocuments(
            shell.page,
            shell,
            dump=self.dump_named,
            load=self.load_named,
            changed=self.on_documents_change,
            said=self.said,
            noun="document",
            menu="Doc ▸ File",
            mark=lambda: document_fingerprint(self.state.document),
            on_dialog=self.on_name_dialog,
            suggest=lambda: "" if state.document.name == UNTITLED else state.document.name,
            open_title="Open document",
        )
        self.documents.current = Current(None, document_fingerprint(state.document))
        self.dirty = False  # the document differs from its saved copy (or has none)

    async def start(self, view: Mode | None = None, settings: Settings | None = None) -> None:
        """Open the app. `view` and `settings` (from the command line) override the saved view and
        the settings of the recovered document."""
        self.starting = True  # refresh callbacks can run before the autosave has been recovered
        page = self.page
        page.title = about.product_name()
        page.fonts = {SYMBOL_FONT: SYMBOL_FONT_FILE}
        page.theme_mode = ft.ThemeMode.DARK
        page.bgcolor = self.theme.background
        page.padding = 0
        page.on_keyboard_event = self.on_key
        page.on_resize = self.on_resize
        page.on_app_lifecycle_state_change = self.on_lifecycle
        # Pick the view before the first draw, so the page never shows one view and then swaps
        await self.recover_system()
        self.apply_theme()
        if view is not None:
            self.state.mode = view
        self.arrange()
        # The page's key event never reports Shift on its own, so a listener tracks it for
        # shift+click (decision 0019).
        page.add(
            ft.KeyboardListener(
                self.outer,
                autofocus=True,
                expand=True,
                on_key_down=lambda e: self.keyboard_down(e.key),
                on_key_up=lambda e: self.keyboard_up(e.key),
            )
        )
        if self.appearance_error:
            self.notice("Appearance", self.appearance_error)
        print("CASSIM: UI", flush=True)  # the first screen is on its way (tools/loadtime.py)
        if self.runner is not None:
            self.status.value = "Starting the calculator engine..."
        try:
            await self.recover()
        finally:
            self.starting = False
            self.status.value = ""
        if settings is not None:
            self.state.document.use(settings)
        self.refresh()
        self.offer_shared(self.shell.route)
        print("CASSIM: READY", flush=True)

    def autosave(self) -> None:
        """Save the document AUTOSAVE_DELAY after the last change, so a reload or crash loses
        nothing (FR-DOC-003). Each change pushes the save back; one save task waits for it."""
        if self.starting:
            return
        self.save_at = time.monotonic() + AUTOSAVE_DELAY
        if not self.save_waiting:
            self.save_waiting = True
            self.page.run_task(self.save_later)

    async def save_later(self) -> None:
        while (wait := self.save_at - time.monotonic()) > 0:
            await asyncio.sleep(wait)
        self.save_waiting = False
        self.save_now()

    def save_now(self) -> None:
        """Autosave the document at once, if it changed since the last autosave, and update the
        unsaved-changes marker. This is the working state only: the named copy changes only on
        Save (FR-DOC-010)."""
        data = to_dict(self.state.document)
        text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        if text != self.saved:
            self.saved = text
            self.shell.write(AUTOSAVE_KEY, text)
        self.mark(fingerprint(data))

    def mark(self, printed: str) -> None:
        """Show whether the document (with fingerprint `printed`) has unsaved changes."""
        dirty = printed != self.current.saved
        if dirty != self.dirty:
            self.dirty = dirty
            self.state.doc_title = self.doc_title()
            self.view.set_doc_title(self.state.doc_title)
            self.page.update()

    def doc_title(self) -> str:
        """The title bar's middle: the document's name, or in full screen (no toolbar row) a
        status message while there is one."""
        if self.full and self.status.value:
            return str(self.status.value)
        return title(self.state.document.name, dirty=self.dirty)

    @property
    def current(self) -> Current:
        """The open document's link to its saved copy (`self.documents`)."""
        return self.documents.current

    @current.setter
    def current(self, current: Current) -> None:
        self.documents.current = current

    def remember(self, current: Current) -> None:
        """Link the open document to its saved copy (or to none) and keep that with the
        autosave, so the name and the marker survive a reload."""
        self.documents.remember(current)
        self.on_documents_change(redraw=False)

    def on_documents_change(self, *, redraw: bool = True) -> None:
        """The open document or its link changed (saved, opened, deleted): the title's marker."""
        self.dirty = document_fingerprint(self.state.document) != self.current.saved
        self.state.doc_title = self.doc_title()
        if redraw:
            self.refresh()

    def dump_named(self, name: str) -> str:
        """The document as saved under `name`, which becomes its name."""
        document = self.state.document
        document.name = name
        return json.dumps(to_dict(document), ensure_ascii=False, separators=(",", ":"))

    async def load_named(self, text: str, name: str) -> None:
        """Open a saved document: replayed by this app's engine (a DocumentFileError, which is a
        ValueError, if it cannot be)."""
        self.replace(await self.read(text))
        self.state.document.name = name

    def said(self, text: str) -> None:
        self.flash(text)
        if self.debug:
            print(f"CASSIM: SAVED {self.current.stored}", flush=True)

    def on_name_dialog(self, dialog: ft.AlertDialog | None) -> None:
        """Save as is open: its name box takes the keys, not the calculator."""
        self.typing_dialog = dialog

    async def recover_system(self) -> None:
        """Reopen the saved System Settings, if any, and pick the view to start in. A phone is
        always in Handheld, whatever start view was saved; with nothing saved, the window's size
        picks the view (and keeps picking it as the window changes, until a view is chosen)."""
        self.appearance_error = await self.shell.load_appearance()
        saved = await self.shell.read(SYSTEM_KEY)
        if saved is not None:
            self.state.system = System.loads(saved)
            start = self.state.system.start_mode
            self.state.mode = (
                starting_mode(self.page.width, self.page.height) if self.phone else start
            )
        else:
            self.first_visit = True
            self.state.mode = starting_mode(self.page.width, self.page.height)

    async def recover(self) -> None:
        """Reopen the autosaved document, if it is readable."""
        await self.documents.store.index()  # read now, so the dialogs can check names at once
        self.state.doc_title = self.doc_title()
        text = await self.shell.read(AUTOSAVE_KEY)
        if text is None:
            return
        try:
            self.replace(await self.read(text))
            self.saved = text
            link = await self.shell.read(CURRENT_KEY)
            current = Current.loads(link)
            if link is None:  # an autosave from before named documents: count it as saved
                current.saved = document_fingerprint(self.state.document)
            self.current = current
            self.dirty = document_fingerprint(self.state.document) != current.saved
            self.state.doc_title = self.doc_title()
            if self.debug:  # the end-to-end tests check what came back
                count = sum(len(problem.pages) for problem in self.state.document.problems)
                print(f"CASSIM: RECOVERED {count} pages", flush=True)
        except DocumentFileError:
            return  # a damaged autosave is ignored, and overwritten by the next change

    def body_size(self) -> tuple[float, float]:
        """The screen's room under its title bar, for a page that draws to size (the sheet)."""
        state = self.state
        title = state.px(TITLE_H)
        if state.mode.device:
            return state.px(SCREEN_W), (self.view.control.height or state.px(SCREEN_H)) - title
        widths, _ = computer_columns(
            self.page.width,
            state.system.computer_sidebar_width,
            state.system.computer_keypad_width,
            keypad_visible=state.system.computer_keypad,
        )
        height = self.view.control.height or computer_screen_height(self.page.height)
        return max(widths["workspace"], 200.0), max(height - title, 120.0)

    def refresh(self) -> None:
        start = time.perf_counter()
        self.state.prepare()  # a sheet takes the engine's replies first
        self.state.doc_title = self.doc_title()
        self.autosave()
        self.view.refresh()
        self.view.show_pointer(self.pointer)
        self.keypad.refresh()
        if self.state.mode is Mode.COMPUTER:  # the sidebar is not shown in Tablet or Handheld
            self.sidebar.refresh()
        self.place_status()
        built = time.perf_counter()
        self.page.update()
        self.view.follow_selection()
        if self.keytime:
            self.show_key_time((built - start) * 1000, (time.perf_counter() - built) * 1000)
        if self.debug:  # tools/switchtime.py times a page change by this line (NFR-PERF-006)
            document = self.state.document
            here = (document.problem, document.page)
            if here != self.shown:
                self.shown = here
                build = (built - start) * 1000
                send = (time.perf_counter() - built) * 1000
                print(
                    f"CASSIM: PAGE {here[0] + 1}.{here[1] + 1} build={build:.0f} send={send:.0f}",
                    flush=True,
                )
            self.print_sheet()
        self.kick()
        self.drain_typeahead()

    def drain_typeahead(self) -> None:
        """Run the keys typed while the engine worked, in order, until one sends an entry to
        the engine again (the rest wait for that run)."""
        if self.draining:
            return  # a key's own redraw: the loop below goes on
        self.draining = True
        try:
            while self.typeahead and not self.busy and not self.engine_owed():
                if self.typing_dialog is not None and self.typing_dialog.open:
                    self.typeahead.clear()  # keys meant for the screen do not go behind a dialog
                    break
                key = self.typeahead.popleft()
                if isinstance(key, str):
                    self.press(key)
                elif key.action == "paste":  # reads the clipboard: the rest wait for it
                    self.page.run_task(self.run_binding, key)
                    break
                elif key.action in ("undo", "redo") and self.variable_history_action(key.action):
                    self.refresh()
                else:
                    self.pointer.hide()
                    self.state.run(key)
                    self.refresh()
        finally:
            self.draining = False

    def engine_owed(self) -> bool:
        """An entry is waiting for the engine (Enter was pressed, the run not started yet)."""
        calculator = calculator_of(self.state.document.current)
        return calculator is not None and calculator.pending is not None

    def show_key_time(self, build: float, send: float) -> None:
        """The last redraw's cost in the status line and the console (`CASSIM: KEY`): `build` is
        Python making the controls, `send` is Flet working out what changed and sending it. The
        browser's own drawing time comes after both and is not in either."""
        self.status.value = f"build {build:.0f} ms, send {send:.0f} ms"
        print(f"CASSIM: KEY build={build:.0f} send={send:.0f}", flush=True)
        with contextlib.suppress(RuntimeError):  # not on a page (the tests' stand-in page)
            self.status.update()

    def place_status(self) -> None:
        """The status line goes in the toolbar row, or in full screen (which has no toolbar row)
        in the middle of the screen's title bar, in place of the name while it has something to
        say."""
        if self.full:
            self.toolbar.controls = []
        else:
            self.toolbar.controls = [*self.toolbar_controls(), self.status, self.sink_box]
        self.state.doc_title = self.doc_title()
        self.view.set_doc_title(self.state.doc_title)

    def print_sheet(self) -> None:
        """`CASSIM: SHEET A2 16`: the cursor's cell and what it shows, when that changes. The
        end-to-end tests read the sheet this way; its canvas has nothing to read."""
        sheet = self.state.sheet
        if sheet is None:
            return
        screen = sheet.screen()
        line = f"{screen.address} {screen.cells.get(sheet.cursor, ('', False))[0]}".strip()
        if line != self.sheet_line:
            self.sheet_line = line
            print(f"CASSIM: SHEET {line}", flush=True)
        selection = screen.address if screen.selection is not None else ""
        if selection != self.sheet_selection_line:
            self.sheet_selection_line = selection
            print(f"CASSIM: SHEET SELECTION {selection or 'NONE'}", flush=True)

    # ---- the engine -------------------------------------------------------------------------

    @property
    def busy(self) -> bool:
        return (
            self.starting
            or self.sheet_file_busy
            or (self.runner is not None and not self.runner.idle)
        )

    @property
    def running(self) -> bool:
        """An entry is being calculated, so Esc can cancel it."""
        return self.runner is not None and self.runner.status is Status.BUSY

    async def read(self, text: str) -> Document:
        """A document from its text, replayed by whichever engine this app uses."""
        return loads(text) if self.runner is None else await self.runner.load(text, PAGES)

    def replace(self, document: Document) -> None:
        self.variable_undo.clear()
        self.variable_redo.clear()
        self.state.replace_document(document)
        if self.runner is not None:
            self.runner.retain(document)

    def kick(self) -> None:
        """Start whatever the engine owes the screen: a queued entry, or queued settings."""
        runner = self.runner
        if self.sheet_file_busy or runner is None or not runner.idle:
            return
        calculator = calculator_of(self.state.document.current)
        if calculator is not None and calculator.pending is not None:
            self.page.run_task(self.run_pending, calculator)
        elif runner.dirty(self.state.document):
            self.page.run_task(self.run_sync)

    async def run_pending(self, calculator: Calculator) -> None:
        assert self.runner is not None
        self.say("Calculating... press Esc to cancel")
        finished = await self.runner.evaluate(calculator)
        if self.debug:  # the end-to-end tests read the canvas app through the console
            history = calculator.history
            shown = history[-1].result.text if finished and history else ""
            print("CASSIM: RESULT " + shown if finished else "CASSIM: CANCELLED", flush=True)
        self.status.value = "" if finished else "Cancelled"
        self.refresh()

    async def run_sync(self) -> None:
        assert self.runner is not None
        await self.runner.sync(self.state.document)
        self.refresh()

    async def cancel(self) -> None:
        assert self.runner is not None
        self.say("Cancelling... restarting the calculator")
        await self.runner.cancel()
        self.status.value = ""
        if self.debug:
            print("CASSIM: RESTARTED", flush=True)
        self.refresh()

    def press(self, name: str) -> None:
        if self.busy:
            if name == "esc":
                self.typeahead.clear()
                if self.running:
                    self.page.run_task(self.cancel)
            else:
                self.keep(name)  # a keypad key, run when the engine is free
            return
        self.pointer.hide()  # a key press puts the pointer away
        self.state.press_keypad(name)
        self.refresh()

    def hold_keypad_arrow(self, name: str, down: bool) -> None:
        if not down:
            if self.pad_hold == name:
                self.pad_hold = None
                self.pad_hold_generation += 1
            return
        self.pad_hold = None
        self.pad_hold_generation += 1
        pending = self.state.pending
        self.press(name)
        if self.busy or pending:
            return
        self.pad_hold = name
        self.page.run_task(self._repeat_keypad_arrow, name, self.pad_hold_generation)

    async def _repeat_keypad_arrow(self, name: str, generation: int) -> None:
        started = time.monotonic()
        await asyncio.sleep(REPEAT_DELAY)
        while self.pad_hold == name and self.pad_hold_generation == generation and not self.busy:
            self.press(name)
            await asyncio.sleep(repeat_interval(time.monotonic() - started))

    def press_cassim(self) -> None:
        if self.busy:
            return
        ctrl = self.state.pending == "ctrl"
        self.state.clear_pending()
        if ctrl and self.installable:
            self.install()
        else:
            self.state.run_action("open_menu", "cassim")
        self.refresh()

    # ---- the pointer that the keypad's centre key steers -----------------------------------

    def on_stick(self, event: str, dx: float, dy: float) -> None:
        """The centre key as a joystick (see `Keypad.on_stick`). A tap with the pointer showing
        clicks where it is; with it hidden, the key does its usual `select`."""
        pointer = self.pointer
        if event == "tap":
            place = pointer.click()
            if place is None:
                self.press(STICK_KEY)
            elif not self.busy:
                if not self.view.click_at(*place):
                    # no hit test on this page, or its sizes not in yet: select as before
                    self.state.press_keypad(STICK_KEY)
                self.refresh()
            return
        if event == "start":
            pointer.resize(*self.body_size())
            pointer.press()
            if self.view.measuring:
                self.show_pointer()
            else:  # redraw once with the history reporting its sizes, for clicks
                self.view.measuring = True
                self.refresh()
            if not self.ticking:
                self.page.run_task(self.steer)
        elif event == "move":
            pointer.drag(dx, dy)
        else:
            pointer.release()

    def show_pointer(self) -> None:
        """Send only the arrow: a whole refresh per step would be far too slow on a phone."""
        self.view.show_pointer(self.pointer)
        with contextlib.suppress(RuntimeError):  # not on a page (the tests' stand-in page)
            self.view.pointer.update()

    async def steer(self) -> None:
        """Move the pointer while it shows; the loop ends when it hides."""
        self.ticking = True
        try:
            last = time.monotonic()
            while self.pointer.visible:
                await asyncio.sleep(POINTER_TICK)
                now = time.monotonic()
                if self.pointer.step(now - last):
                    self.show_pointer()
                last = now
            self.show_pointer()  # hidden by a key press between steps
        finally:
            self.ticking = False
            self.view.measuring = False  # the next refresh stops the size reports

    def on_lifecycle(self, e: ft.AppLifecycleStateChangeEvent) -> None:
        """A key-up is lost when the window loses focus, so drop Shift then. A tab that is hidden
        may be closed without warning, so a waiting autosave is done at once."""
        if e.state is not ft.AppLifecycleState.RESUME:
            self.shift = False
            self.arrow_event = None
            self.pad_hold = None
            self.pad_hold_generation += 1
        if e.state in (ft.AppLifecycleState.HIDE, ft.AppLifecycleState.PAUSE) and self.save_waiting:
            self.save_now()

    def track_shift(self, key: str, *, down: bool) -> None:
        if "shift" in key.lower():
            self.shift = down

    def keyboard_down(self, key: str) -> None:
        self.track_shift(key, down=True)
        if any(modifier in key.lower() for modifier in ("shift", "control", "alt", "meta")):
            self.arrow_event = None

    def keyboard_up(self, key: str) -> None:
        self.track_shift(key, down=False)
        released_arrow = self.arrow_event is not None and key_name(key) == key_name(
            self.arrow_event.key
        )
        if released_arrow or any(
            modifier in key.lower() for modifier in ("shift", "control", "alt", "meta")
        ):
            self.arrow_event = None

    async def repeat_arrow(self, event: ft.KeyboardEvent) -> None:
        started = time.monotonic()
        await asyncio.sleep(REPEAT_DELAY)
        while self.arrow_event is event:
            if not self.busy:  # a held arrow does not pile up keys while the engine works
                await self._handle_key(event)
            await asyncio.sleep(repeat_interval(time.monotonic() - started))

    def show_wizard(self, wizard: Wizard) -> None:
        self.typing_dialog = wizard_dialog(
            self.page, self.state, wizard, self.refresh, problem_colour=self.theme.problem_text
        )

    async def on_key(self, e: ft.KeyboardEvent) -> None:
        key = key_name(e.key)
        if key in ARROW_KEYS:
            if self.arrow_event is not None and key_name(self.arrow_event.key) == key:
                return  # native key-repeat must not restart our slower, accelerated repeat timer
            self.arrow_event = e
        elif self.arrow_event is not None:
            self.arrow_event = None
        await self._handle_key(e)
        if self.arrow_event is e:
            self.page.run_task(self.repeat_arrow, e)

    async def _handle_key(self, e: ft.KeyboardEvent) -> None:
        state = self.state
        if self.typing_dialog is not None and self.typing_dialog.open:
            return  # keys typed into a dialog's boxes are not calculator keys
        self.shift = e.shift
        binding = state.binding_for(e.key, shift=e.shift, ctrl=e.ctrl, alt=e.alt, meta=e.meta)
        if binding is None:
            return
        if binding.action == "escape":
            state.clear_pending()
        if self.sink_focused and binding.action in ("insert", "backspace", "enter"):
            return  # typed into the hidden box: on_sink turns it into keys
        if self.busy:  # Esc cancels the run and what was typed after it; other keys wait
            if binding.action == "escape":
                self.typeahead.clear()
                if self.running:
                    await self.cancel()
                else:
                    self.refresh()
            else:
                self.keep(binding)
            return
        await self.run_binding(binding)

    async def run_binding(self, binding: Binding) -> None:
        """One key, typed now or kept while the engine worked."""
        if binding.action == "paste":  # the system clipboard may hold text from elsewhere
            binding = Binding("paste", await self.shell.pasted())
        if binding.action in ("undo", "redo") and self.variable_history_action(binding.action):
            self.refresh()
            return
        self.pointer.hide()
        self.state.run(binding)
        self.refresh()

    def keep(self, key: Binding | str) -> None:
        """Keep a key typed while the engine works; when the queue is full, later keys are
        refused rather than the first ones lost."""
        if len(self.typeahead) < TYPEAHEAD:
            self.typeahead.append(key)

    # ---- the on-screen keyboard (Computer view on a phone or tablet) --------------------------

    @property
    def soft_keyboard(self) -> bool:
        return self.state.mode is Mode.COMPUTER and self.shell.offers.touch

    def on_sink(self, _: object = None) -> None:
        """Keys typed on the on-screen keyboard reach the calculator."""
        keys = keys_for(self.sink.value or "")
        self.sink.value = SENTINEL
        if self.busy:
            for key in keys:
                self.keep(key)
            return
        for binding in keys:
            if binding.action in ("undo", "redo") and self.variable_history_action(binding.action):
                continue
            self.state.run(binding)
        self.refresh()

    def on_sink_submit(self, _: object = None) -> None:
        self.on_sink()
        if self.busy:
            self.keep(Binding("enter"))  # after the characters it follows
        else:
            self.state.run(Binding("enter"))
            self.refresh()
        self.page.run_task(self.sink.focus)  # Enter would otherwise close the keyboard

    def offer_keyboard(self, action: str) -> None:
        """After a tap where typing goes, open the on-screen keyboard."""
        if self.debug and action in TYPING_ACTIONS:
            print(f"CASSIM: KEYBOARD {action} touch={self.soft_keyboard}", flush=True)
        if action in TYPING_ACTIONS and self.soft_keyboard:
            self.page.run_task(self.sink.focus)

    def request_paste(self) -> None:
        self.page.run_task(self.paste_from_clipboard)

    async def paste_from_clipboard(self) -> None:
        """Paste the system clipboard into the entry line (the keypad's ctrl+v)."""
        self.state.paste_text(await self.shell.pasted())
        self.refresh()

    def act(self, action: Action, arg: str = "") -> None:
        if self.busy:
            return
        if action == "statistics_eval":
            self.page.run_task(self.run_statistics_eval, arg)
            return
        self.state.run_action(action, arg)
        self.refresh()
        self.offer_keyboard(action)

    async def run_statistics_eval(self, expression: str) -> None:
        statistics = self.state.statistics
        if statistics is None:
            return
        self.say("Updating data...")
        if isinstance(statistics.session, RemoteSession):
            if self.runner is None:
                msg = "a remote Data & Statistics session requires the Runner"
                raise RuntimeError(msg)
            calculator = Calculator(statistics.session)
            calculator.pending = Pending(expression, False)
            finished = await self.runner.evaluate(calculator)
            if not finished:
                statistics.message = "Update cancelled."
            elif calculator.history:
                statistics.message = calculator.history[-1].result.error or ""
            else:
                msg = "the engine accepted no point update result"
                raise RuntimeError(msg)
        else:
            result = statistics.session.eval(expression, approximate=False)
            statistics.message = result.error or ""
        self.status.value = ""
        self.refresh()

    def cycle_setting(self, name: str) -> None:
        """A click on Rad/Deg, Auto/Approx or Real/Rect/Polar in the title bar."""
        if self.busy:
            return
        self.state.document.set(**{name: next_choice(self.state.document.settings, name)})
        self.refresh()

    def on_resize(self, e: ft.PageResizeEvent) -> None:
        """Keep the layout fitted to the window. A first visit follows its size until a view is
        chosen; a phone follows its orientation (Handheld upright, Tablet on its side), and so
        does a window that shrinks to phone size."""
        now = is_landscape(e.width, e.height)
        turned, self.landscape = self.landscape is not None and now != self.landscape, now
        mode = self.state.mode.value
        if repick_view(e.width, e.height, mode, chosen=not self.first_visit, turned=turned):
            self.state.mode = starting_mode(e.width, e.height)
        self.arrange()
        self.refresh()

    @property
    def phone(self) -> bool:
        """A phone-sized window (its short side is narrow): only Handheld view is offered, with no
        splitter and a thinner margin."""
        return page_is_phone(self.page)

    @property
    def installable(self) -> bool:
        """The browser has offered to install CASSim and it is not installed yet."""
        return self.shell.offers.installable

    def install(self) -> None:
        self.shell.install()

    def toggle_cutout(self) -> None:
        """CASSim > Avoid cutout, on an installed phone: draw clear of the camera cutout."""
        self.use_cutout = not self.use_cutout
        self.arrange()
        self.refresh()

    def on_bridge(self) -> None:
        """The page reported a change in browser capabilities or offline/update status."""
        if self.state.menu is not None and self.state.menu.root.label == about.product_name():
            root = self.cassim_menu()
            if self.state.menu.root != root:
                self.state._open_menu("cassim")
        self.arrange()
        self.refresh()

    def cassim_menu(self) -> MenuItem:
        return MenuItem(
            about.product_name(),
            items=cassim_items(
                self.shell.offers,
                nspire_menu(
                    view=self.state.mode,
                    phone=self.phone,
                    use_cutout=self.use_cutout,
                    home=self.shell.home is not None,
                    keypad=self.state.system.computer_keypad,
                ),
            ),
        )

    def toggle_keypad(self) -> None:
        """Show or hide the keypad beside the screen in Computer mode (kept with the settings)."""
        system = self.state.system
        system.computer_keypad = not system.computer_keypad
        self.arrange()
        self.on_system_change()

    def set_mode(self, mode: Mode) -> None:
        if mode is Mode.COMPUTER and self.phone:
            return  # no room on a phone for Computer view and the on-screen keyboard
        self.first_visit = False
        self.state.mode = mode
        self.arrange()
        self.refresh()

    def toolbar_controls(self) -> list[ft.Control]:
        theme, mode = self.theme, self.state.mode
        if mode.device:
            return []  # the keypad has the Doc, Menu and CASSim keys

        def button(text: str, action: Callable[[], None], fill: str, colour: str) -> ft.Container:
            return ft.Container(
                label_text(text, size=13, color=colour, no_wrap=True),
                expand=True,
                height=36,
                alignment=ft.Alignment.CENTER,
                bgcolor=fill,
                border_radius=6,
                ink=True,
                on_click=lambda _: action(),
            )

        mode_control = ft.SegmentedButton(
            segments=[
                ft.Segment(value=Mode.HANDHELD.value, label="Handheld"),
                ft.Segment(value=Mode.TABLET.value, label="Tablet"),
                ft.Segment(value=Mode.COMPUTER.value, label="Computer"),
            ],
            selected=[mode.value],
            show_selected_icon=False,
            expand=True,
            style=ft.ButtonStyle(
                bgcolor={
                    ft.ControlState.SELECTED: theme.accent,
                    ft.ControlState.DEFAULT: theme.key,
                },
                color={
                    ft.ControlState.SELECTED: theme.accent_text,
                    ft.ControlState.DEFAULT: theme.key_text,
                },
                padding=ft.Padding.symmetric(horizontal=4, vertical=5),
                text_style=ft.TextStyle(size=12),
            ),
            on_change=lambda e: self.set_mode(Mode(e.control.selected[0])),
        )
        keypad = button(
            "Keypad",
            self.toggle_keypad,
            theme.accent if self.state.system.computer_keypad else theme.key,
            theme.accent_text if self.state.system.computer_keypad else theme.key_text,
        )
        keypad.expand = False
        keypad.width = 76
        cassim = button(
            about.product_name(),
            lambda: self.act("open_menu", "cassim"),
            theme.accent,
            theme.accent_text,
        )
        cassim.tooltip = needs_attention_tooltip(self.shell.offers)
        if self.shell.offers.needs_attention:
            cassim.content = ft.Row(
                [
                    label_text(about.product_name(), size=13, color=theme.accent_text),
                    ft.Icon(ft.Icons.CIRCLE, size=8, color=self.theme.attention),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=4,
            )
        doc_fill, doc_text = theme.key_colours("nav")
        # named as the dialog it opens (SDD-15 section 9.2), so it takes more of the row
        document_settings = button(
            "Document settings", self.open_settings, theme.key, theme.key_text
        )
        document_settings.expand = 2
        undo = ft.IconButton(
            icon=ft.Icons.UNDO,
            tooltip="Undo (Ctrl+Z)",
            on_click=lambda _: self.undo_action(),
            icon_color=theme.key_text,
            bgcolor=theme.key,
            icon_size=15,
            width=42,
            height=36,
            padding=4,
        )
        redo = ft.IconButton(
            icon=ft.Icons.REDO,
            tooltip="Redo (Ctrl+Y)",
            on_click=lambda _: self.redo_action(),
            icon_color=theme.key_text,
            bgcolor=theme.key,
            icon_size=15,
            width=42,
            height=36,
            padding=4,
        )
        return [
            ft.Row([mode_control, keypad], spacing=4),
            ft.Row(
                [
                    cassim,
                    button("Doc", lambda: self.act("open_menu", "doc"), doc_fill, doc_text),
                    document_settings,
                ],
                spacing=4,
            ),
            ft.Row(
                [
                    undo,
                    redo,
                    button(
                        "Menu",
                        lambda: self.act("open_menu", "menu"),
                        theme.accent,
                        theme.accent_text,
                    ),
                ],
                spacing=4,
            ),
            ft.Row(
                [
                    button(
                        "Page manager",
                        lambda: self.act("dialog", SORTER),
                        theme.key,
                        theme.key_text,
                    ),
                    button("+ Page", lambda: self.act("add_page"), theme.key, theme.key_text),
                    button("+ Problem", lambda: self.act("add_problem"), theme.key, theme.key_text),
                ],
                spacing=4,
            ),
        ]

    def delete_variables(self, variables: tuple[VariableInfo, ...]) -> None:
        if not variables or self.busy:
            return
        problem = self.state.document.problems[self.state.document.problem]
        calculator = next(
            (
                model
                for page in problem.pages
                if (model := calculator_of(page)) is not None
                and model.pending is None
                and model.error is None
            ),
            None,
        )
        if calculator is None:
            self.notice(
                "Delete variables",
                "Add a Calculator page to this Problem before deleting variables.",
            )
            return
        sources = tuple(variable.source for variable in variables)
        if any(not source for source in sources):
            self.notice("Delete variables", "One or more variables cannot be restored.")
            return
        names = tuple(variable.name for variable in variables)
        self.page.run_task(self._delete_variables, calculator, names, sources)

    async def _delete_variables(
        self, calculator: Calculator, names: tuple[str, ...], sources: tuple[str, ...]
    ) -> None:
        if await self._calculator_command(calculator, f"DelVar {','.join(names)}"):
            self.variable_undo.append(VariableDeletion(calculator, sources, names))
            self.variable_redo.clear()
            self.flash(f"Deleted {', '.join(names)}. Ctrl+Z to restore.")
        self.refresh()

    async def _calculator_command(self, calculator: Calculator, command: str) -> bool:
        saved_editor = calculator.editor
        calculator.editor = Editor()
        calculator.editor.insert_linear(command)
        try:
            calculator.perform(Binding("enter"))
            if calculator.pending is not None:
                if self.runner is None:
                    msg = "a local calculator left a command pending"
                    raise RuntimeError(msg)
                await self.runner.evaluate(calculator)
        finally:
            calculator.editor = saved_editor
        if not calculator.history or calculator.history[-1].result.error is not None:
            error = calculator.history[-1].result.error if calculator.history else "No result"
            self.notice("Variable change failed", str(error))
            return False
        return True

    def variable_history_action(self, action: str) -> bool:
        history = self.variable_undo if action == "undo" else self.variable_redo
        if not history or self.busy:
            return False
        self.page.run_task(self._apply_variable_history, action)
        return True

    async def _apply_variable_history(self, action: str) -> None:
        source = self.variable_undo if action == "undo" else self.variable_redo
        target = self.variable_redo if action == "undo" else self.variable_undo
        change = source[-1]
        commands = change.sources if action == "undo" else (f"DelVar {','.join(change.names)}",)
        for command in commands:
            if not await self._calculator_command(change.calculator, command):
                self.refresh()
                return
        source.pop()
        target.append(change)
        self.flash("Restored variables" if action == "undo" else "Deleted variables")
        self.refresh()

    def undo_action(self) -> None:
        if not self.variable_history_action("undo"):
            self.state.run_action("undo_pages")
            self.refresh()

    def redo_action(self) -> None:
        if not self.variable_history_action("redo"):
            self.state.run_action("redo_pages")
            self.refresh()

    def show_dialog(self, name: str) -> None:
        dialogs: dict[str, Callable[[], object]] = {
            "cutout": self.toggle_cutout,
            "view:computer": lambda: self.set_mode(Mode.COMPUTER),
            "view:handheld": lambda: self.set_mode(Mode.HANDHELD),
            "view:tablet": lambda: self.set_mode(Mode.TABLET),
            "panel:keypad": self.toggle_keypad,
            "settings": lambda: self.open_system_settings("Settings"),
            "appearance": self.open_appearance,
            "save": self.documents.save,
            "save_as": self.documents.save_as,
            "open_document": self.documents.open,
            "export_file": lambda: self.page.run_task(self.export_file),
            "import_file": lambda: self.ask_discard(lambda: self.page.run_task(self.import_file)),
            "sheet_import_csv": lambda: self._start_sheet_file_action("csv", importing=True),
            "sheet_export_csv": lambda: self._start_sheet_file_action("csv", importing=False),
            "sheet_import_xlsx": lambda: self._start_sheet_file_action("xlsx", importing=True),
            "sheet_export_xlsx": lambda: self._start_sheet_file_action("xlsx", importing=False),
            "share_link": self.share_link,
            "document_settings": self.open_settings,
            "system_settings": lambda: self.open_system_settings("Handheld setup"),
            "home": lambda: self.shell.home() if self.shell.home is not None else None,
        }
        dialog = dialogs.get(name)
        if dialog is not None:
            dialog()
        else:
            self.shell.menu_action(name, HELP_PAGE)  # install, update, help... (every app's)

    def open_system_settings(self, title: str) -> None:
        """System Settings, titled after the item that opened it (SDD-15 section 9.2)."""
        dialog = system_settings_dialog(
            self.page, self.state, self.on_system_change, self.theme, self.open_appearance
        )
        dialog.title = ft.Text(title)

    def has_unsaved(self) -> bool:
        """The document has changes since it was last saved (so a reload asks first)."""
        return self.documents.dirty()

    def say(self, text: str) -> None:
        """Show `text` in the status line now, without redrawing the rest."""
        self.status.value = text
        self.place_status()
        self.page.update()

    def flash(self, text: str) -> None:
        """Show `text` in the status line for a moment."""
        self.say(text)

        async def clear() -> None:
            await asyncio.sleep(FLASH_SECONDS)
            if self.status.value == text:
                self.say("")

        self.page.run_task(clear)

    def ask_discard(self, then: Callable[[], object]) -> None:
        """Do `then` (which replaces the document) at once, or after asking when the open
        document has changes that are not saved (every app's question, `app/saved.py`)."""

        def go() -> None:
            then()
            self.refresh()

        self.documents.ask_discard(go)

    def on_new_document(self) -> None:
        """A new document is saved nowhere, and has nothing to lose yet."""
        self.variable_undo.clear()
        self.variable_redo.clear()
        self.remember(Current(None, document_fingerprint(self.state.document)))

    # ---- files on disk: Import and Export (FR-DOC-004, FR-DOC-006) ----------------------------

    async def export_file(self) -> None:
        """Download the document as `.cassim.json`."""
        document = self.state.document
        await self.shell.save_file(file_name(document), dumps(document), "Export document")

    async def import_file(self) -> None:
        """Open a `.cassim.json` file. It is not in the browser's library until it is saved,
        so it shows as unsaved."""
        try:
            text = await self.shell.pick_file(OPEN_EXTENSIONS, "Import document")
            if text is None:
                return
            self.replace(await self.read(text))
            self.remember(Current(None, ""))
        except (DocumentFileError, UnicodeDecodeError) as error:
            self.notice("Cannot open that file", str(error))
        self.refresh()

    def _start_sheet_file_action(self, kind: str, *, importing: bool) -> None:
        if self.sheet_file_busy:
            return
        self.sheet_file_busy = True
        self.page.run_task(self._sheet_file_action, kind, importing)

    async def _sheet_file_action(self, kind: str, importing: bool) -> None:
        try:
            sheet = self.state.sheet
            if sheet is None:
                return
            if importing:
                data = await self.shell.pick_file_bytes((kind,), f"Import {kind.upper()} data")
                if data is None:
                    return
                rows = read_csv(data) if kind == "csv" else read_xlsx(data)
                sheet.import_rows(rows)
                if self.runner is not None:
                    await self.runner.sync(self.state.document)
                sheet.update()
            else:
                if self.runner is not None:
                    await self.runner.sync(self.state.document)
                sheet.update()
                sheet.request_export_view()
                if self.runner is not None:
                    await self.runner.sync(self.state.document)
                sheet.update()
                rows = sheet.export_rows(formulas=kind == "xlsx")
                if kind == "csv":
                    data = write_csv([[cell.text for cell in row] for row in rows])
                else:
                    data = write_xlsx(rows)
                await self.shell.save_bytes_file(
                    f"spreadsheet.{kind}", data, f"Export {kind.upper()} data"
                )
        except (OSError, ValueError) as error:
            operation = "import" if importing else "export"
            self.notice(f"Cannot {operation} {kind.upper()} data", str(error))
        finally:
            self.sheet_file_busy = False
            self.refresh()

    def share_link(self) -> None:
        """Copy a link that holds the document in its fragment (FR-DOC-007)."""
        try:
            fragment = encode(self.state.document)
        except LinkTooLongError as error:
            self.notice("Too big for a link", f"{error}. Use Doc ▸ File ▸ Export file… instead.")
            return
        self.shell.copy(self.shell.link(fragment))
        self.notice("Link copied", "Anyone with the link can open this document. Nothing is sent.")

    def offer_shared(self, fragment: str) -> None:
        """A page opened from a share link asks before replacing the document (FR-DOC-007). The
        hash URL strategy makes the fragment `/doc=...` the page's route."""
        try:
            text = unpack(fragment.lstrip("/"))
            name = "Untitled" if text is None else str(parse(text).get("name", "Untitled"))
        except DocumentFileError as error:
            self.notice("Cannot open that link", str(error))
            return
        if text is None:
            return

        async def accept() -> None:
            try:
                self.replace(await self.read(text))
                self.remember(Current(None, ""))  # not saved in this app yet
            except DocumentFileError as error:
                self.notice("Cannot open that link", str(error))
            self.refresh()

        self.shell.confirm(
            "Open shared document?",
            f"“{name}” came from a link. It replaces what is open now; "
            "nothing in it runs until you run it.",
            "Open",
            accept,
        )

    def notice(self, title: str, message: str) -> None:
        self.shell.notice(title, message)

    def on_system_change(self) -> None:
        self.shell.write(SYSTEM_KEY, self.state.system.dumps())
        self.apply_theme()
        self.arrange()  # the letter layout changes the keypad's size
        self.refresh()

    def open_appearance(self) -> None:
        """CASSim's shared Appearance dialog; its colour boxes take the keyboard."""

        def save(appearance: Appearance) -> None:
            self.shell.save_appearance(appearance)
            self.on_appearance_change()

        def preview(appearance: Appearance) -> None:
            self.apply_theme(appearance)
            self.refresh()

        self.typing_dialog = appearance_dialog(
            self.page, self.shell.appearance, save, on_preview=preview
        ).dialog

    def on_appearance_change(self) -> None:
        self.apply_theme()
        self.arrange()
        self.refresh()

    def apply_theme(self, appearance: Appearance | None = None) -> None:
        """Draw in the shared theme, or in `appearance` while the dialog previews it."""
        appearance = appearance or self.shell.appearance
        theme = appearance.theme
        self.page.theme_mode = appearance.mode
        self.page.bgcolor = theme.background
        self.status.color = theme.status_text
        if theme == self.theme:
            return
        self.theme = self.shell.theme = theme
        self.view = CalculatorView(
            self.state, theme, self.act, lambda: self.shift, self.cycle_setting
        )
        self.view.body_size = self.body_size
        self.keypad = Keypad(
            self.state, self.press, theme, on_cassim=self.press_cassim, on_stick=self.on_stick
        )
        self.sidebar.theme = theme
        self.shape = None

    def open_settings(self) -> None:
        settings_dialog(self.page, self.state, self.refresh, self.theme)

    def handheld_room(
        self, *, phone: bool, full: bool, margin: int
    ) -> tuple[float | None, float | None]:
        """Set the outer padding and return the viewport inside the selected safe area."""
        top, right, bottom, left = (
            self.shell.offers.safe_area
            if phone and self.shell.offers.installed and not self.use_cutout
            else (0, 0, 0, 0)
        )
        self.outer.padding = ft.Padding.only(
            top=top + (0 if full else margin),
            right=right + margin,
            bottom=bottom + margin,
            left=left + margin,
        )
        width = max(1, self.page.width - left - right) if self.page.width else None
        height = max(1, self.page.height - top - bottom) if self.page.height else None
        return width, height

    def arrange(self) -> None:
        state = self.state
        system = state.system
        if self.landscape is None:  # the shape the first layout had, for telling a phone turned
            self.landscape = is_landscape(self.page.width, self.page.height)
        self.keypad.installable = self.installable
        self.keypad.needs_attention = self.shell.offers.needs_attention
        self.keypad.attention_tooltip = needs_attention_tooltip(self.shell.offers)
        full = state.mode.device and self.shell.offers.standalone and system.zoom <= 1
        self.full = full
        self.toolbar.visible = not full
        if state.mode.device:
            self._arrange_handheld(full=full, phone=self.phone)
        else:
            self._arrange_computer()

    def _arrange_handheld(self, *, full: bool, phone: bool) -> None:
        view = self.view.control
        state = self.state
        system = state.system
        self.frame.controls = [self.toolbar, self.layout]
        share = system.keypad_share or None  # 0 is auto; a phone always uses it
        margin = PHONE_MARGIN if phone else MARGIN
        width, height = self.handheld_room(phone=phone, full=full, margin=margin)
        self.frame.spacing = 0  # the toolbar holds only the status line
        units = keypad_units(state.keypad)
        sizing = Sizing(
            None if phone else share,
            system.zoom,
            FULL_RESERVE if full else STATUS_H,
            margin,
            not phone,
            side=state.mode is Mode.TABLET,
        )
        plan = handheld_plan(width, height, units[0], units[1], sizing)
        sizing = replace(sizing, bar=0) if full else sizing
        self.plan = plan
        state.scale, state.pad_scale = plan.scale, plan.pad_scale
        view.width = state.px(SCREEN_W)
        view.height = (
            full_screen_height(plan, height, units[1], sizing) if full else state.px(SCREEN_H)
        )
        view.expand = False
        # Tablet with the keypad moved left; not on a phone, which has no bar to move it back
        first = plan.side_by_side and system.keypad_first and not phone
        controls = plan.side_by_side and system.computer_column_controls  # the bar's arrows
        shape = (state.mode, plan.side_by_side, phone, system.zoom > 1, full, first, controls)
        if shape == self.shape:
            self.size_splitter(plan)
            return
        self.shape = shape
        parts: list[ft.Control] = [view, self.keypad.control]
        if not phone:
            parts.insert(1, self.splitter(plan))
        if first:  # Tablet with the keypad moved left of the screen
            parts.reverse()
        gap = GAP / 2
        self.layout.alignment = ft.Alignment.CENTER
        self.layout.content = (
            ft.Row(parts, spacing=gap, alignment=ft.MainAxisAlignment.CENTER)
            if plan.side_by_side
            else ft.Column(
                parts,
                spacing=gap,
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            )
        )
        if system.zoom > 1:
            self.layout.content = ft.Column(
                [ft.Row([self.layout.content], scroll=ft.ScrollMode.AUTO)],
                scroll=ft.ScrollMode.AUTO,
            )

    def _arrange_computer(self) -> None:
        state = self.state
        system = state.system
        view = self.view.control
        self.shape = None
        self.outer.padding = MARGIN
        self.frame.spacing = 0
        self.frame.controls = [self.layout]
        state.scale = state.pad_scale = system.zoom
        self.layout.alignment = None
        view.width = None
        view.expand = True
        height = computer_screen_height(self.page.height, toolbar_height=28)
        self.sidebar.height = max(180, height - 160)
        widths, _ = computer_columns(
            self.page.width,
            system.computer_sidebar_width,
            system.computer_keypad_width,
            keypad_visible=system.computer_keypad,
        )
        visible = [
            name
            for name in system.computer_column_order
            if name != "keypad" or system.computer_keypad
        ]
        children: list[ft.Control] = []
        self.computer_panels = {}
        for index, name in enumerate(visible):
            panel = self._computer_panel(name, widths[name], height)
            self.computer_panels[name] = panel
            children.append(
                ft.DragTarget(
                    panel,
                    group="computer-columns",
                    on_will_accept=lambda _, target=name: self._mark_drop(target),
                    on_leave=lambda _, target=name: self._mark_drop(target, over=False),
                    on_accept=lambda _, target=name: self._drop_column(target),
                )
            )
            if index + 1 < len(visible):
                children.append(self._computer_splitter(name, visible[index + 1], height))
        self.computer_row = ft.Row(
            children,
            width=max((self.page.width or 1000) - 2 * MARGIN, 1),
            height=height,
            spacing=0,
            scroll=ft.ScrollMode.AUTO,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )
        self.layout.content = self.computer_row

    def _computer_panel(self, name: str, width: float, height: float) -> ft.Container:
        headers = self.state.system.computer_column_headers
        controls: list[ft.Control] = [self._column_header(name)] if headers else []
        if name == "sidebar":
            content: ft.Control = ft.Column(
                [self.toolbar, self.sidebar.control], spacing=6, expand=True
            )
        elif name == "workspace":
            self.view.control.height = max(height - (COLUMN_HEADER_H if headers else 0) - 8, 300)
            content = self.view.control
        else:
            content = ft.Column(
                [ft.Row([self.keypad.control], scroll=ft.ScrollMode.AUTO)],
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            )
        controls.append(content)
        return ft.Container(
            ft.Column(controls, spacing=6, expand=True),
            width=width,
            height=height,
            padding=COMPUTER_COLUMN_PADDING,
        )

    def _column_header(self, name: str) -> ft.Control:
        """A column's header (Settings: Show column headers): drag it by its name to move the
        column, and a bar shows where it will go."""
        theme = self.theme
        title = COMPUTER_PANEL_NAMES[name]
        label = ft.Row(
            [
                ft.Icon(ft.Icons.DRAG_INDICATOR, size=16, color=theme.key_label),
                label_text(title, size=12, color=theme.panel_text, no_wrap=True),
            ],
            spacing=4,
            tight=True,
        )
        grip = ft.Draggable(
            ft.Container(
                label,
                height=COLUMN_HEADER_H,
                padding=ft.Padding.symmetric(horizontal=6),
                alignment=ft.Alignment.CENTER_LEFT,
                tooltip=f"Drag to move {title.lower()}",
            ),
            group="computer-columns",
            content_feedback=ft.Container(
                label_text(title, size=13, color=theme.accent_text, no_wrap=True),
                bgcolor=theme.accent,
                padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                border_radius=8,
                opacity=0.9,
            ),
            on_drag_start=lambda _: setattr(self, "dragged_column", name),
        )
        return ft.Row([ft.Container(grip, expand=True)], height=COLUMN_HEADER_H, spacing=0)

    def _move_arrow(self, name: str, step: int) -> ft.Control:
        """A < or > beside a resize bar: < moves the column right of the bar one place left, >
        the column left of it one place right. A tap area that takes no keyboard focus, so Tab
        and Enter stay the calculator's keys; with the keyboard column controls on (Settings)
        it is a button that Tab reaches."""
        tip = f"Move {COMPUTER_PANEL_NAMES[name].lower()} {'left' if step < 0 else 'right'}"
        return self._bar_arrow(step, tip, lambda: self._move_column(name, step))

    def _bar_arrow(self, step: int, tip: str, act: Callable[[], None]) -> ft.Control:
        """< (step -1) or > (step 1) beside a bar's line. Each icon fills its box and sits
        against the line, so the two are mirror images round it."""
        icon = ft.Icons.CHEVRON_LEFT if step < 0 else ft.Icons.CHEVRON_RIGHT
        colour = self.theme.key_label
        if self.state.system.computer_column_controls:
            return ft.IconButton(
                icon=ft.Semantics(label=tip, content=ft.Icon(icon)),
                tooltip=tip,
                on_click=lambda _: act(),
                icon_color=colour,
                icon_size=COLUMN_ARROW_W,
                width=COLUMN_ARROW_W,
                height=COLUMN_ARROW_H,
                padding=0,
            )
        return ft.Container(
            ft.Icon(icon, size=COLUMN_ARROW_W, color=colour),
            width=COLUMN_ARROW_W,
            height=COLUMN_ARROW_H,
            alignment=ft.Alignment.CENTER_RIGHT if step < 0 else ft.Alignment.CENTER_LEFT,
            tooltip=tip,
            on_click=lambda _: act(),
            ink=False,  # not focusable: Tab and Enter must not land on it
        )

    def _visible_columns(self) -> list[str]:
        system = self.state.system
        return [c for c in system.computer_column_order if c != "keypad" or system.computer_keypad]

    def _mark_drop(self, target: str, *, over: bool = True) -> None:
        """While a column is dragged over `target`, a bar on the side it will go to: before the
        target if it comes from the right, after it if from the left."""
        panel = self.computer_panels.get(target)
        source = self.dragged_column
        if panel is None:
            return
        panel.border = None
        if over and source is not None and source != target:
            order = self._visible_columns()
            side = ft.BorderSide(3, self.theme.accent)
            after = order.index(source) < order.index(target)
            panel.border = ft.Border(right=side) if after else ft.Border(left=side)
        with contextlib.suppress(RuntimeError):  # not on a page (the tests' stand-in page)
            panel.update()

    def _computer_splitter(self, first: str, second: str, height: float) -> ft.Control:
        def resize(delta: float) -> None:
            self._resize_boundary(first, second, delta)

        def step(delta: float) -> None:
            resize(delta)
            self.shell.write(SYSTEM_KEY, self.state.system.dumps())

        # The line's parts have fixed heights: a bar made only of parts that stretch broke the
        # layout so that typed keys stopped reaching a sheet (the flows browser test)
        room = max(height - (48 if self.state.system.computer_column_controls else 0), 1)
        half = max((room - COLUMN_ARROW_H) / 2, 1)

        def line(length: float) -> ft.Container:
            return ft.Container(width=2, height=length, bgcolor=self.theme.key_label)

        divider = ft.GestureDetector(
            ft.Container(
                ft.Column(
                    [
                        line(half),
                        ft.Row(  # < | > in the bar's middle: move a column across it
                            [
                                self._move_arrow(second, -1),
                                line(COLUMN_ARROW_H),
                                self._move_arrow(first, 1),
                            ],
                            spacing=0,
                            tight=True,
                        ),
                        line(half),
                    ],
                    spacing=0,
                    tight=True,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                expand=True,
                alignment=ft.Alignment.CENTER,
                bgcolor=ft.Colors.TRANSPARENT,
                tooltip="Drag to resize adjacent columns",
            ),
            expand=True,
            mouse_cursor=ft.MouseCursor.RESIZE_LEFT_RIGHT,
            drag_interval=24,
            on_horizontal_drag_update=lambda event: (
                resize(event.global_delta.x) if event.global_delta is not None else None
            ),
            on_horizontal_drag_end=lambda _: self.shell.write(
                SYSTEM_KEY, self.state.system.dumps()
            ),
        )
        controls: list[ft.Control] = []
        if self.state.system.computer_column_controls:
            controls.extend(
                [
                    ft.IconButton(
                        icon=ft.Semantics(
                            label="Narrow the column on the left",
                            content=ft.Icon(ft.Icons.ARROW_LEFT),
                        ),
                        tooltip="Narrow the column on the left",
                        on_click=lambda _: step(-16),
                        icon_color=self.theme.key_text,
                        icon_size=10,
                        width=16,
                        height=24,
                        padding=0,
                    ),
                    ft.IconButton(
                        icon=ft.Semantics(
                            label="Widen the column on the left",
                            content=ft.Icon(ft.Icons.ARROW_RIGHT),
                        ),
                        tooltip="Widen the column on the left",
                        on_click=lambda _: step(16),
                        icon_color=self.theme.key_text,
                        icon_size=10,
                        width=16,
                        height=24,
                        padding=0,
                    ),
                ]
            )
        controls.append(divider)
        return ft.Container(
            ft.Column(
                controls, spacing=0, expand=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER
            ),
            width=COMPUTER_SPLITTER,
            height=height,
            alignment=ft.Alignment.TOP_CENTER,
        )

    def _resize_boundary(self, first: str, second: str, delta: float) -> None:
        system = self.state.system
        if first == "sidebar" and second == "workspace":
            system.computer_sidebar_width += delta
        elif first == "workspace" and second == "sidebar":
            system.computer_sidebar_width -= delta
        elif first == "workspace" and second == "keypad":
            system.computer_keypad_width -= delta
        elif first == "keypad" and second == "workspace":
            system.computer_keypad_width += delta
        elif first == "sidebar" and second == "keypad":
            system.computer_sidebar_width += delta / 2
            system.computer_keypad_width -= delta / 2
        elif first == "keypad" and second == "sidebar":
            system.computer_sidebar_width -= delta / 2
            system.computer_keypad_width += delta / 2
        system.computer_sidebar_width = max(
            COMPUTER_MIN_SIDEBAR, min(COMPUTER_MAX_SIDEBAR, system.computer_sidebar_width)
        )
        system.computer_keypad_width = max(240.0, min(500.0, system.computer_keypad_width))
        self._size_computer_panels()

    def _size_computer_panels(self) -> None:
        if self.computer_row is None:
            return
        system = self.state.system
        widths, _ = computer_columns(
            self.page.width,
            system.computer_sidebar_width,
            system.computer_keypad_width,
            keypad_visible=system.computer_keypad,
        )
        for name, panel in self.computer_panels.items():
            panel.width = widths[name]
        self.page.update()

    def _move_column(self, name: str, step: int) -> None:
        """Move a column one place left (-1) or right (1): its header's ⋯ menu."""
        order = self._visible_columns()
        place = order.index(name) + step
        if 0 <= place < len(order):
            self._place_column(name, order[place])

    def _drop_column(self, target: str) -> None:
        """A column dragged by its header was dropped on `target`: it takes the target's place,
        and the columns between move up one."""
        source, self.dragged_column = self.dragged_column, None
        if source is not None and source != target:
            self._place_column(source, target)

    def _place_column(self, source: str, target: str) -> None:
        """`source` takes `target`'s place: after it if it came from the left, else before."""
        order = self.state.system.computer_column_order
        after = order.index(source) < order.index(target)
        order.remove(source)
        order.insert(order.index(target) + (1 if after else 0), source)
        self.on_system_change()

    def splitter(self, plan: HandheldPlan) -> ft.Control:
        """The bar between the screen and the keypad: drag it to give the screen or the keys more
        of the window, double-click it to go back to the default (kept with the settings)."""
        side = plan.side_by_side
        theme = self.theme
        grip = ft.Container(
            width=4 if side else 48,
            height=48 if side else 4,
            border_radius=2,
            bgcolor=theme.key_label,
        )

        def drag(e: ft.DragUpdateEvent) -> None:
            if e.global_delta is None or self.plan is None:
                return
            delta = e.global_delta.x if self.plan.side_by_side else e.global_delta.y
            # Dragging towards the screen grows the keypad: the keypad is on the right or at the
            # bottom, or (Tablet, moved) on the left
            if self.plan.side_by_side and self.state.system.keypad_first:
                delta = -delta
            room = self.plan.extent * max(self.state.system.zoom, 0.01)
            current = self.state.system.keypad_share or self.plan.share
            self.state.system.keypad_share = clamp_share(current - delta / room)
            self.resize_soon()

        def reset(_: object) -> None:
            self.state.system.keypad_share = 0.0
            self.on_system_change()

        def done(_: object) -> None:
            self.shell.write(SYSTEM_KEY, self.state.system.dumps())

        if side:  # Tablet: < | > round the grip swap the screen and the keypad
            first = self.state.system.keypad_first
            grip = ft.Row(
                [
                    self._bar_arrow(
                        -1, f"Move the {'screen' if first else 'keypad'} left", self.swap_keypad
                    ),
                    grip,
                    self._bar_arrow(
                        1, f"Move the {'keypad' if first else 'screen'} right", self.swap_keypad
                    ),
                ],
                spacing=0,
                tight=True,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
        bar = ft.Container(
            grip,
            alignment=ft.Alignment.CENTER,
            width=SIDE_SPLITTER if side else None,
            height=None if side else SPLITTER,
            tooltip="Drag to resize the keypad; double-click to reset",
        )
        detector = ft.GestureDetector(
            bar,
            mouse_cursor=ft.MouseCursor.RESIZE_LEFT_RIGHT
            if side
            else ft.MouseCursor.RESIZE_UP_DOWN,
            on_double_tap=reset,
            drag_interval=30,
            on_horizontal_drag_update=drag if side else None,
            on_horizontal_drag_end=done if side else None,
            on_vertical_drag_update=None if side else drag,
            on_vertical_drag_end=None if side else done,
        )
        if side:
            self.holder = None
            return detector
        self.holder = ft.Container(detector)  # a column would shrink the bar to its grip
        self.size_splitter(plan)
        return self.holder

    def swap_keypad(self) -> None:
        """Tablet: put the keypad on the other side of the screen (kept with the settings)."""
        self.state.system.keypad_first = not self.state.system.keypad_first
        self.on_system_change()

    def resize_soon(self) -> None:
        """Queue one redraw for the splitter. Drag steps arrive faster than the screen and keys
        can be rebuilt, and a redraw per step made the drag lag far behind the pointer; the steps
        that arrive while a redraw is queued or running only move the share."""
        if self.resizing:
            return
        self.resizing = True
        self.page.run_task(self.resize)

    async def resize(self) -> None:
        await asyncio.sleep(0)  # the drag steps already waiting are taken in first
        try:
            self.resize_now()
        finally:
            self.resizing = False

    def resize_now(self) -> None:
        """Redraw after a splitter step: only the part whose scale changed (often just the keys,
        since the screen is limited by the window's other side), and nothing else. The document
        has not changed, so there is no autosave, toolbar or sidebar work."""
        before = self.state.scale
        self.arrange()
        if self.state.scale != before:
            self.view.refresh()
        self.keypad.refresh()
        self.page.update()

    def size_splitter(self, plan: HandheldPlan) -> None:
        if self.holder is not None:
            across = keypad_size(*keypad_units(self.state.keypad))[0] * self.state.pad_scale
            self.holder.width = across


def mount(shell: Shell) -> App:
    """The Nspire's app in `shell`. In the browser the maths runs in the shell's engine worker (so
    Cancel can end it); on the desktop it stays in this process, unless `CASSIM_ENGINE=remote`
    asks for the same code path with a local engine."""
    engine = shell.engine()
    if engine is None and os.environ.get("CASSIM_ENGINE") == "remote":
        engine = LocalEngine()
    runner = None if engine is None else Runner(engine)
    state = AppState(sessions=local_session if runner is None else runner.new_session)
    return App(shell, state, runner)
