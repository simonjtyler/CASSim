"""Where things go for the window we are in: first-visit mode and the Handheld fit (FR-DEV-004).

Plain numbers in, plain numbers out, so the rules are tested without a browser. Handheld mode draws
the 320x240 screen and the keypad at their natural size and scales the whole thing to the window:
the keypad under the screen in portrait, beside it in landscape (NFR-PORT-003).
"""

from __future__ import annotations

from dataclasses import dataclass

from cassim.app.sizes import starting_view
from cassim.devices.nspire.ui.state import COMPUTER_MAX_SIDEBAR, COMPUTER_MIN_SIDEBAR, Mode

MARGIN = 12  # px kept clear round the scaled calculator
GAP = 12  # px between the screen and the keypad
SCREEN_W, SCREEN_H = 320, 240  # the handheld's pixels
KEY_W, KEY_H, KEY_GAP = 60, 40, 4  # one key unit; the keypad is 5 units across
MIN_SCALE, MAX_SCALE = 0.4, 2.5
BAR_H = 44  # the toolbar row above the calculator


def starting_mode(width: float | None, height: float | None = None) -> Mode:
    """The view for a first visit, and for a phone as it turns: on a phone, Handheld upright and
    Tablet on its side (SDD-15 section 8.2); else Computer."""
    return Mode(starting_view(width, height))


def key_span(units: float, size: int = KEY_W) -> float:
    """Pixels for a key `units` wide (or tall), so that keys and their gaps line up across rows:
    two half keys and the gap between them are one key."""
    return units * (size + KEY_GAP) - KEY_GAP


def keypad_size(width_units: float, height_units: float) -> tuple[int, int]:
    return round(key_span(width_units)), round(key_span(height_units, KEY_H))


DEFAULT_RATIO = 0.8  # the keypad's scale relative to the screen's until the splitter is used
MIN_SHARE, MAX_SHARE = 0.15, 0.8  # the splitter's range: the keypad's share of the room
MIN_ZOOM, MAX_ZOOM = 0.5, 2.0
SPLITTER = 10  # px: the draggable bar between the screen and the keypad
SIDE_SPLITTER = 26  # px: Tablet's bar: an 11 px < and > either side of its 4 px grip
MIN_PART_SCALE = 0.2
COMPUTER_MIN_WORKSPACE = 320
COMPUTER_MIN_KEYPAD = 240
COMPUTER_MAX_KEYPAD = 500
COMPUTER_SPLITTER = 24
COMPUTER_COLUMN_PADDING = 4


PHONE_MARGIN = 4  # px round the calculator on a phone, where every pixel counts
STATUS_H = 20  # px: the status line kept above the calculator in Handheld mode
# In full screen the keys are sized as if this much were still taken at the top (the status line
# and a phone's camera cutout), and the screen gets it: on a phone in portrait the keypad would
# otherwise grow into all of the extra height.
FULL_RESERVE = STATUS_H + 40


@dataclass(frozen=True)
class Sizing:
    """The user's choices: the keypad's share of the room (None: the default fit) and a zoom; and
    what else takes room: the toolbar's height, the margin, and whether there is a splitter."""

    share: float | None = None
    zoom: float = 1.0
    bar: float = BAR_H  # the toolbar's height above the calculator (0 when it is empty)
    margin: float = MARGIN
    splitter: bool = True  # a phone has no splitter, only half a gap between the parts
    side: bool | None = None  # keypad beside the screen (Tablet), under it (Handheld), or the best

    @property
    def between(self) -> float:
        """Px between the screen and the keypad: two half gaps round the splitter, or one."""
        return GAP + SPLITTER if self.splitter else GAP / 2

    @property
    def beside(self) -> float:
        """Px between the screen and the keypad side by side (Tablet), round its wider bar."""
        return GAP + SIDE_SPLITTER if self.splitter else GAP / 2


@dataclass(frozen=True)
class HandheldPlan:
    side_by_side: bool  # keypad beside the screen (landscape) instead of under it
    scale: float  # of the screen
    pad_scale: float  # of the keypad
    share: float  # the keypad's share of the room along the split, as drawn
    extent: float  # the room along the split in px, for turning a drag into a share


def clamp_share(share: float) -> float:
    return max(MIN_SHARE, min(MAX_SHARE, share))


def handheld_plan(
    viewport_w: float | None,
    viewport_h: float | None,
    width_units: float,
    height_units: float,
    sizing: Sizing = Sizing(),  # noqa: B008 - frozen, so one shared default is safe
) -> HandheldPlan:
    """The arrangement and scales for the window. By default each part is as large as the window
    allows across the split (so a phone in portrait has the screen and the keys full width), and
    when the two do not fit along it the keypad gives way first, down to `DEFAULT_RATIO` of the
    screen's scale, then both shrink together: the screen matters more than the keys. Of the two
    arrangements, the one with the larger screen wins. Once the splitter is used the keypad has a
    fixed share of the room instead, and each part scales to its own space. `zoom` then enlarges
    or shrinks both, so they may no longer fit the window."""
    zoom = max(MIN_ZOOM, min(MAX_ZOOM, sizing.zoom))
    pad_w0, pad_h0 = keypad_size(width_units, height_units)
    if not viewport_w or not viewport_h:  # the window size is not known yet
        return HandheldPlan(False, zoom, zoom * DEFAULT_RATIO, 0.5, 1.0)
    room_w = max(viewport_w - 2 * sizing.margin, 1)
    room_h = max(viewport_h - 2 * sizing.margin - sizing.bar, 1)

    def frame(side: bool) -> Frame:
        """Room along the split, the keypad and screen along it, the room across, and theirs."""
        if side:
            return room_w - sizing.beside, pad_w0, SCREEN_W, room_h, pad_h0, SCREEN_H
        return room_h - sizing.between, pad_h0, SCREEN_H, room_w, pad_w0, SCREEN_W

    if sizing.share is None:
        side_fit, top_fit = (_fill(frame(side)) for side in (True, False))
        side = side_fit > top_fit if sizing.side is None else sizing.side
        scale, pad_scale = side_fit if side else top_fit
        extent, pad0 = max(frame(side)[0], 1), frame(side)[1]
        share = pad0 * pad_scale / extent
        return HandheldPlan(side, scale * zoom, pad_scale * zoom, share, extent)
    side = _fill(frame(True)) > _fill(frame(False)) if sizing.side is None else sizing.side
    extent, pad0, screen0, across, pad_across, screen_across = frame(side)
    extent = max(extent, 1)
    share = clamp_share(sizing.share)
    pad_px = share * extent
    scale = min((extent - pad_px) / screen0, across / screen_across)
    pad_scale = min(pad_px / pad0, across / pad_across)
    top = MAX_SCALE
    return HandheldPlan(
        side,
        max(MIN_PART_SCALE, min(top, scale)) * zoom,
        max(MIN_PART_SCALE, min(top, pad_scale)) * zoom,
        share,
        extent,
    )


Frame = tuple[float, int, int, float, int, int]  # along, pad, screen; across, pad, screen


def _fill(frame: Frame) -> tuple[float, float]:
    """The screen's and the keypad's scales for one arrangement (see `handheld_plan`)."""
    along, pad_along, screen_along, across, pad_across, screen_across = frame
    along = max(along, 1)
    screen_top = max(MIN_SCALE, min(MAX_SCALE, across / screen_across))
    pad_top = max(MIN_SCALE * DEFAULT_RATIO, min(MAX_SCALE, across / pad_across))
    if screen_top * screen_along + pad_top * pad_along <= along:
        return screen_top, pad_top  # both fill the window across
    pad = (along - screen_top * screen_along) / pad_along  # the keypad gives way first
    if pad >= min(pad_top, screen_top * DEFAULT_RATIO):
        return screen_top, pad

    def length(k: float) -> float:
        return min(k, screen_top) * screen_along + min(k * DEFAULT_RATIO, pad_top) * pad_along

    low, high = 0.0, screen_top  # then both shrink: the largest k whose parts fit along the split
    for _ in range(40):
        middle = (low + high) / 2
        low, high = (middle, high) if length(middle) <= along else (low, middle)
    scale = max(MIN_SCALE, low)
    return scale, max(MIN_SCALE * DEFAULT_RATIO, min(scale * DEFAULT_RATIO, pad_top))


def full_screen_height(
    plan: HandheldPlan,
    viewport_h: float | None,
    height_units: float,
    sizing: Sizing,
) -> float:
    """The Handheld screen's height in full screen (or the installed app): taller than 240 px at
    its scale, to take the height the keypad leaves (keys below it), or the window's whole height
    (keys beside it). The width is unchanged, so the screen shows more lines."""
    natural = SCREEN_H * plan.scale
    if not viewport_h:
        return natural
    room_h = viewport_h - 2 * sizing.margin - sizing.bar
    if plan.side_by_side:
        return max(natural, room_h)
    pad_h = keypad_size(1, height_units)[1] * plan.pad_scale
    return max(natural, room_h - sizing.between - pad_h)


def computer_columns(
    viewport_w: float | None,
    sidebar_width: float,
    keypad_width: float,
    *,
    keypad_visible: bool,
) -> tuple[dict[str, float], float]:
    """Column widths for Computer mode and the row's total width. The workspace takes the
    remaining space, but keeps a minimum width and scrolls into view on narrow windows."""
    room = max((viewport_w or 1000) - 2 * MARGIN, 1)
    sidebar = max(COMPUTER_MIN_SIDEBAR, min(COMPUTER_MAX_SIDEBAR, sidebar_width))
    keypad = max(COMPUTER_MIN_KEYPAD, min(COMPUTER_MAX_KEYPAD, keypad_width))
    visible = ("sidebar", "workspace", "keypad") if keypad_visible else ("sidebar", "workspace")
    splitters = (len(visible) - 1) * COMPUTER_SPLITTER
    workspace = max(
        COMPUTER_MIN_WORKSPACE,
        room - sidebar - (keypad if keypad_visible else 0) - splitters,
    )
    widths = {"sidebar": sidebar, "workspace": workspace, "keypad": keypad}
    return widths, sum(widths[name] for name in visible) + splitters


def computer_screen_height(viewport_h: float | None, toolbar_height: float = BAR_H) -> float:
    """The Computer-mode screen fills the window below its top controls (at least 300 px)."""
    return max(300.0, (viewport_h or 800) - toolbar_height - 2 * MARGIN - 8)
