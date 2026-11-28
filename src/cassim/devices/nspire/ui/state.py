"""The app's state without Flet: a document, the display mode and the two keyboards."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

from cassim.app.keyboard import key_name
from cassim.core.settings import Settings
from cassim.device.editor import MARK
from cassim.device.engine import RemoteSession, local_session
from cassim.device.keys import Action, Binding, Keyboard, Keypad
from cassim.device.menu import MenuItem, MenuState
from cassim.device.profile import Profile
from cassim.device.sheet_link import link_for
from cassim.device.wizard import Field, Wizard
from cassim.devices.nspire import keymap as nspire
from cassim.devices.nspire import statistics_menus
from cassim.devices.nspire.document import Document as NspireDocument
from cassim.devices.nspire.document import PageKind
from cassim.devices.nspire.menus import entry_context, history_context, todo
from cassim.devices.nspire.pages import graph_actions, graph_analyze, graph_tools
from cassim.devices.nspire.pages.calculator import calculator_of
from cassim.devices.nspire.pages.graphs import Graphs, GridStyle, graphs_of
from cassim.devices.nspire.pages.spreadsheet import (
    NAME_ROW,
    SHEET_ACTIONS,
    Spreadsheet,
    spreadsheet_of,
)
from cassim.devices.nspire.pages.statistics import REGRESSIONS, Statistics, statistics_of
from cassim.devices.nspire.screen import Screen, render
from cassim.doc.document import Document
from cassim.graph.sampling import Window
from cassim.stats.plots import PlotType

if TYPE_CHECKING:
    from cassim.core.session import Session

_MENU_ONLY = frozenset({"menu_pick", "menu_back", "menu_page", "select"})
_GRAPH_GESTURE_FIELDS = 5
_GRAPH_EDITOR_ACTIONS = frozenset(
    {
        "accent", "backspace", "clear", "copy", "cut", "delete", "down", "end", "escape",
        "home", "home_key", "insert", "insert_linear", "left", "paste", "power", "right",
        "select_all", "select_cells", "select_left", "select_right", "select_to_end",
        "select_to_start", "select_word_left", "select_word_right", "shift_tab", "tab",
        "template", "up", "word_left", "word_right",
    }
)  # fmt: skip
# Keys the page sorter passes on: they act on the document or open a menu, never on a page.
_SORTER_PASSES = frozenset(
    {
        "add_page",
        "add_problem",
        "move_page",
        "move_problem",
        "undo_pages",
        "redo_pages",
        "delete_page",
        "new_document",
        "dialog",
    }
)
SORTER = "page_sorter"  # the sorter's name as a `dialog` action (ctrl+up, Doc > View)
COMPUTER_COLUMNS = ("sidebar", "workspace", "keypad")
COMPUTER_MIN_SIDEBAR = 300
COMPUTER_MAX_SIDEBAR = 420


class Mode(StrEnum):
    """The views (SDD-15 section 8.1): Handheld is the device in one column, the keypad under the
    screen; Tablet puts the keypad beside it; Computer has the sidebar and the workspace."""

    HANDHELD = "handheld"
    TABLET = "tablet"
    COMPUTER = "computer"

    @property
    def device(self) -> bool:
        """The device as it looks, screen and keypad: Handheld or Tablet."""
        return self is not Mode.COMPUTER


@dataclass
class System:
    """System Settings: how the app looks, apart from the document (FR-DOC-002)."""

    start_mode: Mode = Mode.COMPUTER
    math_size: int = 20  # LaTeX size in the entry and history
    computer_keypad: bool = False  # Computer mode shows the keypad beside the screen
    computer_column_order: list[str] = field(default_factory=lambda: list(COMPUTER_COLUMNS))
    computer_sidebar_width: float = COMPUTER_MIN_SIDEBAR
    computer_keypad_width: float = 320.0
    computer_column_controls: bool = False
    computer_column_headers: bool = False  # a header on each column, to drag it by
    keypad_share: float = 0.0  # Handheld: the keypad's share of the room (splitter); 0 is auto
    keypad_first: bool = False  # Tablet: the keypad left of the screen
    zoom: float = 1.0  # everything larger or smaller than the fitted size
    letters: str = ""  # keypad letter layout, a name in `Profile.keypads` ("" is the default)
    # The colour theme is shared by every app: `Shell.appearance` (SDD-15 section 7).

    def dumps(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def loads(cls, text: str) -> System:
        """Saved settings; anything unreadable or out of range falls back to the default."""
        system = cls()
        try:
            data = json.loads(text)
            system.start_mode = Mode(data["start_mode"])
            size = data["math_size"]
            system.math_size = size if size in MATH_SIZES.values() else system.math_size
            system.computer_keypad = data.get("computer_keypad") is True
            system.computer_column_controls = data.get("computer_column_controls") is True
            system.computer_column_headers = data.get("computer_column_headers") is True
            system.keypad_first = data.get("keypad_first") is True
            order = data.get("computer_column_order")
            if (
                isinstance(order, list)
                and len(order) == len(COMPUTER_COLUMNS)
                and all(isinstance(item, str) for item in order)
                and set(order) == set(COMPUTER_COLUMNS)
            ):
                system.computer_column_order = list(order)
            for name, low, high in (
                ("computer_sidebar_width", 160.0, COMPUTER_MAX_SIDEBAR),
                ("computer_keypad_width", 240.0, 500.0),
            ):
                value = data.get(name)
                ok = isinstance(value, int | float) and not isinstance(value, bool)
                if ok and low <= value <= high:
                    if name == "computer_sidebar_width":
                        value = max(value, COMPUTER_MIN_SIDEBAR)
                    setattr(system, name, float(value))
            for name, low, high in (("keypad_share", 0.0, 0.8), ("zoom", 0.5, 2.0)):
                value = data.get(name)
                ok = isinstance(value, int | float) and not isinstance(value, bool)
                if ok and low <= value <= high:
                    setattr(system, name, float(value))
            letters = data.get("letters", "")
            system.letters = letters if isinstance(letters, str) else ""
        except ValueError, KeyError, TypeError:
            return cls()
        return system


MATH_SIZES = {"Small": 16, "Normal": 20, "Large": 26}


# The sheet's Menu and context menus, which grey items by what is selected (sheet5).
SHEET_MENUS = frozenset({"menu_sheet", "sheet_cell", "sheet_block", "sheet_name", "sheet_column"})


def _graphs_actions_menu() -> MenuItem:
    """Menu > 1 Actions on a Graphs page, numbered as on the device (emulator run 7, R7-B8)."""

    def tool(label: str, name: str, key: str) -> MenuItem:
        return MenuItem(label, "graphs", f"tool:{name}", key=key)

    return MenuItem(
        "Actions",
        key="1",
        items=(
            MenuItem("Pointer", "graphs", "escape", key="1"),
            MenuItem(
                "Select",
                key="2",
                items=(
                    todo("Region", "1"),
                    MenuItem("Image", key="2", enabled=False),
                    MenuItem("Grid", key="3", enabled=False),
                ),
            ),
            todo("Hide/show", "3"),
            tool("Attributes", "attributes", "4"),
            todo("Set conditions", "5"),
            todo("Delete all", "6"),
            tool("Text", "text", "7"),
            tool("Coordinates and equations", "coordinates", "8"),
            tool("Calculate", "calculate", "9"),
            todo("Redefine", "A"),
        ),
    )


def _graph_entry_menu() -> MenuItem:
    """Menu > 3 Graph entry/edit, numbered as on the device (R7-B9). CASSim plots functions; the
    other entry types and the Equation templates keep their places, greyed."""

    def templates(label: str, key: str, *forms: str) -> MenuItem:
        return MenuItem(
            label,
            key=key,
            items=tuple(todo(form, str(n)) for n, form in enumerate(forms, start=1)),
        )

    return MenuItem(
        "Graph entry/edit",
        key="3",
        items=(
            MenuItem("Function", "goto", key="1"),
            todo("Relation", "2"),
            MenuItem(
                "Equation templates",
                key="3",
                items=(
                    templates(
                        "Line", "1", "Line slope intercept", "Vertical line", "Line standard"
                    ),
                    templates(
                        "Parabola",
                        "2",
                        "Vertex form y",
                        "Standard form y",
                        "Vertex form x",
                        "Standard form x",
                    ),
                    templates("Circle", "3", "Center form", "Standard form"),
                    templates("Ellipse", "4", "Center form"),
                    templates("Hyperbola", "5", "East-West", "South-North"),
                    templates("Conic", "6", "General"),
                ),
            ),
            todo("Parametric", "4"),
            todo("Polar", "5"),
            todo("Scatter plot", "6"),
            todo("Sequence", "7"),
            todo("Diff eq", "8"),
        ),
    )


class AppState:
    """Everything the views draw. A profile supplies the keymaps and keypad (FR-DEV-007)."""

    def __init__(
        self,
        document: Document | None = None,
        *,
        mode: Mode = Mode.COMPUTER,
        profile: Profile = nspire.PROFILE,
        sessions: Callable[[Settings], Session | RemoteSession] = local_session,
    ) -> None:
        self.sessions = sessions  # RemoteSessions when the maths runs in another worker
        self.document = document if document is not None else NspireDocument(sessions=sessions)
        self.mode = mode
        self.profile = profile
        self.keypad_keys = Keyboard(profile.handheld, profile.modifiers)
        self.computer_keys = Keyboard(profile.computer)
        # set by the GUI: reads the system clipboard and pastes it (keypad paste, which has no text)
        self.request_paste: Callable[[], None] | None = None
        self.clipboard_out: Callable[[str], None] | None = None  # set by the GUI: system clipboard
        self.show_dialog: Callable[[str], None] | None = None  # set by the GUI: named dialogs
        self.show_wizard: Callable[[Wizard], None] | None = None  # set by the GUI: field dialogs
        self.menu: MenuState | None = None
        self._catalog_at: list[int] = []  # the Catalog's tab and row, where it opens next time
        self._statistics_wizard: tuple[Statistics, str, Wizard] | None = None
        # The page sorter is open on the screen (ctrl+up). The page it highlights is the current
        # page, so moving the highlight goes to that page and Enter only closes the sorter.
        self.sorting = False
        # Set by the GUI: app menu reflects the browser's current capabilities and status.
        self.cassim_menu: Callable[[], MenuItem] | None = None
        # Caps lock, set by the Caps Lock key or the keypad's ctrl+shift. Flet's key events do not
        # say whether the lock is on, so it is tracked here from its own key presses.
        self.caps = False
        self.system = System(mode)
        # The document's name as the title bar shows it, with `*` for unsaved changes (set by the
        # GUI, which knows the saved copies)
        self.doc_title = ""
        # Set by the GUI: runs the given step at once, or after asking, when it would throw away
        # unsaved changes (a new document)
        self.ask_discard: Callable[[Callable[[], None]], None] | None = None
        self.on_new_document: Callable[[], None] | None = None  # set by the GUI
        self.pad_scale = 1.0  # the keypad's own scale: the screen's times the splitter's ratio
        self.scale = 1.0  # Handheld mode draws everything this many times larger (FR-DEV-004)

    @property
    def math_size(self) -> float:
        """The LaTeX size in the entry and history, at the current Handheld scale."""
        return self.system.math_size * self.scale

    def px(self, size: float) -> float:
        """A length in the handheld's pixels, drawn at the current scale."""
        return size * self.scale

    def kpx(self, size: float) -> float:
        """A length on the keypad, drawn at the keypad's scale."""
        return size * self.pad_scale

    @property
    def keypad(self) -> Keypad:
        """The keypad in the chosen letter layout; an unknown choice gives the profile's own."""
        return self.profile.keypads.get(self.system.letters, self.profile.keypad)

    @property
    def pending(self) -> str:
        """The keypad modifier waiting for the next key ("ctrl", "shift" or "")."""
        return self.keypad_keys.pending

    def clear_pending(self) -> None:
        """Drop a keypad modifier that has done its job (a shift used for a tap in the entry)."""
        self.keypad_keys.pending = ""

    def replace_document(self, document: Document) -> None:
        """Open another document (a new one, a file or the autosave) and close any menu."""
        self.document = document
        self.menu = None
        self.sorting = False
        self.keypad_keys.pending = ""

    @property
    def sheet(self) -> Spreadsheet | None:
        """The current page's spreadsheet, if it is a Lists & Spreadsheet page."""
        return spreadsheet_of(self.document.current)

    @property
    def statistics(self) -> Statistics | None:
        """The current page's Data & Statistics model, if built."""
        current = statistics_of(self.document.current)
        if current is not None:
            return current
        sheet = self.sheet
        return sheet.split_statistics[-1] if sheet is not None and sheet.split_statistics else None

    @property
    def graphs(self) -> Graphs | None:
        """The current page's function graph model, if built."""
        return graphs_of(self.document.current)

    def prepare(self) -> None:
        """Before drawing: the current sheet takes the engine's replies and asks for the cells
        it shows; a dialog it wants opened is opened."""
        graphs_page = self.graphs
        if graphs_page is not None and graphs_page.tools.request is not None:
            self._graphs_request(graphs_page)
        sheet = self.sheet
        if sheet is not None:
            sheet.update()
            self._place_shade_pages(sheet)
            self._open_sheet_wizard(sheet)
        statistics = self.statistics
        if statistics is not None:
            statistics.update()
        graphs = self.graphs
        if graphs is not None:
            graphs.update()

    def _place_shade_pages(self, sheet: Spreadsheet) -> None:
        """A shaded test with no room left on its page goes on a new Data & Statistics page
        after it, showing the shade alone; the sheet stays on screen (emulator run 7, R7-C4)."""
        document = self.document
        while sheet.shade_pages:
            plot = sheet.shade_pages.pop(0)
            if not document.can_add_page():
                continue
            here = (document.problem, document.page)
            model = statistics_of(document.add_page(PageKind.STATISTICS))
            if model is not None:
                model.shade = plot
            document.go(*here)

    def retain_sheets(self) -> None:
        """After pages are added, deleted, moved or brought back: each Problem's engine keeps
        exactly the sheets of its pages (a deleted sheet frees the lists it linked)."""
        for problem in self.document.problems:
            sheets = [page.model for page in problem.pages if isinstance(page.model, Spreadsheet)]
            link_for(problem.session).retain(sheets)

    def _open_sheet_wizard(self, sheet: Spreadsheet) -> None:
        if sheet.wizard is not None and self.show_wizard is not None:
            wizard, sheet.wizard = sheet.wizard, None
            self.show_wizard(wizard)

    def new_document(self) -> None:
        """A blank document with the current Document Settings, once any unsaved changes have
        been let go (the GUI asks)."""
        if self.ask_discard is not None:
            self.ask_discard(self._new_document)
        else:
            self._new_document()

    def _new_document(self) -> None:
        self.replace_document(
            NspireDocument(settings=self.document.settings, sessions=self.sessions)
        )
        if self.on_new_document is not None:
            self.on_new_document()

    def screen(self) -> Screen:
        view = self.menu.view() if self.menu is not None and self.menu.open else None
        status = self.profile.status(self.document.settings)
        status = f"{status} CAPS" if self.caps else status
        return render(self.document, status, view, self.profile.pages, sorter=self.sorting)

    def page_name(self, kind: str) -> str:
        """The device's name for a page type ("Lists & Spreadsheet")."""
        return self.profile.pages.get(str(kind), str(kind))

    def press_keypad(self, name: str) -> None:
        self._perform(self.keypad_keys, name)

    def key_event(
        self,
        key: str,
        *,
        shift: bool = False,
        ctrl: bool = False,
        alt: bool = False,
        meta: bool = False,
    ) -> bool:
        """Handle a physical key. False means it is not ours: let the browser have it."""
        binding = self.binding_for(key, shift=shift, ctrl=ctrl, alt=alt, meta=meta)
        if binding is None:
            return False
        self.run(binding)
        return True

    def binding_for(
        self,
        key: str,
        *,
        shift: bool = False,
        ctrl: bool = False,
        alt: bool = False,
        meta: bool = False,
    ) -> Binding | None:
        """What a physical key does, without doing it (the GUI fetches the system clipboard
        before a paste)."""
        name = key_name(key, shift=shift, ctrl=ctrl, alt=alt, meta=meta)
        sheet = self.sheet
        if (
            name in ("F2", "F4")
            and sheet is not None
            and sheet.editing is not None
            and sheet.editing.startswith("=")
            and not sheet.dialogs
            and sheet.mode is None
            and (self.menu is None or not self.menu.open)
        ):
            return Binding("sheet_ref_mode" if name == "F2" else "sheet_ref_fixed")
        return None if name is None else self._cased(self.computer_keys.press(name))

    def _cased(self, binding: Binding | None) -> Binding | None:
        """With caps lock on, a typed letter swaps case (so Shift still gives a small letter)."""
        letter = binding is not None and binding.action == "insert" and binding.arg.isalpha()
        if self.caps and binding is not None and letter and len(binding.arg) == 1:
            return Binding("insert", binding.arg.swapcase())
        return binding

    def run_action(self, action: Action, arg: str = "") -> None:
        """Do an action by name, for GUI buttons and menus."""
        self.run(Binding(action, arg))

    def paste_text(self, text: str) -> None:
        """Paste text from the system clipboard (the calculator's own nodes if it matches)."""
        self.run(Binding("paste", text))

    def run(self, binding: Binding) -> None:
        """Do a binding: document actions here, everything else on the current page."""
        if self._shell_action(binding) or self._document_action(binding):
            return
        sheet = self.sheet
        if sheet is not None:
            self._sheet_key(sheet, binding)
            return
        statistics = self.statistics
        graphs = self.graphs
        if graphs is not None:
            self._graphs_key(graphs, binding)
            return
        if statistics is not None:
            self._statistics_key(statistics, binding)
            return
        calculator = calculator_of(self.document.current)
        if calculator is not None and binding.action == "context_menu":
            if binding.arg == "warning":
                calculator.show_warning_info()
            elif calculator.error is None and calculator.pending is None:
                self._open_menu("calculator_context")
            return
        if (
            calculator is not None
            and binding.action not in SHEET_ACTIONS
            and not (binding.action in ("undo", "redo") and self._page_undo(binding.action))
        ):
            calculator.perform(binding)
            if binding.action in ("copy", "cut") and self.clipboard_out is not None:
                self.clipboard_out(self.document.clipboard.text)

    def _statistics_key(self, statistics: Statistics, binding: Binding) -> None:
        if binding.action == "statistics":
            self._statistics_action(statistics, binding.arg)
        elif binding.action == "context_menu":
            self._open_menu(binding.arg or "menu_statistics")
        elif binding.action in ("tab", "shift_tab"):
            # Tab opens the x axis's variable list, shift+Tab the y axis's (emulator run 7,
            # R7-C9: Tab, then Tab again for y), as a click on its box does
            self._open_menu("statistics_x" if binding.action == "tab" else "statistics_y")
        elif binding.action in ("undo", "redo"):
            self._page_undo(binding.action)
            self.retain_sheets()

    def _graphs_key(self, graphs: Graphs, binding: Binding) -> None:
        if binding.action == "graphs":
            self._graphs_tool_action(graphs, binding.arg)
        elif graph_tools.key(graphs, binding) or graph_analyze.key(graphs, binding):
            return  # a zoom tool or a trace has the key
        elif binding.action == "graphs_submit":
            self._graphs_submit(graphs, binding.arg)
        elif binding.action in ("place", "extend"):
            self._graphs_place(graphs, binding)
        elif binding.action in ("enter", "approximate"):
            if graphs.functions:
                graphs.submit_editor(graphs.active_index)
        elif binding.action in ("graphs_select", "up", "down", "goto", "tab"):
            self._graphs_navigation(graphs, binding)
        elif binding.action in {
            "graphs_toggle",
            "graphs_zoom",
            "graphs_gesture",
            "graphs_standard",
            "graphs_view",
        }:
            self._graphs_display_action(graphs, binding)
        elif binding.action == "context_menu":
            self._open_menu("menu_graphs")
        elif binding.action in ("undo", "redo"):
            self._graphs_undo(graphs, binding)
        elif binding.action in _GRAPH_EDITOR_ACTIONS:
            graphs.edit(binding)
            if binding.action in ("copy", "cut") and self.clipboard_out is not None:
                self.clipboard_out(self.document.clipboard.text)

    def _graphs_request(self, graphs: Graphs) -> None:
        """An Actions tool's dialog: Attributes for the graph it took, or the text for Text."""
        request, graphs.tools.request = graphs.tools.request, None
        if request is None or self.show_wizard is None:
            return
        kind, argument = request
        if kind == "attributes":
            entry = next((f for f in graphs.functions if f.name == argument), None)
            if entry is None:
                return
            found = graphs.attributes.get(argument, graph_actions.Attributes())
            form = graph_actions.attributes_wizard(entry, found)
            self.show_wizard(
                Wizard(
                    form.title,
                    form.fields,
                    steps=lambda values: [
                        Binding("graphs", f"attributes:{argument}:{json.dumps(dict(values))}")
                    ],
                    check=graph_actions.attributes_problems,
                )
            )
        else:
            self.show_wizard(
                Wizard(
                    "Text",
                    (Field("text", "Text"),),
                    steps=lambda values: [
                        Binding("graphs", f"text:{argument}:{values.get('text', '')}")
                    ],
                )
            )

    def _graphs_tool_action(self, graphs: Graphs, argument: str) -> None:
        """Window / Zoom and Trace: a dialog opens here, everything else is the page's."""
        dialogs = {
            "dialog:window": graph_tools.window_wizard,
            "dialog:trace_step": graph_tools.trace_step_wizard,
        }
        if argument in dialogs:
            if self.show_wizard is not None:
                self.show_wizard(dialogs[argument](graphs))
            return
        if not graph_analyze.perform(graphs, argument):
            graph_tools.perform(graphs, argument)

    def _graphs_display_action(self, graphs: Graphs, binding: Binding) -> None:
        if binding.action == "graphs_toggle":
            graphs.toggle(binding.arg)
        elif binding.action == "graphs_zoom":
            graphs.zoom(float(binding.arg))
        elif binding.action == "graphs_gesture":
            self._graphs_gesture(graphs, binding.arg)
        elif binding.action == "graphs_standard":
            graphs.set_window(Window())
        else:
            graphs.set_view(binding.arg)

    def _graphs_navigation(self, graphs: Graphs, binding: Binding) -> None:
        if not graphs.functions:
            return
        if binding.action == "graphs_select":
            graphs.select_function(int(binding.arg))
        elif binding.action == "goto" or (
            # Tab opens the entry line on the first empty fN, as ctrl+G does (Simon's note 2);
            # inside a template it moves between the slots (R6-A9)
            binding.action == "tab"
            and not graphs.functions[graphs.active_index].editing.editor.path
        ):
            graphs.select_empty_function()
        elif graphs.functions[graphs.active_index].editing.editor.path:
            graphs.edit(binding)
        else:
            graphs.move_function(-1 if binding.action == "up" else 1)

    def _graphs_gesture(self, graphs: Graphs, argument: str) -> None:
        values = argument.split(",")
        if len(values) != _GRAPH_GESTURE_FIELDS:
            msg = "a graph gesture needs five values"
            raise ValueError(msg)
        dx, dy, factor, x, y = (float(value) for value in values)
        graphs.gesture(dx, dy, factor, x, y)

    def _graphs_undo(self, graphs: Graphs, binding: Binding) -> None:
        if graphs.functions:
            editing = graphs.functions[graphs.active_index].editing
            can_step = editing.can_undo if binding.action == "undo" else editing.can_redo
            if can_step:
                graphs.edit(binding)
                return
        self._page_undo(binding.action)

    def _graphs_submit(self, graphs: Graphs, argument: str) -> None:
        index_text, separator, expression = argument.partition(":")
        try:
            index = int(index_text)
        except ValueError as error:
            raise ValueError(f"invalid graph entry index {index_text!r}") from error
        if separator:
            graphs.submit(index, expression)
        else:
            graphs.submit_editor(index)

    def _graphs_place(self, graphs: Graphs, binding: Binding) -> None:
        index_text, separator, target = binding.arg.partition(":")
        if not separator:
            msg = "a graph editor target needs an entry index"
            raise ValueError(msg)
        index = int(index_text)
        if not 0 <= index < len(graphs.functions):
            raise IndexError(f"no graph function at index {index}")
        graphs.active_index = index
        graphs.edit(Binding(binding.action, target))

    def _sheet_key(self, sheet: Spreadsheet, binding: Binding) -> None:
        if binding.action == "context_menu":
            self._open_menu(sheet.context_menu())
            return
        if binding.action == "statistics_point":
            return
        if binding.action == "statistics" and sheet.split_statistics:
            self._statistics_action(sheet.split_statistics[-1], binding.arg)
            return
        undo = binding.action in ("undo", "redo") and not sheet.dialogs and sheet.mode is None
        if undo and sheet.editing is None:
            can = sheet.can_undo if binding.action == "undo" else sheet.can_redo
            if not can:  # nothing left on the page: the document's own undo (as the Calculator)
                (self.document.undo if binding.action == "undo" else self.document.redo)()
                self.retain_sheets()
                return
        sheet.perform(binding)
        if binding.action in ("copy", "cut") and self.clipboard_out is not None:
            self.clipboard_out(self.document.clipboard.text)
        self._open_sheet_wizard(sheet)

    def _page_undo(self, action: str) -> bool:
        """Undo or redo with nothing left to step in the entry line falls through to the document
        (emulator run S7 f: ctrl+Z on a fresh page undoes the page insert, ctrl+Y brings it back).
        True if the document took the key."""
        calculator = calculator_of(self.document.current)
        if calculator is not None and (
            calculator.error is not None or calculator.pending is not None
        ):
            return False  # the key belongs to the dialog or the run
        if action == "redo":
            if calculator is not None and calculator.can_redo:
                return False
            return self.document.redo()
        if calculator is not None and calculator.can_undo:
            return False
        return self.document.undo()

    def _shell_action(self, binding: Binding) -> bool:
        """Caps lock, menus and dialogs, which belong to the shell and not to a page."""
        if binding.action == "caps":
            self.caps = not self.caps
        elif self.menu is not None and self.menu.open:
            self._active_menu_key(binding)
        elif self.sorting:
            self._sorter_key(binding)
        elif binding == Binding("dialog", SORTER):
            self.sorting = True
        elif binding.action == "open_menu":
            self._open_menu(binding.arg)
        elif binding.action == "wizard":
            self._open_wizard(binding.arg)
        else:
            return binding.action in _MENU_ONLY  # a menu click with no menu open does nothing
        return True

    def _active_menu_key(self, binding: Binding) -> None:
        assert self.menu is not None
        if binding.action == "dialog" and binding.arg in {
            "help",
            "view:computer",
            "view:tablet",
            "view:handheld",
        }:
            self.menu = None
            self.run(binding)
            return
        name = ""
        if binding.action == "open_menu":
            name = binding.arg
        elif binding.action == "context_menu" and self.sheet is not None:
            name = self.sheet.context_menu()
        elif binding.action in {"add_page", "add_problem"} and not binding.arg:
            name = binding.action
        if name:
            if self.sorting and name not in {"doc", "cassim", "add_page", "add_problem"}:
                return
            target = self._menu_root(name)
            self._remember_catalog()
            if target is not None:
                same = target is self.menu.root or (
                    (
                        name
                        in {
                            "variables",
                            "cassim",
                            "graphs_history",
                            "menu_sheet",
                            "menu_graphs",
                        }
                        or (name == "menu" and self.graphs is not None)
                        or name.startswith("sheet_")
                    )
                    and target.label == self.menu.root.label
                )
                self.menu = None if same else self._menu_state(name, target)
            return
        self._menu_key(binding)

    def _sorter_key(self, binding: Binding) -> None:
        """While the page sorter is open it takes every key. The arrows move the highlight (left
        and right through the pages in order, up and down between Problems), Enter, the centre
        key, Esc and ctrl+up close it, and Delete or del removes the highlighted page. A tap on a
        tile highlights it, and a tap on the highlighted tile opens it."""
        document = self.document
        action = binding.action
        if action in ("enter", "select", "escape") or binding == Binding("dialog", SORTER):
            self.sorting = False
        elif action == "sorter_go":
            self._sorter_tap(binding.arg)
        elif action == "open_menu":
            if binding.arg in ("doc", "cassim"):  # a page's Menu has nothing to do in the sorter
                self._open_menu(binding.arg)
        elif action in _SORTER_PASSES:
            self._document_action(binding)
        else:
            keys: dict[Action, Callable[[], object]] = {
                "left": lambda: document.next_page(-1),
                "right": document.next_page,
                "up": lambda: self._sorter_problem(-1),
                "down": lambda: self._sorter_problem(1),
                "delete": document.delete_page,
                "backspace": document.delete_page,
                "undo": document.undo,
                "redo": document.redo,
            }
            key = keys.get(action)
            if key is not None:  # anything else (typing, the page's own keys) does nothing
                key()

    def _sorter_problem(self, step: int) -> None:
        """Up or down in the sorter: the same page number in the Problem above or below, or its
        last page when it has fewer."""
        document = self.document
        problem = document.problem + step
        if 0 <= problem < len(document.problems):
            document.go(problem, min(document.page, len(document.problems[problem].pages) - 1))

    def _sorter_tap(self, where: str) -> None:
        """A tap on tile `problem.page` (from 0) highlights it; a tap on the highlighted one opens
        it."""
        document = self.document
        problem, page = (int(part) for part in where.split("."))
        if (problem, page) == (document.problem, document.page):
            self.sorting = False
        else:
            document.go(problem, page)

    def _menu_root(self, name: str) -> MenuItem | None:
        if name == "menu":
            if self.sheet is not None:
                name = "menu_sheet"
            elif self.statistics is not None:
                name = "menu_statistics"
            elif self.graphs is not None:
                name = "menu_graphs"
            elif calculator_of(self.document.current) is None:
                return None  # a page CASSim has not built yet has no Menu
        if name == "cassim" and self.cassim_menu is not None:
            return self.cassim_menu()
        if name == "menu_statistics" or name.startswith("statistics_"):
            return self._statistics_menu(name)
        built = {
            "graphs_history": self._graphs_history_menu,
            "menu_graphs": self._graphs_menu,
            "calculator_context": self._calculator_context,
        }.get(name)
        if built is not None:
            return built()
        root = self._variables_menu() if name == "variables" else self.profile.menus.get(name)
        if self.sheet is not None and root is not None and name in SHEET_MENUS:
            root = self.sheet.adjust_menu(root)
        return root

    def _calculator_context(self) -> MenuItem | None:
        """The Calculator's context menu: a history line's while one is picked, else the entry
        line's, with the device's grey states (run 5, H3 j)."""
        calculator = calculator_of(self.document.current)
        if calculator is None:
            return None
        if calculator.recall is not None:
            return history_context(warning=calculator.warning_info() is not None)
        variables = self._variables_menu()
        listed = variables.items if variables is not None else ()
        return entry_context(selection=bool(calculator.editor.selection()), variables=listed)

    def _graphs_history_menu(self) -> MenuItem | None:
        graphs = self.graphs
        if graphs is None:
            return None
        items = tuple(
            MenuItem(
                f"{entry.name}(x) = {entry.expression or entry.editing.editor.linear() or '…'}",
                "graphs_select",
                str(index),
                hint="hidden" if not entry.visible else "",
            )
            for index, entry in enumerate(graphs.functions)
        )
        return MenuItem("Graph functions", items=items)

    def _graphs_menu(self) -> MenuItem | None:
        graphs = self.graphs
        if graphs is None:
            return None
        grid = MenuItem(
            "Grid",
            key="6",
            items=tuple(
                MenuItem(
                    label, "graphs_view", style.value, key=key, enabled=style != graphs.grid_style
                )
                for key, label, style in (
                    ("1", "No Grid", GridStyle.NONE),
                    ("2", "Dot Grid", GridStyle.DOT),
                    ("3", "Lined Grid", GridStyle.LINED),
                )
            ),
        )
        return MenuItem(
            "Menu",
            items=(
                _graphs_actions_menu(),
                MenuItem(
                    "View",
                    key="2",
                    items=(
                        MenuItem("Graphing", key="1", enabled=False),
                        MenuItem("Plane geometry", key="2", enabled=False),
                        MenuItem("3D graphing", key="3", enabled=False),
                        MenuItem("Hide analytic window", key="4", enabled=False),
                        MenuItem(
                            "Hide axes" if graphs.show_axes else "Show axes",
                            "graphs_view",
                            "axes",
                            key="5",
                        ),
                        grid,
                        MenuItem("Show entry line", key="7", enabled=False),
                        MenuItem(
                            "Hide axes end values"
                            if graphs.show_end_values
                            else "Show axes end values",
                            "graphs_view",
                            "end-values",
                            key="8",
                            enabled=graphs.show_axes,
                        ),
                        MenuItem("Hide object selection guides", key="9", enabled=False),
                    ),
                ),
                _graph_entry_menu(),
                graph_tools.window_zoom_menu(),
                graph_tools.trace_menu(),
                graph_analyze.menu(),
                MenuItem("Table", key="7", enabled=False),
                MenuItem("Geometry", key="8", enabled=False),
                MenuItem("Settings…", key="9", enabled=False),
            ),
        )

    def _statistics_menu(self, name: str) -> MenuItem | None:
        statistics = self.statistics
        if statistics is None:
            return None
        has_x, has_y = bool(statistics.x_name), bool(statistics.y_name)
        categorical = statistics.categorical_x
        numeric_pair = has_x and has_y and not categorical
        categorical_chart = statistics.plot_type in (
            PlotType.DOT_CHART,
            PlotType.BAR,
            PlotType.PIE,
        )
        histogram = statistics.plot_type is PlotType.HISTOGRAM
        if name == "statistics_plot":
            return MenuItem(
                "Plot type",
                items=tuple(
                    MenuItem(
                        plot.value,
                        "statistics",
                        f"plot:{plot.value}",
                        enabled=plot is not statistics.plot_type,
                    )
                    for plot in statistics.available_plot_types()
                ),
            )
        if name in {
            "statistics_x",
            "statistics_y",
            "statistics_summary",
            "statistics_split",
        }:
            purpose = name.removeprefix("statistics_")
            choices = statistics.lists
            if purpose in ("summary", "y"):
                choices = statistics.numeric_lists
            elif purpose == "split":
                choices = statistics.category_lists
            selected = {
                "x": statistics.x_name,
                "y": statistics.y_name,
                "summary": statistics.summary_name,
                "split": statistics.split_name,
            }[purpose]
            action = {
                "x": "x",
                "y": "y",
                "summary": "summary",
                "split": "split",
            }[purpose]
            return MenuItem(
                f"Choose {purpose.title()} List",
                jump=True,
                # the chosen list, or the first list when none is (the device's list starts
                # there: emulator stats 1 and run 7, R7-C9)
                start=(choices.index(selected) + 1 if selected in choices else int(bool(choices)),),
                items=(
                    MenuItem("(none)", "statistics", f"{action}:"),
                    *(
                        MenuItem(variable, "statistics", f"{action}:{variable}")
                        for variable in choices
                    ),
                ),
            )
        if name.startswith("statistics_context_"):
            return self._statistics_context_menu(name.removeprefix("statistics_context_"))
        if name != "menu_statistics":
            return None
        plot_types = tuple(
            MenuItem(
                plot.value,
                "statistics",
                f"plot:{plot.value}",
                enabled=plot is not statistics.plot_type,
            )
            for plot in statistics.available_plot_types()
        )
        return MenuItem(
            "Menu",
            items=(
                MenuItem("Plot type", key="1", jump=True, items=plot_types, enabled=has_x),
                MenuItem(
                    "Plot properties",
                    key="2",
                    items=(
                        MenuItem(
                            "Connect data points",
                            "statistics",
                            "toggle-connect",
                            key="1",
                            enabled=has_y
                            and statistics.plot_type in (PlotType.SCATTER, PlotType.XY_LINE),
                        ),
                        MenuItem(
                            "Add X variable",
                            "open_menu",
                            "statistics_x",
                            key="5",
                            enabled=bool(statistics.lists),
                        ),
                        MenuItem(
                            "Add X summary list",
                            "open_menu",
                            "statistics_summary",
                            key="6",
                            enabled=categorical and bool(statistics.numeric_lists),
                        ),
                        MenuItem("Remove X variable", "statistics", "x:", key="7", enabled=has_x),
                        MenuItem(
                            "Add Y variable",
                            "open_menu",
                            "statistics_y",
                            key="8",
                            enabled=bool(statistics.numeric_lists),
                        ),
                        MenuItem("Remove Y variable", "statistics", "y:", key="9", enabled=has_y),
                        MenuItem(
                            "Force categorical X"
                            if not statistics.categorical_x
                            else "Force numeric X",
                            "statistics",
                            "toggle-force-x",
                            key="B",
                            enabled=has_x,
                        ),
                        MenuItem(
                            "Split categories by variable",
                            "open_menu",
                            "statistics_split",
                            key="D",
                            enabled=categorical and bool(statistics.category_lists),
                        ),
                        MenuItem(
                            "Remove split variable",
                            "statistics",
                            "split:",
                            key="E",
                            enabled=bool(statistics.split_name),
                        ),
                        MenuItem(
                            "Show all labels"
                            if not statistics.show_all_labels
                            else "Hide all labels",
                            "statistics",
                            "toggle-labels",
                            key="4",
                            enabled=categorical_chart,
                        ),
                        MenuItem(
                            "Extend box plot whiskers"
                            if not statistics.extend_whiskers
                            else "Show box plot outliers",
                            "statistics",
                            "toggle-whiskers",
                            key="3",
                            enabled=statistics.plot_type is PlotType.BOX,
                        ),
                        MenuItem(
                            "Histogram bin width…",
                            "statistics",
                            "wizard:bin-width",
                            key="2",
                            enabled=histogram,
                        ),
                        MenuItem(
                            "Histogram scale",
                            key="A",
                            items=tuple(
                                MenuItem(scale, "statistics", f"histogram-scale:{scale}")
                                for scale in ("Frequency", "Percent", "Density")
                            ),
                            enabled=histogram,
                        ),
                        MenuItem(
                            "Clear all",
                            "statistics",
                            "clear",
                            key="F",
                            enabled=has_x or has_y or bool(statistics.split_name),
                        ),
                    ),
                ),
                MenuItem(
                    "Actions",
                    key="3",
                    items=(
                        MenuItem(
                            "Category order",
                            key="1",
                            items=tuple(
                                MenuItem(order, "statistics", f"sort-order:{order}")
                                for order in ("List Order", "Value Order", "Alpha Order")
                            ),
                            enabled=categorical or bool(statistics.summary_name),
                        ),
                    ),
                ),
                MenuItem(
                    "Analyze",
                    key="4",
                    enabled=has_x and not categorical_chart,
                    items=(
                        MenuItem(
                            "Plot function…",
                            "statistics",
                            "wizard:function",
                            key="4",
                            enabled=numeric_pair,
                        ),
                        MenuItem(
                            "Remove plotted function",
                            "statistics",
                            "function:",
                            key="1",
                            enabled=bool(statistics.function_text),
                        ),
                        MenuItem(
                            "Regression",
                            key="6",
                            jump=True,
                            enabled=numeric_pair,
                            items=(
                                MenuItem("None", "statistics", "regression:none"),
                                *(
                                    MenuItem(label, "statistics", f"regression:{command}")
                                    for command, label in REGRESSIONS
                                ),
                            ),
                        ),
                        MenuItem(
                            "Residuals",
                            key="7",
                            enabled=bool(statistics.regression),
                            items=(
                                MenuItem(
                                    "Show residual squares"
                                    if not statistics.residual_squares
                                    else "Hide residual squares",
                                    "statistics",
                                    "toggle-residual-squares",
                                    key="1",
                                    enabled=bool(statistics.regression),
                                ),
                                MenuItem(
                                    "Show residual plot"
                                    if not statistics.residual_plot
                                    else "Hide residual plot",
                                    "statistics",
                                    "toggle-residual-plot",
                                    key="2",
                                    enabled=bool(statistics.regression),
                                ),
                            ),
                        ),
                        MenuItem(
                            "Plot value…",
                            "statistics",
                            "wizard:value",
                            key="8",
                            enabled=has_x and not categorical_chart,
                        ),
                        MenuItem(
                            "Show normal PDF" if not statistics.normal_pdf else "Hide normal PDF",
                            "statistics",
                            "toggle-normal-pdf",
                            key="9",
                            enabled=statistics.plot_type is PlotType.HISTOGRAM,
                        ),
                    ),
                ),
                MenuItem(
                    "Window/zoom",
                    key="5",
                    enabled=has_x and statistics.plot_type is not PlotType.PIE,
                    items=(
                        MenuItem(
                            "Window settings…",
                            "statistics",
                            "wizard:window",
                            key="1",
                            enabled=not categorical_chart,
                        ),
                        MenuItem(
                            "Zoom - data",
                            "statistics",
                            "zoom-data",
                            key="2",
                            enabled=has_x,
                        ),
                    ),
                ),
            ),
        )

    def _statistics_context_menu(self, target: str) -> MenuItem | None:
        statistics = self.statistics
        if statistics is None:
            return None
        if target in statistics_menus.TARGETS:  # a box, a bar or a regression (stats4, R5-G2)
            return statistics_menus.context_menu(statistics, target)
        zoom = MenuItem(
            "Zoom",
            items=(MenuItem("Zoom - data", "statistics", "zoom-data"),),
        )
        if target == "x":
            return MenuItem(
                "X axis",
                items=(
                    MenuItem(
                        "Force categorical X"
                        if not statistics.categorical_x
                        else "Force numeric X",
                        "statistics",
                        "toggle-force-x",
                        enabled=bool(statistics.x_name),
                    ),
                    MenuItem(
                        "Remove X variable",
                        "statistics",
                        "x:",
                        enabled=bool(statistics.x_name),
                    ),
                    zoom,
                ),
            )
        if target == "y":
            return MenuItem(
                "Y axis",
                items=(
                    MenuItem(
                        "Remove Y variable",
                        "statistics",
                        "y:",
                        enabled=bool(statistics.y_name),
                    ),
                    zoom,
                ),
            )
        items = (
            MenuItem(
                "Connect data points",
                "statistics",
                "toggle-connect",
                enabled=bool(statistics.y_name)
                and statistics.plot_type in (PlotType.SCATTER, PlotType.XY_LINE),
            ),
            zoom,
        )
        return MenuItem("Point" if target == "point" else "Plot", items=items)

    def _statistics_action(self, statistics: Statistics, action: str) -> None:
        name, _, argument = action.partition(":")
        if name == "wizard":
            wizard = statistics.wizard(argument)
            self._statistics_wizard = (statistics, argument, wizard)
            if self.show_wizard is not None:
                self.show_wizard(wizard)
        elif name == "function":
            statistics.perform(f"set-function:{argument}")
        else:
            statistics.perform(action)

    def _open_menu(self, name: str) -> None:
        root = self._menu_root(name)
        if root is not None:
            self.menu = self._menu_state(name, root)

    def _menu_state(self, name: str, root: MenuItem) -> MenuState:
        """A menu opening; the Catalog where it was left."""
        menu = MenuState(root)
        if name == "catalog" and self._catalog_at:
            menu.reopen(self._catalog_at)
        return menu

    def _remember_catalog(self) -> None:
        """Keep the open Catalog's tab and row for the next time it opens (run 5, E5)."""
        if self.menu is not None and self.menu.root is self.profile.menus.get("catalog"):
            self._catalog_at = self.menu.positions()

    def _variables_menu(self) -> MenuItem | None:
        """The var key: the current Problem's variables, each typed by choosing it. On a sheet's
        name cell it links the column instead (check 6, E7)."""
        sheet = self.sheet
        calculator = calculator_of(self.document.current)
        graphs = self.graphs
        session = (
            sheet.session
            if sheet is not None
            else graphs.session
            if graphs is not None
            else calculator.session
            if calculator
            else None
        )
        if session is None:
            return None
        rows = sorted(session.variables(), key=lambda row: row.name.casefold())
        if (
            sheet is not None
            and sheet.cursor[1] == NAME_ROW
            and not sheet.columns[sheet.cursor[0]][1]
        ):
            # an empty name cell lists the variables; a list links the column (sheet5, R5-E7)
            return MenuItem(
                "Variables",
                jump=True,
                items=tuple(
                    MenuItem(row.name, "sheet", f"link:{row.name}", hint=row.text)
                    if row.text.startswith("{")
                    else MenuItem(
                        row.name,
                        "insert",
                        row.name,
                        hint="function" if row.is_function else row.text,
                    )
                    for row in rows
                )
                or (MenuItem("(none)", "escape"),),
            )
        if sheet is not None and sheet.cursor[1] == NAME_ROW:
            lists = tuple(
                MenuItem(row.name, "sheet", f"link:{row.name}", hint=row.text)
                for row in rows
                if row.text.startswith("{")
            )
            return MenuItem(
                "var",
                items=(
                    MenuItem("Store var", "sheet", "store_var", key="1"),
                    MenuItem("Unlink", "sheet", "unlink", key="2"),
                    MenuItem(
                        "Link to:",
                        key="3",
                        jump=True,
                        items=lists or (MenuItem("(none)", "escape"),),
                    ),
                ),
            )
        # On a Graphs entry line a function comes with both brackets and the cursor between
        # them, `f9()` (emulator run 7, R7-B11).
        call = (lambda name: ("insert_linear", f"{name}({MARK})")) if graphs else None
        items = tuple(
            MenuItem(row.text, *call(row.name), hint="function")
            if row.is_function and call is not None
            else MenuItem(row.text, "insert", f"{row.name}(", hint="function")
            if row.is_function
            else MenuItem(row.name, "insert", row.name, hint=f"{row.name} = {row.text}")
            for row in rows
        )
        return MenuItem("Variables", jump=True, items=items or (MenuItem("(none)", "escape"),))

    def _open_wizard(self, name: str) -> None:
        wizard = self.profile.wizards.get(name)
        if wizard is not None and self.show_wizard is not None:
            self.show_wizard(wizard)

    def finish_wizard(self, wizard: Wizard, values: dict[str, str]) -> list[str]:
        """Paste what a dialog built. Returns the problems instead if a field will not do."""
        problems = wizard.problems(values)
        if not problems:
            if self._statistics_wizard is not None and self._statistics_wizard[2] is wizard:
                statistics, action, _ = self._statistics_wizard
                problems = statistics.finish_wizard(action, values)
                if not problems:
                    self._statistics_wizard = None
                return problems
            bindings = wizard.bindings(values)
            if self.sheet is not None and wizard.steps is None:
                # On a sheet a command's dialog (Distributions) puts `=its formula` in the
                # selected cell's entry line, to be entered with Return (run 4, S10)
                text = "".join(b.arg for b in bindings if b.action in ("insert", "insert_linear"))
                text = text.replace(MARK, "")
                bindings = [Binding("sheet", f"edit:={text}")] if text else []
            for binding in bindings:
                self.run(binding)
        return problems

    def escape_wizard(self, wizard: Wizard) -> None:
        """Esc in a dialog: back to the dialog before it, where there is one (a test's fields go
        back to its Data Input Method box: emulator run 6, R6-C3)."""
        for binding in wizard.back:
            self.run(binding)

    def store_wizard(self, wizard: Wizard, values: dict[str, str]) -> None:
        """Leave a live dialog's results in variables (the Finance Solver's `tvm.` set)."""
        calculator = calculator_of(self.document.current)
        if wizard.store is not None and calculator is not None:
            calculator.session.store_numbers(wizard.store(values))

    def _menu_key(self, binding: Binding) -> None:
        """While a menu is open it takes every key; a chosen leaf runs once the menu has closed."""
        assert self.menu is not None
        chosen = self.menu.press(binding.action, binding.arg)
        self._remember_catalog()
        if not self.menu.open:
            self.menu = None
        if chosen is not None:
            self.run(chosen)

    def _document_action(self, binding: Binding) -> bool:
        document = self.document
        kind = (
            PageKind(binding.arg or PageKind.CALCULATOR)
            if binding.action.startswith("add")
            else None
        )
        steps = int(binding.arg or 1) if binding.action.startswith("move") else 0
        actions: dict[Action, Callable[[], object]] = {
            "add_page": lambda: (
                document.can_add_page() and document.add_page(kind or PageKind.CALCULATOR)
            ),
            "add_problem": lambda: document.add_problem(kind or PageKind.CALCULATOR),
            "delete_page": document.delete_page,
            "next_page": document.next_page,
            "prev_page": lambda: document.next_page(-1),
            "move_page": lambda: document.move_page(document.page + steps),
            "move_problem": lambda: document.move_problem(document.problem + steps),
            "undo_pages": document.undo,
            "redo_pages": document.redo,
            "dialog": lambda: self.show_dialog and self.show_dialog(binding.arg),
            "new_document": self.new_document,
        }
        if binding.action in ("add_page", "add_problem") and not binding.arg:
            # ctrl+I, ctrl+doc, Doc > Insert > Page or Problem: choose the application first
            self._open_menu(binding.action)
            return True
        action = actions.get(binding.action)
        if action is None:
            return False
        action()
        self.retain_sheets()
        return True

    def _perform(self, keyboard: Keyboard, name: str) -> bool:
        binding = keyboard.press(name)
        if binding is None:
            return False
        cased = self._cased(binding) if keyboard is self.keypad_keys else binding
        assert cased is not None
        if cased.action == "paste" and not cased.arg and self.request_paste is not None:
            self.request_paste()  # the GUI fetches the system clipboard, then pastes
            return True
        self.run(cased)
        return True
