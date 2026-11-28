# SDD-15. Shared interface (CASSim's own menus, themes, views and dialogs)

Status: Standard agreed with Simon on 2026-11-26. It is written against `main` on that date; section 10 lists where the code does not follow it yet. The shared theme (section 7) was built on 2026-11-27, which closed gaps 1 to 3 and most of 17; the shared CASSim menu (sections 3 to 6) closed gaps 4 to 7 and 12; dialogs and wording (section 9) closed 8 to 11, 16 and 20 (the Nspire moved onto `SavedDocuments` on 2026-11-27); the Doc menu (section 9.4) closed 14 and 15; decision 0040 closed 21; `cassim.app.sizes` closed 18 on 2026-11-28. Touch sizes closed 19 the same day: Scientific's chips take taps over the bar's 48 px, and Pseudocode's grips and dividers are 40 px or more (hover hints are Flet tooltips, which also show on a long press). Most of 17 closed on 2026-11-28: Data & Statistics' plot colours, shadows, the pointer, error text and the swatches are tokens or live in `theme.py`. Views closed 13 the same day: every app has Computer, Tablet and Handheld (`STANDARD_VIEWS`, `sizes.starting_view`), a phone follows its orientation, and Settings ▸ Start in keeps the view each app opens in.
Applies to: the Home screen and every app (Nspire, Pseudocode & Python, Scientific, and later ClassPad and Prime).
Requirements: FR-DEV-002, FR-DEV-003, FR-DEV-004, FR-DEV-006, FR-DEV-008, FR-DEV-010, FR-THEME-001, FR-THEME-002, FR-DOC-010, FR-PROF-010 to FR-PROF-013, NFR-PORT-002, NFR-PORT-003.
Decisions: 0028 (clean room), 0032 (device interface and shell), 0033 (named documents).
Related: SDD-05 (the shell and the Nspire UI), SDD-14 (Scientific).

## 1. Scope

Every CASSim app has two kinds of interface, and they follow different rules.

| Kind | Examples | Rule |
|---|---|---|
| Follows the device | The Nspire Calculator Menu and Doc menu, its keypad and key labels, Document Settings; the Scientific key legends and modes | The device's order, numbering, structure and vocabulary (FR-DEV-005, FR-DEV-008, decision 0028). This document only sets their case (section 9.2). A learning aid may relabel a key for a moment, and a feature the device lacks may be offered, as long as it is marked as CASSim's own and can be switched off. The Scientific app's hyp names and its extras are examples (SDD-14 section 4.3, decision 0041). |
| CASSim's own | The CASSim menu; the Doc menu of an app that has no device Doc menu; Open and Save; Import, Export and Share link; themes; views; install and update; toolbars; tutorials; trace tables; Home | This document. The same words, order, look and behaviour in every app. |

Where the two meet, the device's structure wins and CASSim's items fit into it. For example, CASSim's Import, Export and Share link items go at the end of the Nspire's own File menu.

## 2. Principles

1. **Build it once, in the shell.** Menus, dialogs, the theme choice, update and view logic, and the size constants live in `cassim.app`. An app passes in its own items; it does not re-implement the menu or the dialog.
2. **Fixed sections and positions.** The CASSim and Doc menus have the same sections in the same order in every app. What is in a section can differ between apps. An item that can't be used right now is greyed, not hidden, so positions and Nspire menu numbers never move. Only a fact fixed when the app is built (Home exists in this bundle, this app has a keypad) can leave an item out.
3. **One setting, everywhere.** A choice made once, such as the theme or Start in, applies in Home and in every app. A choice that only one app has, such as the Scientific calculator model, sits beside it in the same dialog.
4. **State is visible.** A toggle shows whether it is on, the same way everywhere. A control that cycles shows its current value.
5. **Ask before losing work.** New, Open, Import, an example, Reset all and a reload for an update ask first when the work is unsaved.
6. **Touch everywhere.** Every view must work by touch as well as by mouse and keyboard, because many computers have touch screens (section 8.3).
7. **Material Design** (Material 3, which Flet implements) is the default for anything this document does not settle.

## 3. The top bar

The **CASSim** button comes first and the **Doc** button second, in every app and on Home. The CASSim button's label is `about.product_name()`, so it reads CASSim, or CASSimᵝ on the testing site. In the Nspire's Handheld and Tablet views, the keypad's CASSim key opens the same menu.

When `BrowserOffers.needs_attention` is true, the CASSim button (and the Nspire's CASSim key) shows a dot in the theme's `attention` colour. That happens when an update is ready or offline setup has failed. Its tooltip then reads "CASSim menu: update ready" or "CASSim menu: offline setup failed".

## 4. CASSim menu

### 4.1 Sections, in this order

| Section | Items | Notes |
|---|---|---|
| 1. Navigate | Home | All-in-one bundle only. |
| 2. View | The app's views as a one-of choice: Computer view, Tablet view, Handheld view. Then the app's panels as on/off items: Keypad, Tutorials, Sidebar. Then Fullscreen, or Avoid cutout on an installed phone. | One-of items show ● on the current view; on/off items show ✓ when on (section 6). An app with one view shows no view items. An app leaves out a panel item only when it has no such panel. |
| 3. Set up | Settings…, Appearance…, Keyboard shortcuts… | Settings… opens a dialog titled "Settings". Appearance… is described in section 7.3. |
| 4. The app | Install CASSim… or Uninstall CASSim…; the update item; the offline status | Section 5. |
| 5. Help | Help (wiki)…, About CASSim… | Use `about.product_name()` in the label, not a literal. |

Sections are separated by a divider in a menu bar, and by a thin rule in the Nspire's numbered menu panel. "Retry offline setup" is not a separate item: when offline setup has failed, choosing the offline status offers Retry in its notice, so the Nspire's numbers do not shift.

Home shows the same menu with its own subset: Settings…, Appearance…, the app section, and Help.

### 4.2 Form

Pseudocode and Scientific use `ft.MenuBar`. The Nspire draws its menus as numbered device-style panels, so its CASSim menu is one too, numbered 1–9 then A–Z. A shell function builds the item list once from the sections above plus the app's own items. Each app then renders that list: the menu bar, the Nspire panel, or Home.

## 5. Update, offline and install items

**The update item** has one label at a time, from `BrowserOffers.update_label`. Choosing it calls `Shell.activate_update`. No app writes its own label or fallback.

| Label | When | Choosing it |
|---|---|---|
| Check for updates | Nothing is known | Asks the site, then shows the answer in a notice titled "Check for updates". |
| Fetching update… | A new version is downloading | Checks again. |
| Reload to update | A new version is ready; the attention dot shows | Reloads. With unsaved work it first asks "Reload CASSim?" [Cancel] [Reload]. |

The unsaved-work question belongs in `Shell.activate_update`. The app passes in a callback that says whether it has unsaved work (`SavedDocuments` already knows).

**Offline status** reads "Offline: preparing", "Offline: ready", "Offline: unavailable", "Offline: unknown" or "Update failed". Choosing it shows the details; when setup failed, the notice has a [Retry] action. Every app shows it, because every app is part of the same installed site.

**Install CASSim…** is greyed unless the browser offers to install. Once CASSim is installed, the item becomes **Uninstall CASSim…**, which asks first and then explains the steps (`Shell.uninstall`).

## 6. Toggles and choices

| Kind | Use for | Looks | Label and tooltip |
|---|---|---|---|
| On/off menu item | Showing a panel; Fullscreen; Avoid cutout | ✓ before the label when on | A fixed noun: "Keypad", "Tutorials", "Fullscreen". The label never swaps (not "Show tutorials" and "Hide tutorials"). |
| One-of menu items | Views | ● before the current one | "Computer view", "Tablet view", "Handheld view". A shortcut picks its view; it does not toggle. |
| Toolbar toggle button | The same panels, on a toolbar | `accent` fill when on, `key` fill when off; the same label both ways | The tooltip says what a click does ("Hide the keypad"). Screen readers announce it as a toggle with its state. |
| Segmented choice | Two to four named options seen together: Handheld \| Computer, Pseudocode \| Python, Guide me \| Show me \| Test me | The selected segment has the `accent` fill and no tick icon | Each segment is a word. |
| Cycle chip | A mode with a short value: Rad/Deg, Auto/Approx, Math/Line, Trace | Shows the current value as an outlined chip | Tooltip: "Angle: radian. Click for degree." It must take keyboard focus. |

A setting appears in one place only. Remembered states:

| Remembered per browser | Saved in the document | Not remembered |
|---|---|---|
| The theme and colour changes; Start in; which panels show (keypad, tutorials, sidebar), except on a phone; column splits and zoom; editor preferences; the calculator model; the Scientific app's TABLE extra and hyp names | Maths settings (angle, number mode, display format, the Scientific app's exact-surds extra); trace orientation; which page is open | Fullscreen; open menus; collapsed panes; a view chosen during a session |

## 7. Colour schemes

### 7.1 One theme for CASSim

There is one theme choice for the whole of CASSim, saved shell-wide as `theme_name` under `cassim.system`, which Home already writes. Every app reads it when it starts and whenever it changes. No app keeps its own list of theme names. The presets are Dark (the default, FR-THEME-001), Light and High contrast, and Outline when FR-THEME-002 adds it. Flet's `ThemeMode` is LIGHT for Light and DARK for the rest, set in one shell function.

### 7.2 Tokens

- `cassim.app.theme.Theme` holds the shared tokens: page, panels, text, accent, menus, error, attention, warning, success and focus.
- An app's own tokens go in a skin derived from the shared theme under the same preset names. That covers Scientific's chassis, LCD and key faces, and the Nspire's key styles.
- No literal colours in UI code: every colour comes from a token. The tokens to add first are `attention`, `warning`, `success`, `chip_edge` and `line_highlight` (section 10).
- The whole app follows the theme, including its toolbars and top bar.
- A test checks every token with `contrast()` in each preset: at least 4.5 : 1 for text and 3 : 1 for borders and focus rings.

### 7.3 Appearance dialog

One dialog, built in the shell. It opens from CASSim ▸ Appearance… everywhere, on Home too.

1. **Theme:** a segmented choice, Dark | Light | High contrast.
2. **The app's own look**, if it has one: Scientific's Calculator model drop-down, supplied by the app.
3. **Customise colours:** the Nspire's editor for each token (a swatch, a `#RRGGBB` box, the error "Use #RRGGBB"). It is folded away by default and available in every app. Changes are saved per preset. Theme files to import and export (FR-THEME-002) attach here later.
4. **Buttons:** [Reset preset] on the left; [Cancel] [Save] on the right (section 9.1). Changes preview live, and Cancel puts the previous look back.

## 8. Views and screen sizes

### 8.1 Views (chosen)

| View | What it is | Nspire | Pseudocode & Python | Scientific |
|---|---|---|---|---|
| Computer | Keyboard and mouse first: the toolbar, side panels, resizable columns, a large work area | Sidebar, workspace, optional keypad | Code and Console beside Run controls, Symbols and Trace, with a splitter | Calculator beside the tutorials, with menu bar and chips |
| Tablet | Handheld with two columns side by side, with targets sized for touch | Display beside keypad | The two columns, without the splitter | Calculator beside the tutorials |
| Handheld | One column: the device as it looks, scaled to fit | Display above keypad | Columns stacked in reading order | Calculator only, with tutorials below |

All three views work by touch, mouse and keyboard. An app that cannot sensibly offer a view leaves it out of the menu.

### 8.2 Screen sizes (found)

| Size | Test | Effect |
|---|---|---|
| Phone | Shorter side under 600 px | Handheld in portrait, Tablet in landscape. Computer view is greyed with the hint "Not on a phone". Optional chips hide. Margins are small. Which panels show is not saved. |
| Narrow | Width under 900 px | Computer view stacks its columns, as in Handheld. |
| Installed phone | `offers.installed` on a phone | Avoid cutout replaces Fullscreen. |

The constants, the tests and the dialog width rule live in `cassim.app.sizes`. A dialog's content is `clamp(200, preferred, window − 128)` wide: an AlertDialog keeps 40 px either side and pads its content by 24 px, so a 360 px phone leaves 232 px.

### 8.3 Touch in every view

- Every control works by tap. Nothing needs hover, right-click or a modifier key: a hover hint also shows on long press, and a context menu also opens on long press.
- Touch targets are at least 48 px in Tablet and Handheld (Material), and at least 40 px in Computer, where the hit area may be larger than what is drawn. That includes splitters, resize grips and drag handles.
- Typing in a text box on a touch screen brings up the on-screen keyboard (the Nspire's `soft_keys.py` does this today).

### 8.4 Choosing the view

On the first visit the screen size picks the view, and keeps picking it on resize until the person chooses one. After that, Settings ▸ Start in decides which view each launch opens in. A view chosen during a session lasts until the app is closed and is not saved.

## 9. Dialogs and wording

### 9.1 Dialog buttons (Material 3)

- Actions are text buttons at the bottom right. The confirming action is last (rightmost) and the dismissive action (Cancel) comes just before it. A third, neutral action (Reset preset) goes at the left.
- The confirming button's label is the verb for what happens: Save, Replace, Delete, Discard, Reload, Open, Copy link. A notice with one button uses OK. A read-only panel (Keyboard shortcuts, About) uses Close.
- Change `Shell.confirm` and `Shell.notice` once, and every app follows.

### 9.2 Words

| Rule | Do | Not |
|---|---|---|
| Sentence case everywhere: CASSim's labels, titles, notices, and the device menus' labels | Save as…, New document, Settings & status, Check for updates | Save As…, Check for Updates |
| Ellipsis when the item opens a dialog that asks for something more | Settings…, Open…, Uninstall CASSim… | Settings, Open Document |
| Write menu paths with ▸ | Doc ▸ Export file… | Doc > File > Save to file |
| A confirmation title is a question | Reset all?, Replace saved program? | Reset all |
| Names go in curly quotes | Delete “Quadratics”? | Delete "Quadratics"? |
| Say where things are kept the same way everywhere | Saved in this app, on this device. | Saved in this browser. |
| A dialog's title matches the item that opened it | Settings… opens "Settings" | Handheld Setup… opens "System Settings" |
| A command CASSim does not do yet | Greyed, with the hint "Not in CASSim yet" | Hidden |
| Shortcuts: each key capitalised, joined with + | Ctrl+O, Alt+Shift+C | ctrl+O |
| Menu hints: a keyboard shortcut sits beside its item; any other hint (a command's syntax, "Not in CASSim yet") goes in the line under the menu for the highlighted item, in every view | Normal Pdf… with normPdf(XVal,μ,σ) under the menu | the syntax beside each item, widening the menu past the screen |
| The product name comes from `about.product_name()` | About CASSimᵝ… on the testing site | A literal "About CASSim…"; the page title "CASSim-pseudocode" |

Sentence case changes only the capital letters of a device menu's labels. Their words, order and numbering still follow the device. Command names keep their spelling (`completeSquare`, `solve`).

### 9.3 Shared dialogs

These come from `cassim.app` (`saved.py`, `shell.py`, `warning.py`):

- Open, Save as, Replace, Delete, Discard changes and Saved
- Import, Export and Share link
- About, Warning, Check for updates and Uninstall

The app supplies only its noun ("document", "program", "calculation") and its file types.

### 9.4 Doc menu

**Sections, in this order:**

1. **Document:** New, Open…, Save, Save as…
2. **Files:** Import file…, Export file…, Share link…
3. **The app's own sections**, such as Examples ▸, or the Nspire's Edit and Settings & status
4. **Clear:** Reset all…, only where the app has settings or memory to clear (Scientific)

**What New does:** the Nspire opens a new document. Pseudocode opens a blank program. Scientific clears the calculation and keeps the settings, unlike Reset all.

**Asking first:** New, Open, Import and an example all ask "Discard changes?" first when the work is unsaved.

**Device Doc menus:** a CAS calculator with its own Doc menu (the Nspire now, ClassPad and Prime later) keeps the device's sections and numbers. CASSim's Import file…, Export file… and Share link… go at the end of its File section.

### 9.5 Running code

The Pseudocode & Python runner is sandboxed, so Run runs at once, with no permission prompt (decision 0040). No user code runs as Python: a Pseudocode program, a Python program (translated to pseudocode first) and a Console line all go through CASSim's own interpreter. Code that arrives from Open, Import, an example or a share link never runs by itself: it waits for Run. Stop must end a run within 1 s.

## 10. Where the code differs (2026-11-26)

Paths are under `src/cassim/`; line numbers are approximate. The list is ordered by what to fix first. A row is deleted when its gap is closed, so the numbers are not consecutive.

| # | Gap | Where | Change |
|---|---|---|---|
| 17 | Two sets of colours are not tokens yet: the cursor bar the editor writes into its LaTeX and the maths selection's defaults (`COLOURS_LEFT` in `tests/test_interface_rules.py`). The frame round the code editor keeps the Dracula background (`code_background`) in the Light preset, where the editor itself is light | `device/editor.py`, `app/math_canvas.py`, `devices/pseudocode/ui/app.py` | Pass the theme's `accent` and `selection` to the editor's LaTeX; `code_background` per preset. |

## 11. Checklist for a new extra

Before a CASSim-own feature, panel or app merges, check that the items below hold. Three of them are tested for every app (`tests/test_interface_rules.py`): labels in sentence case, Cancel before the confirming button, and no new literal colours. Each has a frozen list of what does not follow it yet, which may only shrink; the test prints the fix for a label (`sentence()`).

- [ ] Its menu items are in the right section of the CASSim or Doc menu, in sentence case, with an ellipsis if they open a dialog, and greyed (not hidden) when they can't be used.
- [ ] It uses the shell's menus, dialogs, Open and Save, theme, update and size helpers, and adds none of its own.
- [ ] Every colour comes from a theme token. A new token has a value in every preset and a contrast test.
- [ ] It works in each view the app has (Computer, Tablet, Handheld), by touch, at phone size (360 px wide, in both orientations; NFR-PORT-003).
- [ ] Its toggles and choices use the kinds in section 6, and its remembered states fit the table there.
- [ ] It asks before discarding work.
- [ ] It can be reached by keyboard, with a visible focus ring. Any gaps are listed in `docs/accessibility.md`.
- [ ] Its help page in `docs/wiki/` and this document are updated in the same change.
