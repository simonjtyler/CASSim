# CASSim — plan and architecture (draft for review)

A static, installable (PWA) family of browser apps for calculators and programming:
Nspire and Pseudocode & Python are the current devices, with ClassPad, Prime and later devices able
to join the same shell as plug-ins. Device engines run client-side via Pyodide where needed and the
UI is built with Flet. Draft v0.5, 2026-11-19.

**Requirements live in `docs/SRS.md` (draft 0.9; every question is answered except Q17, Q18, Q19 and Q22, which concern ClassPad and HP Prime, and Q21, which is partly answered).** This plan is the architecture and milestone view; where the two disagree, the SRS wins for *what*, this file for *how and when*. CASSim is a **simulator, not a hardware emulation**, released under the **MIT licence** (decision 0042).

**Roadmap after the Nspire core (updated 2026-11-19).** M0–M4 build the Nspire Calculator, data pages and Graphs/Table/Notes. M2x and M5 established the multi-app shell: the all-in-one app always opens to the Home chooser, Nspire and Pseudocode & Python are current choices, and each device can also be built on its own. M5 continues the Python and pseudocode work; TI-Basic and library extensions follow in M6, with final polish in M7. M8 adds the Casio ClassPad device to the existing shell (Could), and M9 may add HP Prime (Would). See section 3.2 and milestones M5–M9.

## 1. What I checked while exploring (and what I didn't)

| Finding | Status |
|---|---|
| `flet publish` produces a static site with `manifest.json`, `flutter_service_worker.js`, icons and `python-worker.js`. Python 3.14 pins Pyodide 314.0.7. | Ran it (Flet 1.0.5) |
| Pyodide 314.0.7 ships numpy 2.4.6, scipy 1.18.0, sympy 1.14.0, mpmath, micropip. | Pyodide docs |
| Flet docs: static sites run Python in the browser; long CPU work can freeze the UI. `python-worker.js` hints Python may run in a worker. | Docs + build output; worker, cancel and restore verified (decision 0005) and built in M2e |
| SymPy 1.14 does the core VCE operations quickly (solve, factor, apart, diff, integrate, limit, dsolve, det: each under 0.11 s natively; import 0.22 s, scipy import 1.4 s). | Ran `spikes/sympy_timings.py` |
| A TI-syntax evaluator spike (`:=`, `→`, `f(x)`, `solve(...)|x>0`, `[1,2;3,4]`, implicit multiplication, `√`, `π`) works but only through regex hacks. A real parser is needed. | Ran `spikes/ti_eval_spike.py` |
| **Divergence found:** `solve(sin(x)=1/2,x)` returns only the principal values in SymPy; TI returns the general solution with `@n1`. Expect many such differences, so the golden corpus (section 6) is essential. | Ran |
| `.tns` files are a proprietary container (`*TIMLP0601`, `Document.xml`, `Problem1.xml` entries) with opaque payloads. The community format notes I found say no known way to read them. Any future decoding follows the clean-room rule (NFR-LEG-008): public documentation or black-box comparison of files Simon made, never decompiling TI software. | Inspected your `mm_*`/`gm_*` files; **not decoded** |
| Whether SymPy + SciPy actually load and run inside the Flet static build, and the cold-start time and download size. | Tested in M0 spike 1: go (decision 0002) |

## 2. Principles

1. **Engine first, UI second.** A pure-Python core (no Flet imports, enforced by a lint rule) that is usable from a CLI, tests and the browser.
2. **A headless "device model"** (keys, menus, cursor, screen buffer) sits between engine and Flet, so keyboard and page behaviour is tested without a GUI. Flet only renders it.
3. **Behaviour is defined by the simulator, not by SymPy.** Every behaviour we claim is pinned by a golden test captured from the real TI-Nspire CX CAS simulator. The target is "close enough not to confuse a student or teacher": same mathematical content in a familiar form, exact text only where a case says `compare: exact`.
4. **Typed, linted, reproducible:** uv, Ruff, Ty, Git, CI from day one. SymPy is weakly typed, so it is quarantined behind one typed adapter module.
5. **Original implementation.** Copy behaviour, structure and vocabulary; never copy expression or code (decision 0028). No TI ROM, TI artwork or logos. The handheld skin is our own design that keeps the familiar layout, drawn from scratch rather than traced. Behaviour is learned only by using TI's software and handheld (the corpus), never by decompiling, disassembling or inspecting their binaries (NFR-LEG-008), and help and explanatory text is CASSim's own (NFR-LEG-009). A visible disclaimer says CASSim is not affiliated with TI and is not an approved exam calculator.
6. **Private by construction.** No server, no telemetry or analytics, no student data leaves the device. Imported documents and share links never auto-run code.
7. **Core first, then Code and extensions.** The Python/pseudocode environment starts after M4, before TI-Basic and library extensions. Other devices start after M7. Earlier work must not make either later stage harder; the M2 profile guard and M2x device boundary apply throughout.

## 3. Architecture

```
cassim/
  pyproject.toml            uv project; ruff + ty + pytest config; dependency groups: dev, test, web
  src/cassim/
    core/                   PURE PYTHON, no Flet
      lexer.py parser.py ast.py     TI grammar -> AST (Pratt parser), pretty-printer
      values.py                     typed Value union: Number, Expr, List, Matrix, Str, Bool, Eq, Void, Unit
      settings.py                   angle, calc mode (Auto/Exact/Approx), Real/Rect/Polar, float digits, base
      scope.py                      Document > Problem > Variables; library namespace (lib\fn); Local; Ans
      evaluator.py                  AST -> Value, mode-aware
      catalog/                      command registry by area: algebra, calculus, linalg, lists, stats, prob,
                                    finance, number, complex, string, trig/hyp, convert (►Polar etc.)
      compat/sympy_adapter.py       ONLY place that touches SymPy internals; TI-compat fixes (solve families
                                    @n1, cSolve, domain constraints, simplification/format differences)
      format.py                     Value -> TI linear text AND a 2D layout tree (fraction, sqrt, power, matrix)
      results.py builtin_names.py   what the UI holds without importing SymPy (decision 0027)
      errors.py                     TI error codes/messages
    basic/                  [placeholder] TI-Basic lexer/parser/interpreter (Prgm, Func, control flow, Disp/Request/Text, Try)
    pylib/                  [placeholder] Python-script bridge + sandbox API (see 5.4)
    libs/                   [placeholder] native Python ports of mm_/sm_/gm_ style libraries, registered as lib\fn
    sheet/                  Lists & Spreadsheet engine, headless (slice 3a): refs.py (cell, `$`, range and `a[]`
                            references in formulas), sheet.py (cells, named columns = lists, formula columns, deps graph)
    stats/                  Backend-neutral Data & Statistics value parsing and plot scenes (slice 3d);
                            regression fitting is shared with core/compat/statistics.py (pure Python, no SciPy)
    graph/                  scene.py: the backend-neutral scene (FR-GRAPH-006, slice 3.0); sampling.py: checked math-source compilation,
                            windows, ticks and adaptive function sampling; analysis.py: headless Trace and Analyze Graph numerics;
                            zoom.py: the Window / Zoom windows and window values; later: other entry types and their scenes
    doc/                    Document > Problem > Page, the versioned JSON serialiser (migrations, replay_steps) and share
                            links. Page types are registered by the device, not named here (decision 0032, M2x step 2)
    device/                 headless device framework: key layers (shift/ctrl/var/menu/doc), menu tree (data-driven), input
                            editor and the entry session each page's entry line uses (entry_session.py: undo, clipboard,
                            keys), the maths layout every maths line is painted from (math_layout.py and the fonts' numbers
                            in math_metrics.json, decision 0038), wizard, clipboard, the Profile type; and, until slice 3.0,
                            the engine protocol (engine.py)
    cli/                    `cassim` REPL (prompt_toolkit) + `cassim run file.tib`
  src/cassim/app/            FLET: the shell only (decision 0032): main.py owns Home and lazily mounts the selected device;
                            home.py draws the all-in-one chooser without importing device UI; shell.py is what a device's UI
                            may use (storage, files, clipboard, links, notices, About, install and full screen, the engine
                            worker); math_canvas.py (maths lines painted on a canvas from device/math_layout.py, decision 0038); saved.py (Open, Save and
                            Save As on documents kept by name in the app's storage, for any device, decision 0033);
                            sizes.py (phone, narrow, dialog width and touch sizes, SDD-15 8.2);
                            web.py, about.py, theme.py,
                            keyboard.py, assets
  src/cassim/devices/        one plug-in package per calculator (decision 0032): the Device interface, the table of sites,
                            load(id). A device never imports another device, and imports without Flet
    nspire/                 DEVICE; keymap.py, menus.py, syntax.py (the profile data); pages/ (page types, Calculator and
                            Graphs models); screen.py, runner.py, document.py; ui/ (FLET: app.py joins state.py to views.py,
                            layout.py and the Graphs controls; the only part of a device that imports Flet)
    pseudocode/             DEVICE; standalone Code view in ui/ (Flet), backed by runtime/pseudocode/
    scientific/             DEVICE (SDD-14); CASSim Scientific scientific calculator: keys.py (keypad and keyboard),
                            layouts.py (other calculators' keypads),
                            values.py, layout.py, editor.py, parser.py (Pratt; no eval), display.py,
                            engine.py (statistics), state.py, tutorials.py, examples.py;
                            ui/ (FLET: app.py, render.py, skins.py; the only part that imports Flet)
  src/cassim/bundle.py       the devices in this build; tools.publish writes its own copy (M2x step 5)
  src/cassim/runtime/        pseudocode lexer, parser, interpreter, trace, syntax file, printer (M5b, built)
  tests/  unit/  corpus/  device/  e2e/
  corpus/                   golden cases (YAML); their simulator screenshots are in CASSim-evidence
  tools/                    capture + replay tooling for the simulator corpus
  docs/  spikes/
  ../CASSim-evidence/       separate repository: screenshots, capture briefs, references/ (0039)
```

### 3.1 Key design decisions

- **Parser.** Pratt parser over a real tokenizer for: `:=`, `→`/`->` store, `|` constraint (lowest precedence), implicit multiplication (`2x(x-1)` vs `f(x)` call vs `ax` variable), `^` with TI's unary-minus rules, `√`, `π`, `ᵀ`/`@t`, `≤ ≥ ≠`, `and/or/not/xor`, lists `{}`, matrices `[1,2;3,4]`, strings, `lib\fn`, `@n1` arbitrary-constant names, `#` indirection, `'` primes, units `_m`. Round-trip tested (parse → print → parse) with Hypothesis.
- **Values.** Typed `Value` union; arithmetic wraps SymPy objects but exposes only our types. Exact/Approx is a property of evaluation (mode + a decimal point forces approximate), matching TI's rules.
- **Settings.** Document-level (angle, calc mode, real/complex, digits) plus system-level. Presets for the three VCE courses (General: Degree/Approximate/Real; Methods: Radian/Auto/Real; Specialist: Radian/Auto/Rectangular, from the cas-solver skill).
- **Scoping.** Document → Problems → Pages. All pages in a Problem share variables; a new Problem is a blank slate; `Define`/`→` writes the current Problem; library functions are document-wide and read-only; `Local` for programs.
- **Long-running work.** Evaluation must be cancellable (TI's On/Esc). Plan: CAS runs in a worker; cancel = terminate and restart worker with state restored from the document model. Verified in M0 spike 1.
- **Heavy dependencies.** SymPy loads at start. SciPy and NumPy are not shipped: the statistics and numerics are pure Python and mpmath, with SciPy used only by the tests as an independent check (decision 0031). Service worker caches everything for offline use.
- **Shared data.** Within a Problem every page is a view of the same variables, which live in the engine worker. The document stores definitions and view state; values are recomputed. Variables carry revision numbers so a page redraws only what changed, and each page's model and scene are kept so switching does not wait for the engine (decision 0031; FR-DOC-008, NFR-PERF-006).
- **2D maths display.** `format.py` returns a layout tree; the renderer draws it (Flet canvas). Input is a 2D template editor (decision 0015): the tree model in `device/editor.py` draws itself as LaTeX with a cursor glyph and writes the linear TI text for the parser, so the engine is unchanged. Engine text comes back into the tree through the parser (`device/editor_ast.py`); decision 0035 plans one template registry and shared renderers. *As built (decision 0038, 2026-11-26): the tree is set out in Python from the KaTeX fonts' metrics (`device/math_layout.py`) and painted on a Flet canvas (`app/math_canvas.py`), with the cursor and the selection on layers of their own; the entry line, the history, graph entries and sheet cells are all drawn this way, and LaTeX remains only for rows that have no tree.*
- **Storage.** *As built (M3 slice 3.0): the autosave and System Settings are in IndexedDB in the browser (`TextStore` in `app/web.py`, reached through the shell), and the autosave waits half a second after the last change; an older localStorage copy is read until it is next written. The desktop app keeps Flet `SharedPreferences`.* Documents live in browser storage (IndexedDB via Pyodide `js` interop; localStorage is too small and Flet client_storage may be limited: spike 5). Upload/download of the native `.cassim.json` (versioned schema, schema-validated and size-limited on import). Open and Save read and write only `.cassim.json`. `.tns` is deferred (Won't for now) and nothing depends on it; if it is built it goes under File > Import… and Export…, never Open or Save (FR-DOC-006).
- **Sharing.** A document can be shared as a URL: compressed and encoded in the URL **fragment**, so nothing reaches a server. Opening a link asks for confirmation first. Keep links under about 2,000 characters; larger documents fall back to file export.
- **Themes.** Dark is the default. Themes (at least Dark, Light, Outline) are defined in a user-editable config file (keypad, screen and accent colours), persisted in browser storage and exportable; an invalid config falls back to Dark with a message.
- **Accessibility.** Should-have, applied where cheap. Keyboard-only use and visible focus in Computer mode are required. Flet renders to a canvas, so screen-reader support is hard: gaps are recorded in `docs/accessibility.md` and stubbed (labels and semantics hooks), not silently skipped.
- **Graphics.** Engine emits a scene; Flet `canvas` draws it. Charts libraries are not suited to implicit functions, asymptotes and trace; matplotlib is too heavy for Pyodide.
- **Spreadsheet.** Custom calc engine (TI cell/column semantics, columns are shared Problem variables so they can't map onto Excel-style engines like `formulas`/`pycel`). A library is used only for I/O: stdlib `csv` and `openpyxl` (pure Python; confirm it loads in Pyodide) for xlsx import/export.

### 3.2 Code runtime and later device profiles (M5, M8–M9)

The Python/pseudocode runtime is M5 and starts after M4, before the M6 programming extensions. The
device interface, Nspire move, all-in-one Home chooser and bundle-aware build came in M2x/M5
(section 15); Nspire and Pseudocode are peers in that shell. ClassPad remains M8, and HP Prime M9.

**Device profile.** Everything that makes one calculator behave like itself is bundled as a profile; the engine pieces that are genuinely common stay shared.

| Layer | Shared | Per profile |
|---|---|---|
| Maths | SymPy adapter, Value types, exact/approximate machinery, stats and distribution maths, spreadsheet calc engine, graph sampler and scene format | Compat fixes (solution forms, simplification differences), number-display rules, error codes and messages |
| Language | Tokenizer and Pratt-parser framework | Dialect: grammar tables, symbols, command names and arity, catalogue |
| Document model | Storage, versioned-schema machinery, autosave | What a document is (Nspire: Document > Problem > Page; the others as their oracle shows) and its page/app types |
| Device model | Key-layer, menu and screen-buffer framework | Keymap, menu tree, skin, presets (e.g. the VCE settings) |
| Evidence | Corpus format and replay tool | `corpus/<device>/` cases captured from that device's oracle |

Layout: `src/cassim/devices/nspire/`, `.../scientific/`, `.../classpad/`, `.../pseudocode/`, `.../prime/` (each a plug-in, section 15), with `core/` keeping the shared parts. Today's TI-specific parts of `core/` (grammar tables, catalogue, error table, display conventions) move under `devices/nspire/` in M8a, when the ClassPad shows what is shared (decision 0032 item 7, agreed 2026-11-13; M2x moved everything else); the Nspire corpus is the safety net, and the refactor is done when every Nspire case replays unchanged. The Nspire symbol and statistics conventions (SRS C-4, C-5) stay the Nspire profile's; other profiles take theirs from their own oracle.

**Runtime for Python and pseudocode** (`src/cassim/runtime/`). A small `Interpreter` interface: run source against an I/O context, stream output, accept input, report errors with line and column, cancel. Two implementations:
- *Python*: CPython from Pyodide in a **dedicated worker**, separate from the CAS engine. A runaway script is cancelled by terminating its worker (as in decision 0005) without touching CAS state. The goal is no network and no host-page access for user code; how that is enforced (CSP, removing the `js` bridge, or both) is a spike before the build, and any gap that cannot be closed is documented rather than hidden.
- *Pseudocode*: our own tokenizer, parser and tree-walking interpreter in pure Python, so the same code runs in the CLI, the tests and the browser. The dialect is the VCAA pseudocode as extended by the author's conventions document (`docs/pseudocode/dialect.md`): numeric types (integer, rational, real, complex) and basic strings only, function-valued parameters, and tolerant of the slips found in real exam text. Errors are reported in pseudocode terms and an execution-step limit stops runaway loops. A tree-walker is preferred over translating to Python because it gives clean errors, a step budget and a trace for free.

**Where it appears.** (1) A **Code view**: editor and console with no device skin, files in browser storage, import/export of `.py` and `.txt`. It is the `pseudocode` device: one entry in the all-in-one app's switcher and its own small site (section 15; Q23 revised 2026-11-13). (2) **Page types**, Python and Pseudocode, registered by any profile that wants them. The Nspire profile gets both: as I understand it the CX II models have a native Python page (the plain CX does not), and pseudocode is a deliberate extension that the UI labels as not a handheld feature. Whether ClassPad and Prime offer them is SRS Q22. Pages are self-contained in M5. A bridge to the Problem's variables and a `py()` call from the CAS is a Could-have for after M5 (the real Nspire does not allow it, so it would be a CASSim extension). Nothing auto-runs, ever (SRS C-7).

**One program tree, two languages.** Pseudocode (our parser) and the supported Python subset (the standard `ast` module) are both turned into one internal program tree. Printers turn the tree back into pseudocode or readable Python, which gives translation in both directions. Normal Python **Run** still uses CPython; the tree interpreter exists for pseudocode and for tracing. The risk is the two drifting apart, so every golden program is run both ways (differential test, reals compared numerically) and round trips are property-tested.

**Stepwise trace tables.** The interpreter emits an event per step (assignment, condition with values substituted, call, return, output, input). The events are kept, so stepping forwards **and backwards** moves a cursor instead of re-running, and random numbers and input replay identically. Two views of the same events: a **vertical** trace table (one row per executed line, a variable cell filled where it changes) that works for anything, and a **horizontal** desk check (code down the side, one column per loop pass) when the run has one main loop and no nesting. Auto picks; the user can switch. Layouts and the reference example: `docs/pseudocode/trace-tables.md`.

**Settings bar.** The Code view's editor has a bar at the top with two controls, Number mode (Approx / Auto / Exact, the TI rule being Auto) and Angle (Radian / Degree), and a "…" menu for everything else (display precision, default 6 significant digits Mathematica-style; Real/Complex; Gradian; random seed; step limit; syntax). They govern pseudocode runs, traces and translation (Auto and Exact emit `Fraction`, Degree wraps trigonometry in `radians()`); a direct CPython run cannot honour them, so they show as disabled with the reason. On a Nspire page the bar starts from the document settings.

**Configurable syntax.** The pseudocode grammar is driven by a **syntax file** (`docs/pseudocode/syntax-default.yaml`) kept in browser storage, editable in the app and exportable. It lets one construct be written several ways, each spelling accepted, warned about or rejected, with optional tokens (`then`, `do`, the colon, parentheses) and several block terminators (`end for`, `endfor`, `next`). The same file's emit section sets what the printer writes. The parser is therefore table-driven rather than hard-coded; the code pane always shows the user's own text. Because a free grammar can become ambiguous, files are validated, data-only, size-limited and fall back to the default if invalid; property tests restyle and re-parse every golden program under every preset.

**Switching (implemented).** The all-in-one app (`cassim-app`, `cassim-calc`) always opens to a Home
chooser; it does not remember the last-used device. The current enabled devices are Nspire and Pseudocode & Python;
unbuilt choices stay visible and disabled. Device documents, settings and worker lifetimes remain
separate. Per-device lazy archives and download-on-first-open are the remaining cache work described
in section 15.3; the shell does not need to be redesigned when another profile is added. Display
modes (section 4) apply where a device supports them. Each built device can also be published as a
smaller single-device site (section 15).

**Oracle per device.** The Nspire uses the TI teacher software. For ClassPad and Prime the natural oracles are the manufacturers' own PC emulators (as I understand it, ClassPad Manager and the HP Prime Virtual Calculator); I have not checked availability or licence terms. The capture effort that dominated M0/M1 will recur, so each new profile ships Tier 1 first. Python semantics need no oracle (it is CPython); device-specific Python modules (e.g. TI's `ti_system`, `ti_plotlib`) are a later extra if wanted.

## 4. GUI modes (shell plus device-specific layouts)

| Mode | Layout | Use |
|---|---|---|
| **Computer CAS** (equal top priority) | Wide window: page tabs/sidebar (problems → pages), large 2D calculator pane, scrollable history, templates palette, variable/catalog panel, physical keyboard first | Teacher/student at a desk |
| **Tablet / demo** | Screen on one side, on-screen keyboard on the other (portrait/landscape), big touch targets, optional "show keystrokes" for projection | Live demonstration |
| **Handheld** (equal top priority) | Faithful-layout 320×240 screen + keypad; scales to fullscreen on phones; hardware keyboard mapped | Practising the real handheld workflow |

The device model drives all three; modes differ only in layout components and which panels are visible. Primary test targets: Chromebooks, Chrome, Safari (macOS, iOS, iPadOS); secondary, smoke-tested: Edge, Firefox. Handheld mode must be usable at 360 px wide in both orientations. Hosting is any free or cheap static host with correct MIME types (Cloudflare Pages, section 14).

**Profiles and modes.** Switching device is orthogonal to these modes: a profile supplies its own
handheld skin, keymap and page set, while the Computer and Tablet layouts are shared components
where the profile supports them. The Code view has no calculator skin. The ClassPad is
stylus/touch-driven, so its Handheld mode may need a touch-first interaction model rather than a
key-sequence one (SRS Q19).

## 5. Features by area

1. **Calculator page.** History, `Ans`, ctrl+enter approximation, templates, catalog, variable menu, copy/paste of results, errors.
2. **Pages:** Calculator, Graphs, Lists & Spreadsheet, Data & Statistics, Notes, Program Editor, Python (new), Pseudocode (new, M5). Geometry is out of scope.
3. **Documents.** Multiple documents, problems, page sorter, settings dialogs, undo/redo, autosave.
4. **Extending beyond the real calculator.** (a) TI-Basic programs/functions, including `Define LibPub` libraries, in M6. (b) A Python page, built in M5 with the pseudocode pages. It is self-contained in M5. A `py("script","fn",args)` call from the CAS and a `cassim` API for Problem variables are a Could-have for a later stage, since the real Nspire does not allow that bridge. Python in an uploaded document **never auto-runs**: it waits for an explicit "Run", since documents and share links are untrusted. The sandbox is mandatory; there is no prompt (decision 0040).
5. **Libraries (mm_/sm_/gm_).** The `.tns` libraries cannot be loaded directly. Plan: reimplement each UDF as native Python (fast, typed, testable), verified against the simulator with the libraries installed. LazyMath is also Unlicense, so porting and redistribution are permitted; still record that check in `docs/decisions/` before the first port.
6. **Other apps and extensions (M5–M9).** The Pseudocode & Python app is the standalone Code view
   (M5, Should), alongside Nspire in the all-in-one shell; Nspire Python/Pseudocode page types,
   TI-Basic and library extensions follow as scoped (M5/M6). Polish and extras are M7. The existing
   multi-app shell gains a Casio ClassPad profile in M8 (Could) and possibly HP Prime in M9 (Would,
   behind a go/no-go). Details in section 3.2 and section 8.

## 6. Testing strategy ("every stage properly tested")

| Layer | What | Tooling |
|---|---|---|
| Unit | lexer, parser, printer round-trips, values, settings, each catalog function | pytest, Hypothesis |
| **Golden corpus** | Simulator-captured cases, replayed through the engine. This is the regression net | pytest parametrised from YAML |
| Device model | key sequence → expected screen text/state, menu navigation, mode switching | pytest, no GUI |
| Render snapshots | handheld/tablet/computer screens at fixed viewport; image diff with tolerance | Playwright + pixelmatch-style compare |
| E2E / PWA | built static site served locally: loads, types, evaluates, installs, works offline (service worker) | Playwright |
| Static | formatting, lint, strict types | Ruff, Ty |
| Coverage and traceability | At least 90% line and branch on `core/`, 80% on `device`, `doc`, `sheet`, `stats`, `graph`; `cassim.app` excluded (Playwright covers it). Every SRS requirement ID appears in a test or is listed as untested with a reason; `tools/` generates `docs/traceability.md`, checked in CI | pytest-cov, `tools/` |

Testing is staged to avoid rerunning unrelated checks during an edit loop:

1. **While editing:** run the affected test file or test case, plus direct neighbours for a
   changed shared API. Run Ruff on changed files and Ty when types or interfaces change.
2. **Before a PR:** run all affected unit/device/app tests and `tests/flows/`. Run the relevant
   Playwright files for UI, storage, document, publishing, PWA, worker or Pyodide changes; use the
   full browser suite for cross-cutting startup, shell, build or PWA work.
3. **CI:** keep the complete non-e2e suite, coverage floors, traceability and selected critical
   browser tests as the regression gate.

E2e tests share an app startup only when they also share a valid state journey. Fresh install,
failed-update, offline, root/sub-path, and touch contexts remain isolated because that isolation is
the condition under test. Shared feature journeys should solve natural student or VCE-style
problems, carrying data and results between pages rather than arranging synthetic control sequences.
`docs/testing/TESTING.md` maps source areas to the pre-PR commands.

**Corpus case format**

```yaml
- id: methods.solve.quadratic-001
  course: methods                # applies document-settings preset
  tags: [solve, tier1]
  steps:
    - in:  "f(x):=x^2-4"
      out: "Done"
    - in:  "solve(f(x)=0,x)"
      out: "x=-2 or x=2"
  provenance: {source: simulator, version: "<TI-Nspire CX CAS Teacher Software x.y>", captured: 2026-11-xx,
               evidence: shots/methods.solve.quadratic-001.png}
  status: pass                   # pass | xfail(reason) | hand-verified (not yet simulator-checked)
  compare: exact                 # exact text | canonical (symbolically equal) | numeric(tol)
```

- Capture is done with the simulator via the existing cas-solver workflow (new Problem per case, document settings first). Each case stores a screenshot as evidence and a human review flag.
- Seed it from the skill's known traps (`d(` unsupported, `1.` forcing approximate, `^` capturing exponents, `Ans` insertion, `solve|domain`, GM Approximate mode, `eff`/`nom`, `tvm*` argument order) plus VCE exam questions across Methods/Specialist/General, plus one or more cases per catalog entry.
- Failing-but-known cases are `xfail(strict=True)`: fixing one forces removing its marker, so progress ratchets and regressions fail CI.
- `compare: canonical` lets early milestones check maths correctness before output formatting matches TI exactly; tighten to `exact` per area over time.

## 7. Dev environment

- **uv** (Python 3.14 to match Pyodide 314), lockfile committed. **Ruff** for lint and format (rules: E, F, I, UP, B, SIM, ANN, PL, PT, RUF; `ANN` and strictness on `core/`). **Ty** for types, strict on the core packages; I have not verified Ty's current stability, so M0 checks it and keeps pyright as a fallback if SymPy/Flet stubs block us. **Git** with conventional commits, pre-commit (Ruff and Ty), GitHub Actions CI (lint, types, tests, web build, Playwright smoke), deploy to Cloudflare Pages (section 14).
- Flet MCP / Claude Code: helpful from M2 for GUI iteration, so I'd switch to Claude Code before M2 (and for the repo work in M0/M1 too).

## 8. Milestones

Sizes are rough effort (S ≈ days, M ≈ 1–2 weeks, L ≈ several weeks). Each milestone ends with its tests green and a tagged release.

**M0 — Foundations and de-risking (M)**
- Repo, uv, Ruff, Ty, pytest, pre-commit, CI. Decision log in `docs/decisions/`.
- Spike 1: SymPy + SciPy inside the Flet static build (cold-start time, download size, offline, does Python run in a worker, can we cancel?). Spike 2: `.tns` decodability. Spike 3: Flet canvas drawing speed (graph of 2000 points, pan/zoom). Spike 4: IndexedDB from Pyodide. Spike 5: `openpyxl` in Pyodide.
- Corpus tooling (schema, replay, capture checklist) and the first ~60 simulator-captured cases.
- Extract a complete command coverage matrix from the Reference Guide (draft index of ~290 entries already in `docs/reference_index_draft.txt`; extractor misses some, e.g. `solve`, so it needs refining).
- Exit: spikes written up with go/no-go; CI green on an empty package; corpus replays.
- **Status: done (2026-11-02).** Spikes 1–5 are written up in `docs/decisions/` (go, except `.tns`, which is a no-go for now), CI is green, and the corpus replays (179 cases, all passing).

**M1 — Text-based CAS with TI syntax (L)**
- 1a Lexer, parser, AST, printer (+ Hypothesis round-trips).
- 1b Values, settings (angle/mode/real-complex/digits), `Ans`, exact vs approximate rules, TI-style formatting and error messages.
- 1c Documents/Problems/scope: `Define`, `:=`, `→`, `DelVar`, `ClearAZ`, `Local`, constraint `|`, libraries namespace.
- 1d Catalog, in tiers. Tier 1 (VCE core): solve/cSolve/zeros, factor/expand/propFrac/completeSquare, derivative/integral/limit/nInt/deSolve, trig and exponentials, lists and matrices (det, inverse, rref), norm/binom/inv distributions, `tvm*`/`eff`/`nom`, regressions and OneVar. Tier 2: remainder of the Reference Guide. Tier 3: edge conversions and unusual templates.
- 1e `cassim` REPL and script runner, tab-completion from the catalog.
- Exit: Tier 1 corpus passes (canonical at minimum), strict types on `core/`, coverage matrix published.
- **Status: done (2026-11-02).** See `docs/decisions/0007` to `0011`.
- **Run 6 follow-ups (2026-11-25, `docs/testing/emulator-check6-run6-plan.md` 1.1). Done 2026-11-25** (`tests/unit/test_cas_run6.py`):
  1. Arbitrary constants (decision 0034 item 4): the Session holds one `c` and one `n` counter per Problem, restarting in a new Problem; new constants are numbered from them through a context variable in the adapter, and only the numbers an answer shows are used up (a recalled `ans` keeps its names). `solve(sin(x)=0,x)` is `x=n1·π` (evenly spaced families merge), `domain(tan(x),x)` is `x≠(2·n1-1)·π/2`, and `fMin`/`fMax` of a periodic function whose f'=0 is one family is `x=(4·n1-3)·π/4 and (-1)^n1>0` (otherwise the decimal search, as before). `deSolve` constants share the `c` counter (Reference Guide; to confirm in run 7, J1g).
  2. Display forms: `x=-(c1-3)/3` (free parameters factored); an arbitrary integer before π (`2·n1·π`); a shared exponential taken out of a derivative, `(1-x)·ⅇ^(-x)`, while different exponentials stay apart; a negated factor gives its sign to the product (`-y·(x-1)`, was `y·-(x-1)`).
  3. Exact definite integrals: logarithms of numbers are combined before the length test (limit 25 operations), so `∫₀² 1/(x³+x+2)dx` stays exact with `ln(9/2)/8` and the K7 integral stays a decimal. A logarithm of a fraction stays whole in any number (`ln(9/2)`, `ln(1/2)` is `-ln(2)`; to confirm in run 7, J1h).
  4. `tCollect` multiplies a sum of squares out when that ends shorter (`41-40·cos(3·t/2)`; a sum with no bare variable is led by a positive term); `expand(…,x)` divides a quotient out in `x`; `|x=value` is not put into the answer for the variable a solving command solves for.
  5. A single frequency of 0 is a Domain error.
  6. `invBinom` and `invBinomN` take a 4th argument 1 (Matrix Form) and give the matrix of the value before the answer and the answer with their cumulative probabilities; the dialogs' box pastes it.
  Still different: `expand` lists its terms in CASSim's order (the device puts the fraction first), and `expand` with no variable does not divide out (run 5 K6 #1, xfail); the order of the B5 integral's terms.

**M2 — GUI shell: keyboard, pages, settings (L)**

**Status (2026-11-12):** 2a to 2h, the 2d editor completion and the exam-style flows are merged. M2 is not closed, but nothing left can be done without a device or a decision.

Done since the 2026-11-08 list:
- The site was published on GitHub Pages and loaded (Simon); it moved to Cloudflare Pages on 2026-11-13 (section 14).
- Installed on Simon's phone; save and load work (Simon, 2026-11-12). It is slow there: see section 12, A6, for a later session.
- Stub pages (2026-11-12): Doc > Insert adds Graphs, Lists & Spreadsheet, Data & Statistics and Notes pages. At that point they had no model; Lists & Spreadsheet and Data & Statistics are now built in M3 slices 3b and 3d, and the initial function-plotting path for Graphs is in progress under M4. Notes remains a stub.
- Disclaimer (NFR-LEG-002): the About CASSim dialog (Doc > 8 About CASSim, and an About chip in Computer mode) holds the disclaimer, privacy, licence, third-party notices (NFR-LEG-003) and versions; no footer line, by choice (2026-11-08). The repo link is private until the repo is public.
- The documentation gaps of section 11 (2026-11-09).
- Emulator shortcut follow-up (2026-11-12, `docs/testing/emulator-shortcuts-results.md` S7 e to g, S5 b2, S8 a): ctrl+Z with nothing to undo on a fresh page undoes the page insert and ctrl+Y redoes it; the keypad has ctrl+Z and ctrl+Y (shift+esc is not redo); keypad ctrl+7 picks the first history row and ctrl+1 returns to the entry line; a second Delete on a highlighted template leaves its first slot's content, selected.
- Handheld splitter drag (2026-11-12): drag steps are coalesced into one redraw, and a redraw rebuilds only the part whose scale changed, with no autosave, toolbar or sidebar work (`App.resize_soon`). Tested headless only; not yet timed in a browser.

Still open, each waiting on something:
1. Runs on Safari (macOS and iOS) and a Chromebook, which are primary targets (NFR-PORT-001). No devices are available; only Chromium has been driven by the tests (`docs/testing/browsers.md`).
2. Typed-character capture on non-US keyboard layouts (2d, decision 0024). Needs such a keyboard.
3. Tablet mode (FR-DEV-003, Should) has no code yet.
4. The 2f/2g items still to check on the simulator (0022, 0023; `docs/testing/emulator-templates-results.md`). Run 6 confirmed Clear History and its undo, `ans` on a new page, Backspace against del after a template, and the history deletes by Backspace and del; the rest are in `docs/testing/simulator-todo.md`, section J.
5. A one-off review of FR-DEV-007: `app/state.py` imports `profiles.nspire` directly as its default profile, which is acceptable only if everything else comes through the `Profile` object.
6. Emulator check 3 (`docs/testing/emulator-history-results.md`, a partial run on 2026-11-10): fixed 2026-11-12 except the history layout, which Simon chose to keep (a thin rule between pairs, not grey banding). Built to match the emulator: undo and redo cross evaluations and deletes (a store is not undone) and, once a page has nothing left to undo, the page insert; Del or Backspace on an empty entry line does nothing; Enter on an empty line runs the last entry again, with or without `Ans`; `ans` in a history line is shown as the value it had (14 digits, bracketed unless a plain number), while a saved file and the repeat keep `ans`; `Ans` follows the history after an undo or delete; Home with a history line picked goes to the first line; an error leaves its entry in the history with the message as a quoted string. Not run on the emulator: the mouse (H3), keypad ctrl and shift layers, most of H7 and H8, scrolling and spacing. Not copied: the long-input ▸ cut-off (CASSim wraps), the redo that re-shows an error dialog.

- Keys to carry over from the handheld: **Ctrl+Enter** gives the answer as a decimal, the same as wrapping the entry in `approx(...)`. The engine already has it as `Session.eval(line, approximate=True)`; the REPL uses `:approx` and Alt+Enter (see `docs/user/repl.md`).
- **Guard for the profile work in M8 (no extra scope):** framework code in `device/` and `cassim.app` holds no Nspire-specific constants. Key layers, menu trees, page types, skin and theme values come from data or registries that the Nspire profile supplies, and page types are registered, not hard-coded in a switch. This costs almost nothing now and avoids a rewrite later (section 3.2; SRS FR-DEV-007).
- Decisions and the four spikes that precede 2b to 2e are in `docs/decisions/0013-m2-planning.md` (2D rendering, MathLive, GitHub Pages publish, cancel and restore). The skin is driven by a config file; the display mode is remembered, with a media query on a first visit; Document Settings gain `case` and `ascii`.
- 2a Device model (started 2026-11-06: `device/keys.py`, `device/calculator.py` with entry, history, recall, undo and redo, and the Nspire keymaps in `profiles/nspire.py` are done; the `device/document.py` with Problems, Pages, the page sorter order and document settings is done; the menu tree and screen buffer are next): key layers, menu tree from data, the 2D template input editor (`device/editor.py`: fractions, powers, roots done; matrices, lists, copy and paste to do; shift-arrow and ctrl+A selection done), screen buffer; headless key-sequence tests.
- 2b Flet app (started 2026-11-06): `cassim.app` has the state, browser key mapping, and Handheld and Computer views with the on-screen keypad, running in-process (`flet run src/cassim/app/main.py`); the engine worker, Tablet mode and the first-visit width rule are still to do.
- 2c Documents, Problems, Pages (add/delete/reorder, page sorter), variable list, document/system settings dialogs, undo/redo. **Started 2026-11-07:** page add/delete/next/previous (keys and toolbar), clickable page list, variable list, Document Settings dialog are done; the Doc and Menu menus from data (`device/menu.py`, trees in `profiles/nspire.py`; F4 and F2 on a computer, doc and menu keys on the keypad) are done too; page reorder (sidebar buttons and Doc > Page) and document-level undo/redo of page changes are done; the Page Sorter dialog (tiles, click to go, move, delete, undo) and System Settings (start view, maths size; kept for the session only until storage in 2e) are done, so **2c is complete**; the Menu tree is a starter set (the full catalog and the Doc layout need checking on the simulator).
- 2d Editor completion: matrix and list templates, selection, copy and paste, history recall as templates (parse an old entry back into the tree), click-to-place the cursor (done, see below), typed-character capture on other keyboard layouts (needs a Dart key handler or a hidden text field; see 0015). **Known problems (Simon, 2026-11-06):** the selection box still leaves a gap at the cursor; selection does not handle fractions gracefully (a fraction is one unit, shift-arrows cannot select inside its slots or across a slot boundary, and the numerator and denominator rows do not highlight together). **Done 2026-11-07:** click-to-place (2026-11-07, decision 0019): the entry line is now drawn from Flet controls with a hit zone per character, slot and template, so a click places the cursor in plain rows, fraction slots, exponents, radicands and matrix cells, and shift+click extends the selection (`Editor.place`); selection gap fixed (cursor drawn inside the highlight); selection leaving a slot takes the whole template and carries on; history recall keeps templates (entries store their nodes); matrix grid template (Menu > Matrix & Vector, Tab by cell, Up/Down by row, `[a,b;c,d]` text); click a history row to pick it and click again to recall it. **Done 2026-11-08 (decision 0024):** a list template, selecting (and copying, cutting, deleting) matrix rows and columns, shift-extend by touch (long press, or the keypad shift key then a tap) and a stretching radical. **Caps Lock done 2026-11-08** (the key and the keypad's ctrl+shift, shown as CAPS; 0024). **Still to do (later, needs a non-US keyboard to check):** typed-character capture on other keyboard layouts, which would also fix a lock that starts on; see 0024 for what was tried and how to pick it up.
- 2e Storage and files: IndexedDB persistence, autosave, upload/download `.cassim.json`, PWA install and offline, fullscreen handheld on phones. **Started 2026-11-07:** done: `device/serialize.py` (versioned `.cassim.json`, entries replayed on load so results are recomputed, templates kept), autosave and recovery after reload (Flet `SharedPreferences`, which is browser localStorage, not IndexedDB; IndexedDB is now the main autosave store from M3 slice 3.0, with named Code files added in M5), Doc > File > New, Open file and Save to file. **To do:** Safari and Chromebook runs (the GitHub Pages site is published and loads). **Done 2026-11-07:** Handheld fills a phone (`app/layout.py`: the screen, text and keys are drawn at a scale that fits the window, keypad under the screen in portrait and beside it in landscape; a first visit starts in Handheld when the window's short side is under 600 px; a compact toolbar with a Tools dialog, an Install button (the page keeps the browser's install prompt and the app, which runs in a worker with no DOM, asks for it over a BroadcastChannel: `app/web.py` `Bridge`) and a Fullscreen button; the Google fallback fonts Flutter asks for are vendored, and an e2e test fails on any other font 404; the manifest asks for fullscreen); the installable offline site (`python -m tools.publish`: manifest, generated icons, versioned precaching service worker with an update bar, loading screen, vendored Pyodide packages, wheels and symbols font; `tests/e2e/test_pwa.py` boots it under `/CASSim/` and reloads it offline) and the engine worker: `device/engine.py` (`EngineCore`, `RemoteSession` with a journal and a variable snapshot, `LocalEngine`), `device/runner.py` (`Runner`: queued entries, sync of settings, Cancel and rebuild, async document load), `app/web.py` (a second Pyodide worker with a spare). Esc cancels a run in about 0.2 s and the engine is back in about 2 s with Problems and variables intact; `CASSIM_ENGINE=remote` runs the same path on the desktop. Also URL-fragment share links (`device/share.py`, Doc > File > Copy share link; the page uses the hash route strategy so the fragment arrives as `page.route`, and a link asks before it replaces the document) and System Settings kept in browser storage.
- 2f Keypad and menus like the Nspire (2026-11-07, decision 0022): the CX II key layout and ctrl/shift labels in CASSim's own drawing; the Calculator Menu with the handheld's numbering; trig, templates, catalog, variables, relations, punctuation and symbol menus; clickable cascading menus; syntax hints; data-driven dialogs for the multi-argument commands (distributions, stats, regressions, Finance Solver, Derivative at a Point, Create Matrix, systems, polynomial roots); an optional keypad beside the screen in Computer mode; an ABC or QWERTY letter block (System Settings). Checked against the Teacher Software on 2026-11-08 (Cowork run; greyed placeholders keep every device number).
- 2g More 2D templates (2026-11-08, decision 0023): nth root, log with base, absolute value, piecewise, systems, d/dx and d²/dx², definite and indefinite integrals, Σ, Π, limit; wired to the keys (ctrl+^, ctrl+10ˣ, shift+−, shift++), the templates grid, the Calculus menu and the dialogs; engine `root(` and `piecewise(`. Checked against the Teacher Software (Cowork run 2, 2026-11-08); also `linSolve(`, `invBinomN(`, the Differential Equation Solver dialog and a Non-real result error for even roots.
- 2h Sizing (PR 37, 2026-11-08): menus show up to 10 rows with no 'more' rows, Handheld draws the keypad at 0.8 of the screen scale with a draggable splitter, and a Zoom setting in System Settings; both saved with the system settings.
- Exit: build the static site, install on phone, complete the golden "exam-style" scripted flows via device-model tests and Playwright.
  - **Flows done 2026-11-08 (decision 0025):** `corpus/flows/exam.yaml` holds 12 exam-style flows (Methods, Specialist, General, handheld keypad), played key by key by `tools/flows.py` through `AppState` (`tests/flows/`) and, for the 5 marked `browser`, typed into the built site by Playwright (`tests/e2e/test_flows_browser.py`, all pass). Installed on Simon's phone, with save and load, on 2026-11-12.

**M2x — Device interface and bundles (M), before M3 (decided 2026-11-13). Done 2026-11-13 (PRs 83 to 87 and the bundles PR).** Section 15.4 steps 1 to 3: the ADR on the device interface and bundle format; the Nspire moved to `devices/nspire/` behind it (this is 8a, brought forward, and it carries decision 0031's A4 move of the document model); a bundle-aware `tools.publish` with the `tin` bundle and its site. No behaviour changes. Exit: every corpus case replays unchanged, the e2e suite passes, coverage floors hold, and download size is reported per bundle.

**M3 — Data pages: Lists & Spreadsheet, Data & Statistics, Finance (L)**

**Status (2026-11-18): Mostly met.** Slices 3a to 3b are done; 3c, 3d, and 3e are merged in PRs #149, #152, and #154, with the Statistics UI follow-up in #156. The combined Python suite previously passed 6,470 tests, configured coverage floors and required browser checks. General Maths spreadsheet and data-page workflows are in `corpus/flows/data-pages.yaml`; page-switch and recalculation measurements are recorded in decision 0031. FR-SHEET-004 to 007 now have focused navigation, range-selection and heading-selection tests; browser checks cover mouse drag, Shift+click and row/column headings. The shared spreadsheet editor is implemented in this work. The 3d/3e defaults and save/reload behavior are not TI-simulator verified; they are listed for the next Cowork capture. Automatic and Manual Data Capture remain deferred. The touch-first rule and shared-data design (decision 0031) still apply.

**Editor follow-up:** physical and on-screen arrow holds now step once, repeat slowly, then
accelerate in Calculator and spreadsheet editing and cell navigation. The spreadsheet formula bar
uses the Calculator's structured maths editor and renderer, retaining reference pointing and cell
navigation. Apply the same editor to Graphs and verify repeat when Graphs is integrated.

- Spikes A and B (done 2026-11-13, decision 0031): a switch rebuilds controls from kept data (about 19 ms on a desktop; keeping controls alive is slower); the grid is one canvas text per column; replies must be deltas and sheet stores must not format the whole list. Not yet timed on a phone.
- 3.0 Foundations, shared with M4: SDD-07; section 12 rows A1 (typed ops) and A5 (A4, documents and the page-model boundary in `doc/`, was done in M2x step 2); variable revisions, the delta reply and the UI-side store (FR-DOC-008); the per-page scene cache and `tools/switchtime.py` (NFR-PERF-006); the shared scene type (FR-GRAPH-006); two-pane split pages (FR-DOC-009); the warning triangle (FR-CALC-007); debounced autosave in IndexedDB; schema bump with a migration. **Done 2026-11-13 (PRs 89 to 93 and the SDD-07 PR):** typed ops and replies, revisions, delta replies and the store; the scene type and its canvas; the IndexedDB autosave; `tools/switchtime.py` (about 125 ms a switch on the laptop, decision 0031); the warning triangle; SDD-07. **Done in 3e:** split pages and schema-3 migration. The per-page scene cache comes with the sheet page in 3b, the first page with a scene.
- 3a Sheet engine, headless (`sheet/`): cells, columns linked to list variables, formula columns, `a[]`, ranges, `$` references, the dependency graph and recalculation, indexed assignment (`xs[2]:=20`, done 2026-11-13: replaces, appends one past the end, else "Dimension error"), voids, `#UNDEF`, the Data Loss and Conflict Detected cases, sort, fill, insert and delete. Replays the `app_spreadsheet`, `app_sheet_sort` and `app_sheet_fill` corpus cases. **Progress 2026-11-13:** indexed store (PR 98), empty elements `_` in core (PR 99), and `sheet/refs.py` and `sheet/sheet.py`: cells, entries, formulas, references, linked and formula columns, `sync` with the Problem's variables, the dependency graph, `#UNDEF`, `#ERR`, the refused-edit dialogs and Conflict Detected (PR 100). Then (PRs 101, 102, 103 and 105; **3a done 2026-11-14**): Fill, Sort, Insert and Delete (`sheet/actions.py`), `seqgen` and Generate Sequence, the variable locks ("variable in use", formula columns read-only), and the engine's `sheet` op (`device/sheets.py`), through which the formula-column, seq-column, Generate Sequence, Sort and Fill corpus cases replay (`tests/device/test_engine_sheet.py`). **Left for 3b:** copy and paste with Data Loss (a UI clipboard), Move Column, the status-bar text of the Fill case, and journalling a sheet as its contents (`restore`) rather than as its edits.
- 3b Sheet page: canvas grid, edit bar, keys, selection, clipboard, Go To, resize, the Menu and context menus from checks 4 to 6. **Part 1 (headless) done 2026-11-14:** the page model `devices/nspire/pages/spreadsheet.py` (cursor, block, row and column selection, editing with a caret, Enter moving down, Fill, Move Column and Resize modes, copy, cut and paste with formulas moved and Data Loss for rows, Del, page undo falling through to the document's, Go To, the Menu and four context menus with check 6's numbering, var > Link To on a name cell, wizards for Sort, Generate Sequence and Conflict Detected); `device/sheet_link.py` (one channel per Problem, local or through the Runner; a deleted page drops its sheet); replies carry the definitions' edits, so the page saves without the engine; the journal keeps one `restore` per sheet; a loaded sheet rebuilds after its Problem's other pages. **Part 2 done 2026-11-14:** the grid as a scene (`devices/nspire/sheet_scene.py`: grid, heads, cells and cursor layers, two labels a column, long text cut with `...`), drawn by `devices/nspire/ui/sheet_view.py`, which rebuilds only the layers that changed; touch routes (tap, double tap to edit, long press or right-click for the context menu, a finger drag scrolls, a mouse drag selects, the wheel scrolls, a row number selects its row); the bar with the cell name and its content; dialogs with OK and Cancel; the sheet in `tools/switchtime.py` (66 ms a switch on the laptop, decision 0031); `tests/e2e/test_sheet_browser.py`. **3b is done.**
  Formula names ask Column or Variable only for single-letter linked names; longer names are variables. Cell-address conflicts still ask Cell or Variable.
- 3c Statistics from the sheet: Stat Calculations, Distributions, Confidence Intervals and Stat Tests. The core now has mpmath-backed interval and test commands; spreadsheet inference writes live label/value columns. The 1-Prop z Test includes the simulator-observed result-column default (`a[]`) and Draw: Shade P Value, which renders a split sheet/normal-plot view. The existing Stat Calculations behavior remains live, including `stat.RegEqn`; distributions paste formulas into the selected cell. The exact defaults and output layouts for the other inference dialogs, and Shade behavior outside the observed two-sided 1-Prop z Test, remain for simulator follow-up.
- 3d Data & Statistics page (done; PR #152 merged): live Problem lists, numeric dot/box/histogram/normal-probability/scatter/XY plots, General Maths categorical dot/bar/pie charts, summary and split categories, regression/residual overlays, Plot Function/Value, histogram settings, windows and Zoom–Data. The UI follow-up removes placeholder labeling and the top toolbar, places clickable X/Y selectors on the axes (including none), moves plot selection into Menu, enlarges marks, supports point selection/context menus plus drag-editing numeric scatter and dot data, and keeps the page sorter accessible from Statistics. Uses backend-neutral scenes and persists only view settings. Emulator checks for drag behavior and some visualization context-menu targets remain in `docs/testing/simulator-todo.md` (G1–G2).
- 3e Quick Graph for a named list; Summary Plot with Split Page or New Page; CSV and basic XLSX import/export, with formulas preserved in XLSX and displayed values in CSV (done; PR #154 merged). openpyxl and et-xmlfile are included in the web app archive. Python CI checks pass (6,470 passed, 84 skipped, 59 deselected, 27 xfailed), coverage floors pass, and the required browser checks are green. Quick Graph/Summary Plot defaults and save/reload behavior remain for Cowork simulator investigation; implementation choices are documented in SDD-07.
- Finance: the Finance Solver was built in 2f; beginning/end payment and `amortTbl` examples were captured in `corpus/seed/037_check6_run4.yaml` (D19; transcription awaits human review).
- **Run 6 follow-ups (2026-11-25, `docs/testing/emulator-check6-run6-plan.md` 1.3). Done 2026-11-25** (items 1 to 5; item 6 is M4, Simon's note 4):
  1. Stats input for 2-Sample z Test, 2-Sample t Test and 2-Sample t Interval, in the device's field order, in the sheet and the Calculator dialogs; the engine takes their summary forms. Esc in a fields dialog goes back to the Data Input Method box (`Wizard.back`; the Flet dismiss path is not run in a browser). Fixed on the way: `tTest_2Samp` reads Hypoth before Pooled, and `LinRegtTest` takes Hypoth as its 4th argument (`X,Y[,Freq[,Hypoth]]`; a 5th is ignored), as the Reference Guide has them.
  2. A dragged Data & Statistics point stores three decimal places (the rule for other windows is run 7, J3a).
  3. Result rows as the device shows them: every test starts with Alternate Hyp; intervals list CLower, CUpper, the estimate, ME; 2-Sample t Interval adds x̄1, x̄2, sx1, sx2, n1, n2; Linear Reg t Test has its 13 rows (RegEqn, r², r, Resid). The run 6 values are tests. TI's t distribution differs from SciPy's in the 8th figure for the 2-Sample t Interval bounds (about 2ᴇ-8; CASSim agrees with SciPy). The 2-Sample z and t Test row orders are by analogy, not captured.
  4. Fill and Insert Cell already matched and are tested; Insert Cell is now grey in a results column, and Insert Row leaves inference result labels in place (Delete Row not captured).
  5. The Calculator Statistics menus match the run 6 lists (`χ² 2-way Test` spelt as on the device) and are pinned by a test. The sheet's Stat Calculations has no G Correlation Matrix; the device's sheet list was not captured past its top.
- Greyed, not built: the movable line, Data Capture, Multiple Regression, ANOVA 2-Way and Custom Split. A page holds up to four panes (decision 0034 item 2): Quick Graph, Summary Plot, Shade P Value and Shade area add one, going from halves to three panes to 2×2.
- Exit: General Maths spreadsheet and live-data workflows run headlessly and in the browser; timings are reported in decision 0031. These flows are hand-worked examples, not simulator captures or a claim that every cas-solver workflow has been reproduced.

**M4 — Graphs and Tables (L)**

**Status (2026-11-18):** in progress. The headless function sampler and Trace/Analyze numerical algorithms are implemented independently of M3. The initial integrated Graphs page supports shared Problem functions, worker-side compilation, structured function entry, plotting, visibility, a standard window, zoom buttons, save/load, pointer panning, pinch zoom and wheel zoom anchored at the pointer. Gesture-rate tuning and performance checks, graph attributes and context menus, split Table, sliders and Notes remain. The M3 page-model and split-page foundations are available. Remaining Cowork captures are listed in `docs/testing/emulator-check6-run4-remaining.md`. Spikes C and D are done (decision 0031): curves are sampled in the UI worker at one point a pixel column and redrawn inside each pan, pinch or wheel event (6 to 7 ms a frame on a desktop); fills use fewer points; relations use marching squares in pure Python (6 to 8 ms at 4 px cells). This is the next user-facing implementation milestone.

- 4a Sampler and scene, headless (`graph/`): **initial function path implemented:** checked math-source compilation, window transforms, automatic tick values, adaptive function sampling, and curve layers in the shared scene. **Done 2026-11-21:** scene tests for the D12/D13 breaks and ends (no joins across `1/x`, `tan`, `1/(x-1)^2`, `abs(x)/x`, `floor`; no end markers for `ln`, `sqrt`, `sqrt(4-x^2)`, restrictions), and a restriction typed with `|` is kept as a one-piece piecewise; `graph/zoom.py` holds the Window / Zoom windows. Full scene snapshots remain.
- 4b Graphs page: **initial function path implemented:** `f1` to `f99` function entry uses the Calculator's structured editor and renderer; View controls axes, end values and dot/lined grid, with per-page persistence (simulator scope pending). The Graphs appearance pass (2026-11-19) shows one active expression row at a time with a visibility checkbox, the shared editor, Up/Down slot navigation and a CASSim-styled function-history menu; plotted functions carry curve-coloured labels. Function definitions use the shared Problem variables and are compiled in the engine worker for browser execution. Pointer pan, pinch zoom and wheel zoom remain implemented (kept as an extension, decision 0034). **Done 2026-11-21 (C1, C2):** function colours in the device's order as theme tokens, keyed by fN so a colour holds across a Problem's pages, with the `fN` part of a label bold; Menu > 4 Window / Zoom with Window Settings (full digits, `2·π`, checked) and every zoom at the recorded windows; Box, In and Out as tools with their prompts (tap or Enter at an arrow-moved pointer). Zoom – Fit with a scatter plot waits for run 6 (R6-D3), and Zoom – Data has no data plots to use until 4d. Remaining: gesture-rate tuning and device performance checks, graph attributes and context-menu hit regions with `app/context_menu.py`, including in split panes, so physical Ctrl+right-click keeps the browser menu.
- 4c Trace and Analyze Graph: **headless numerical algorithms implemented** for zero, minimum, maximum, intersection, inflection, dy/dx, integral with typed bounds, and bounded area. **Done 2026-11-21:** Menu > 5 Trace (Graph Trace, Trace All, the Trace Step dialog; readout `f2: (4.71, -2)` in Float 3 and the graph's colour; edge panning; Up/Down between graphs; typed x; taps) and Menu > 6 Analyze Graph (graph?, lower bound?, upper bound?, position?; results kept on the page as graphs and bounds, recomputed when a function changes, saved with the page). Not built: Path Plot, Geometry Trace, Analyze Conics, and the corpus replay. The automatic trace step is 1% of the window width (decision 0034); Up going to the previous graph is a choice from incomplete evidence.
- 4d Other entry types, in this order: scatter plot, parametric, relations and conics (marching squares, spike D; drop false lines at jumps), polar, sequence, differential equations.
- 4e Table (split page, ctrl+T from the graph and from the sheet) and sliders.
- 4f Notes page, text only (FR-NOTE-001); maths boxes are a later Could.
- **Simon's notes (2026-11-22). Done 2026-11-25** (the paused `feature/m4-graphs-menus` branch had been merged; nothing to check against):
  1. No `Ans` in a graph entry line: done by the entry-session work (2026-11-25): each entry line is a `device/entry_session.py` `EntrySession` and only the Calculator's turns the `Ans` rule on; a test checks a graph line. Whether `ans` is offered in the graph line's menus is still to check.
  2. Tab on a Graphs page opens the entry line on the first empty `fN`, as ctrl+G does; inside a template it moves between the slots (R6-A9). Tab is captured as a key; that the browser keeps focus is not tested in a browser.
  3. No crash for `sqrt(x)` (page-level tests for `sqrt(x)`, `ln(x)`, `1/sqrt(4-x^2)`, `x^(1/3)`).
  4. Wheel, two-finger scroll and pinch zoom on Data & Statistics plots about the pointer (`stats/plots.py` `zoomed_window`): scatter and xy-line plots and histograms zoom both axes, dot and box plots along x; category charts and normal probability plots do not zoom. The plot takes scale events so one finger still drags a point. The device does not zoom (run 6 S1); this is decision 0034 item 1. Trackpad scroll on a Chromebook and a Mac is still to try.
- **Run 6 follow-ups (2026-11-25, `docs/testing/emulator-check6-run6-plan.md` 1.2):**
  1. Done: the zoom and analysis pointers move 1/160 of the plot a press.
  2. Done: Minimum and Maximum reached at a bound mark the bound's point.
  3. Done: the no-result message is an Error dialog over the graph (drawn in the scene; Enter, Esc or a tap closes it, other keys wait).
  4. Done: a restriction is labelled as a one-row brace and a piecewise template's empty last condition reads `Else` (`label_latex` in `pages/graphs.py`).
  5. Done: `x^(1/3)` is drawn as the real cube root for x<0 (the graph compiler emits a real odd root); page-level domain tests.
  6. Done (Handheld rule): a drag starting on an axis, away from the origin, rescales both axes about the origin (`axis_grabbed`, `axis_drag_factor`). The Computer view is run 7, J2a.
  7. Done: Enter during a trace leaves a kept point (`AnalysisObject` kind `point`) that stays after Esc and follows the function.
  8. To do with 4d: Zoom – Fit with scatter entries (alone, the data ranges padded 10%; with functions, probably the union of the window and the data range padded 10%, run 7 J2d).
  9. Blocked: `nInt` graphs are not supported yet ("unsupported graph expression"), so there is nothing to draw coarse to fine. When numeric integrals can be graphed, draw sparse points first, then fill in (about 5 to 6 s on the device), and let the page be left while they draw.
  10. To do with 4e and 4d: ctrl+T (Table Start 0, step 1, Independent and Dependent Auto; rows scroll above the start; ctrl+T again closes it with the window unchanged); entry defaults (Parametric and Polar 0 to 6.28 step 0.13; Sequence n 1 to 99 step 1 with Initial Terms; Diff Eq `y1'=` with `(x0,y10)`).
  11. Waiting: Trace Up and Down (run 5 and run 6 disagree; run 7, J2c).
- Greyed, not built: Plane Geometry, 3D Graphing and the Geometry menu.
- Exit: scene snapshot tests green; pan and zoom timed on a mid-range phone and a Chromebook and reported (FR-GRAPH-007).

**M5 — Python and pseudocode: Code view, translation and trace tables (L), Should.** Starts after M4 and before M6. The Code view ships as the `pseudocode` device (section 15).
- 5a `runtime/`: `Interpreter` interface; Python runtime in its own worker with cancel (within 1 s), streamed output and `input()`. Spike first on keeping user code off the network and the host page; until then programs are translated and interpreted, not run as Python (decision 0040).
- 5b Pseudocode language: syntax-file-driven tokenizer, parser and tree interpreter for the dialect (`docs/pseudocode/dialect.md`, `syntax-default.yaml`); numeric tower (integer, rational, real, complex) and strings; Approx / Auto / Exact number modes and Radian / Degree; 6-digit display; `input` type inference; lists (1-based by default) and seeded random numbers (Should); function-valued parameters; pseudocode-level diagnostics; step limit. Replay `corpus/pseudocode/seed.yaml` (58 cases) from the start. **Built 2026-11-07 (PR #25; decisions 0020, 0021):** tokenizer, parser, interpreter, vertical and horizontal trace tables, the table-driven syntax file with presets and validation (FR-SYN-001 to 004, 008, 009), and the printer (FR-SYN-005, 007); 58 golden programs replay green. **Updated 2026-11-19:** the supported Python/Pseudocode program-tree converters, responsive standalone Code workspace, settings, typing aid, Run/Step/Start/End trace controls and trace-item selection are built. Direct CPython worker execution, named Code storage, the syntax/file editing features and Nspire page types remain.
- 5c Translation: the shared program tree; pseudocode to Python and Python (subset) to pseudocode; differential and round-trip tests.
- 5d Trace engine and tables: event recording, forwards/backwards cursor, vertical and horizontal views, Auto layout, step-limit handling. The reference bisection example must reproduce the author's two tables.
- 5e **Standalone slice integrated (2026-11-19):** the `pseudocode` device is mounted from the
  all-in-one Home chooser and has an editor, pseudocode run/step/trace controls, Python/Pseudocode
  source selection and file import/export. The Syntax editor, Regularise/Convert controls, full
  named-file IndexedDB UI, Python execution, translation and Nspire page integration remain in
  scope (FR-RUN, FR-EDT and FR-SYN).
- 5f Page types: Python and Pseudocode pages in the Nspire profile (the bar starts from the document settings; pages are self-contained, and the variable bridge is deferred past M5), document schema bump with a migration (FR-DOC-004).
- Exit: every golden program passes in both languages and the two agree; trace tables match the reference tables; cancel and trust-prompt E2E pass; the installed PWA works offline.

**M6 — Programming and extensions (L), Could.**
- TI-Basic interpreter + Program Editor; library mechanism; native ports of mm_/sm_/gm_ libraries (licence check first), each verified on the simulator.
- Reuse M5's program-tree and runtime work where useful; the Python and Pseudocode pages remain part of M5.

**M7 — Polish and extras (M).**
- Accessibility follow-through (`docs/accessibility.md`); localisation-ready strings; exam-restriction mode (Could-have, teacher-configurable); theme config export/import; user docs; public deployment. `.tns` is dropped from scope for now.

**M8 — Device profiles and Casio ClassPad (L), Could.**
- 8a (brought forward to M2x, before M3; section 15.4) ADR on the profile boundary, then move the Nspire onto the profile interface. Gate: every Nspire corpus case replays unchanged, coverage targets (NFR-MAINT-004) still met, render snapshots unchanged. No other 8x item starts until this is green.
- 8b **Shell switcher complete for built devices.** Home and the Nspire/Pseudocode device boundary are live. Complete and verify per-profile storage namespaces (SRS Q20), then the lazy per-device asset/offline plan in section 15.3.
- 8c Decide the model and oracle (SRS Q17), record the emulator's licence terms in `docs/decisions/`, and capture the first ~60 corpus cases in `corpus/classpad/` before writing code, as M0 did for the Nspire. Nothing is assumed to behave like the Nspire.
- 8d Dialect, settings presets and display conventions from the corpus; Tier 1 catalogue (VCE core) first, tiers as in M1d.
- 8e Apps/pages as the oracle shows them (calculation, graph and table, statistics, spreadsheet), reusing the M3/M4 engines through the profile. Geometry excluded.
- 8f Device model, keymap and skin in our own artwork; decide touch-first vs key-driven interaction (SRS Q19).
- 8g Python and Pseudocode pages if SRS Q22 says yes (the M5 runtime is reused).
- Exit: Nspire corpus unchanged; Tier 1 ClassPad corpus passes (canonical); scripted exam-style flows for Methods and Specialist; profile switching E2E.

**M9 — HP Prime profile (M–L), Would.** Not planned; kept so the option stays visible.
- 9a Go/no-go review after M8: oracle availability and terms (SRS Q18), M8's actual effort, whether anyone needs it. A "no" costs nothing elsewhere in the plan.
- 9b If go: the same recipe as M8 (corpus first, Tier 1 catalogue, then the apps the oracle shows; as I understand it, Home and CAS views plus an app set). The HP PPL programming language, if wanted, is a separate dialect on the runtime interface.
- Exit: as M8.

## 9. Risks and decisions

Decisions (from the SRS review, 2026-11-02; do not re-litigate):

1. **Fidelity:** canonical equality first, exact text per area as the corpus grows; "close enough not to confuse" is the bar.
2. **Performance and size:** no hard budgets. Cold start (baseline 15 s vendored, 35 s CDN) and download (22 MB CDN, 95 MB vendored) are measured and reported with a progress screen. Tier 1 operations aim for 1 s or less after import; SciPy first use 5 s or less and shown as busy; Cancel within 1 s.
3. **Licensing:** CASSim is MIT (decision 0042); LazyMath is Unlicense. TI marks, artwork and ROM are never shipped; reference screenshots (`docs/design/reference/<device>/`) and evidence screenshots (`corpus/shots/`, `docs/testing/*-shots/`) are kept in the separate evidence repository (decision 0039), never in the build. IP boundary and clean-room rule per decision 0028: layout, menus, names and syntax may match the device; artwork, prose and code may not, and behaviour is learned by observation only.
4. **Appropriate use:** teaching, practice and demonstration. Not an approved exam calculator, and the UI says so.
5. **Python 3.14, no Geometry page, no `.tns` for now.** If `.tns` is ever built, it is File > Import/Export only (FR-DOC-006).
6. **Sequencing and priorities (updated 2026-11-19):** CASSim is now an all-in-one shell with the Nspire and Pseudocode & Python app choices. Finish the Nspire page set through M4 and the Code runtime/UI as Should work (M5), then TI-Basic and library extensions as Could (M6), and polish as M7. The multi-app boundary and chooser are accepted and built; Casio ClassPad follows as a device in that shell (M8), and HP Prime is Would behind a go/no-go review (M9). The M2 guard, M2x profile boundary and M5 sandbox spike remain accepted.
7. **Pseudocode choices (2026-11-02):** the TI "Auto" rule is a third number mode; printed reals default to 6 significant digits (Mathematica style); `input` infers number versus string; the settings bar is Number mode and Angle plus a "…" menu; the syntax is user-configurable through a stored syntax file; VCAA cases stay in the repo with attribution (decision 0012, revised 2026-11-12).

Open risks:

1. **Flet static limits** (threading, cancellation, canvas speed): M0 spikes were go and the engine worker, cancel and offline site are built; fallback is a thin custom web front-end over the same engine. The 2D editor is CASSim's own template editor (decisions 0015, 0018), so MathLive and MathQuill are dropped, and Dart code in the static build is verified.
2. **Simulator capture effort:** driving the simulator by screenshot is slow; budget it per milestone and prioritise Tier 1 cases.
3. **Offline end to end:** wheels must be vendored and `index.html` patched after `flet publish` (decision 0002); verify with Playwright.
4. **Accessibility on a canvas renderer:** screen-reader support may not be achievable in Flet; tracked in `docs/accessibility.md`.
5. **Oracle access for ClassPad and Prime.** Unverified: that the manufacturers' emulator software is available to you and permits corpus capture. Screenshot-driven capture was the bottleneck for the Nspire and will be again; hence Tier 1 first and the Prime go/no-go.
6. **Maintenance load multiplies.** Each profile is its own corpus, catalogue and skin. Mitigation: shared engines, a strict profile boundary, Tier 1 per profile before widening.
7. **Refactor regression.** Moving the Nspire onto profiles could change its behaviour. Mitigation: the corpus gate in 8a.
8. **Sandbox for user code.** Pyodide is CPython with a `js` bridge, so "no network, no host access" needs a spike (5a) before it is claimed. Until it passes, no user code runs as Python: Run and the Console go through CASSim's own interpreter, which is the control (decision 0040, 2026-11-27).
9. **Touch-first ClassPad.** The device model is key-sequence based; a stylus-driven device may need a different interaction layer (SRS Q19).
10. **Trademarks.** Casio and HP marks, artwork and firmware are treated exactly as TI's (SRS NFR-LEG-005).
11. **Two interpreters must agree.** Tracing and pseudocode use our tree interpreter while Python runs on CPython. Mitigation: differential tests on every golden program and on generated programs, numeric comparison for reals, and the number and angle semantics defined once, in the dialect spec.
12. **VCAA material.** Several pseudocode corpus cases come from VCAA exams (`third_party: true`, attributed in `source`). They hold the algorithm listings and CASSim's own answers, not VCAA's question prose, and stay in the public repository (decision 0012, update 2026-11-12; SRS NFR-LEG-007). Remove any case VCAA objects to.
13. **Configurable grammar.** A user-editable syntax file can make the grammar ambiguous or break saved programs. Mitigation: validation (FR-SYN-004), data-only files, fall-back to the default, and property tests that restyle and re-parse every golden program under every preset (FR-SYN-007).
14. **Documentation and traceability debt.** Largely paid on 2026-11-09 (section 11). Traceability is generated and checked in CI; 108 of 195 requirements are not cited by any test, each with a reason in `docs/traceability-reasons.yaml`, and the list shrinks as tests cite IDs. The SDDs for the built areas (02, 04, 05, 07, 10, 14) exist; the others wait for their areas.
15. **Browser coverage.** All e2e runs use Chromium; Simon has loaded the GitHub Pages site and installed it on his phone; the Cloudflare site passed a headless smoke test with an offline reload. Safari and Chromebook are primary targets and are untested because no devices are available; Flutter canvas, service worker and fullscreen behave differently there. Run them as soon as a device can be borrowed, not at M7.
16. **Branch and worktree hygiene.** Several chats work in parallel. A leftover folder (`worktrees/m2f-menus`) outlived its merged branch and looked like a live worktree. Use `git worktree list` and remove finished ones. (Checked 2026-11-12: no stale worktrees or branches; `m7-batch3` was merged as PR 44.)

## 10. Design documents

The SDD set (`docs/design/SDD-00` to `SDD-14`: overview, engine, worker and cancel, display and format, device model, Flet UI, document and storage, data pages, graphing, programming and Python, PWA and build, test strategy, device profiles, Python and pseudocode runtime, CASSim Scientific) is listed in SRS appendix A, with what stands in for each one not yet written. **SDD-02, 04, 05 and 10 were written on 2026-11-09, SDD-07 (data pages) on 2026-11-13 and SDD-14 (CASSim Scientific) on 2026-11-25; the rest are not.** Their material is in `docs/decisions/` and in the code; write each when its milestone starts. `docs/design/README.md` says what else is kept in `docs/design/` and where screenshots go (reference screenshots in `docs/design/reference/<device>/`, evidence in `docs/testing/`). Each SDD names the requirement IDs it covers and does not restate them: the SRS is the only copy. Requirement IDs (`FR-*`, `NFR-*`) are the stable references between SRS, SDD, tests and corpus tags.

## 11. Documentation and planning follow-ups (proposed 2026-11-08)

These came out of a review of PLAN.md, the SRS, CLAUDE.md and `docs/` against the repository. Recommendations, in the order to do them.

1. **DONE 2026-11-09.** **Traceability generator (NFR-MAINT-006, Must).** Add `tools/traceability.py`: parse requirement IDs from `docs/SRS.md`, find them in `tests/` (docstrings and markers) and corpus tags, write `docs/traceability.md` with an "untested, reason" list, and check it in CI. Run it first: the gap list is the best view of what the tests do not yet claim.
2. **DONE 2026-11-09.** **Enforce coverage (NFR-MAINT-004).** CI runs `--cov=cassim` but has no threshold. Add `fail_under` per package once the first report shows where things stand; set it just below today's figures so it ratchets.
3. **DONE 2026-11-09.** **`docs/accessibility.md` (NFR-USE-002).** Start with what is known: keyboard operation in Computer mode, focus, the canvas-renderer limit, and the Semantics hooks. Short is fine; the file's job is to record gaps.
4. **DONE 2026-11-09.** **SDD-02, 04, 05, 10** from the decisions (section 10).
5. **DONE 2026-11-09.** **Browser matrix.** A short `docs/testing/browsers.md`: what has been run on which browser and device, with dates, so NFR-PORT-001 has evidence. Do the Safari, iOS and Chromebook runs before the M2 exit.
6. **Keep AGENTS.md short.** Milestone detail belongs in this file, not in the agent working brief, where it quickly goes stale.
7. **DONE 2026-11-09.** **Number the open "to check on the simulator" items in one place.** They are scattered across decisions 0007 to 0010, 0022 and the emulator results files. Collect them in `docs/testing/simulator-todo.md` so the next capture session has a single list.
8. **Sequencing.** After M2 closes, take M3 (data pages) then M4 (graphs); both are Must for VCE use (planned in decision 0031, 2026-11-13). M5 builds the isolated Python/pseudocode environment next. M6 is mostly Could (TI-Basic, library ports); consider doing only the `mm_`/`sm_`/`gm_` ports Simon actually uses and leave room for the TI-Basic interpreter to reuse the M5 program tree.
9. **Public release gate.** The third-party notices (NFR-LEG-003) have no owner or milestone. Add them to the M7 exit. (NFR-LEG-007, the VCAA cases, was settled on 2026-11-12: they stay, attributed; decision 0012.)
10. **Release gate: original text (NFR-LEG-009, NFR-LEG-006).** Before public release, audit the in-app help, catalog and error strings against both Reference Guides for verbatim copying (decision 0028 records the method and a first clean run on 2026-11-12; repeat it once help and catalog text exist). Add it to the M7 exit with item 9. TI screenshots may stay in the repository but never go in the build (decision 0029).
11. **TODO, early 2027: VCAA approved technology.** The VCAA site was down when the help page "Other calculators and CAS software" (`docs/wiki/`) was written (2026-11-13), so its exam section is from search results. Check the 2027 approved calculator and software lists and the new restrictions (user-defined functions restricted from 2027), then update that page, the wiki's exam wording and any SRS text that names approved devices.
12. **Pseudocode loop-boundary annotations.** On the next pseudocode app edit, add a clear, matching indication of each loop's start/end region in both the code pane and trace table, including repeated/nested loops, without changing the program text or trace semantics.

**Warning triangle (FR-CALC-007): built in slice 3.0, 2026-11-13.** `Result.warnings` is raised in `Evaluator._finish` (Real mode, a non-real step with a real answer), carried by the worker reply and drawn left of the entry by the shared `cassim.app.warning.warning_mark`. Still to capture on the simulator: where else the device shows it (Graphs, Lists & Spreadsheet, Data & Statistics); those pages use the same mark.

## 12. Architecture follow-ups (from a structural review, 2026-11-08)

Done in branch `arch-cleanup`: the replay interface is public (`serialize.replay_steps`, used by `from_dict` and `Runner.load`), the architecture map above matches the code, and `tests/test_architecture.py` enforces the import rules and checks that this map lists every package. The rest is deliberately deferred and **tied to a trigger**: do it when the trigger happens, not before.

| # | Change | Trigger | Notes |
|---|--------|---------|-------|
| A3 | Split `devices/nspire/ui/views.py` (calculator view and several dialogs) into cohesive modules. | Move code as each part is next touched. | The former compact tools menu has gone; app-level actions now share one CASSim menu in both views. |
| A6 | Re-check the spare engine (`app/web.py`, decisions 0016, 0027, SDD-02). Each load still boots three Pyodide runtimes (Flet, the engine, the spare). Remaining options: skip the spare on phones (Cancel would then restart in about 2 to 4 s since 0027), or share one runtime. | Phone memory trouble or key-press lag, or Cancel changes. | Simon's phone install (2026-11-12) works but was slow (about 11 s to load on a Pixel 6). Partly done in 0027 (2026-11-12): engine boot cut from 7 to 9 s to 2 to 4 s, and the spare now waits 3 s after the engine is ready (`SPARE_DELAY`). Key-press lag was cut earlier (keypad not rebuilt per press: 322 ms to 34 ms per refresh, 2026-11-09). Still to do: time start-up, memory and key presses on the Pixel 6 (`tools/loadtime.py` for desktop) and record them in 0027. |
| A7 | Lazy-load catalog areas in the engine: register each function's name and arity up front, and import its module (calculus, matrices, distributions, finance and so on) on first use. | The phone timing (A6) shows the engine, not the UI, is what the user waits for, or a new area (SciPy statistics, M4) makes engine start-up slower. | Deferred in 0027: the engine boots in the background in about 2 s, and lazy loading moves that wait to the first use of a feature, perhaps mid-question. `core/builtin_names.py` already holds every name, so the registry change is small. Measure with `tools/loadtime.py` and a first-use timing per area; SciPy must stay lazy whatever is decided (PLAN section 3, `stats/`). |
| A8 | Reset the document format for the release: `SCHEMA = 1` in `doc/serialize.py`, drop every pre-release migration and reader (schema 1 one-character rows, entries as objects, the localStorage autosave fallback in `Shell.read`), and refuse pre-release files with a clear message. Old autosaves and saved documents in the browser are then dropped rather than opened. | CASSim v1.0 release (Simon, 2026-11-14). | Backwards compatibility with pre-release saves is deliberately broken at v1 (decision 0033). Until then, keep pre-release files opening. From v1 on, every format change adds a migration (FR-DOC-004). |
| A10 | A touchpad mode for the pointer beside the joystick: the pointer moves only while the finger moves and stays until something else happens, as on the device (`device/pointer.py`). | A user asks, or Tablet mode work. | The joystick is CASSim's own design by choice (emulator check 6, part P). |
| A12 | Two remaining Pseudocode typing-aid risks on a slow machine: (a) the conversion runs in Python, which sends the whole editor text back, so a key typed while it is on its way back is overwritten; (b) Flutter's text field has its own Ctrl+Z, which can cross the app's typing-aid undo (`on_keyboard`). If either is seen, convert and undo in the browser instead. | A report of lost or garbled typing or a failed undo in Pseudocode, a slow-Chromebook test, work on typing aids, or a Flet release whose text field can edit or format text in the browser. **Review again later** (Simon, 2026-11-22: the 0.5 s pause and the tests' 1.5 s wait are accepted for now; users can adapt if a key is lost). | (a) seen on 2026-11-22 once the aid was on by default (`\th` lost after `<-` on a loaded machine). Mitigated the same day, as Simon chose: the aid now converts only after typing pauses for 0.5 s (`TYPING_AID_PAUSE`), covering everything typed since (`convert_region`), so only a key pressed in the instant after a pause can be lost. Earlier the same day: under load several keys reach Python as one change, so conversion handles a short burst, not just one key. The e2e tests pause 300 ms between typed pieces, and 1.5 s (`AID_WAIT`) after typing something the aid converts before typing on; a per-key Playwright delay instead makes Flutter web drop shifted keys such as `<`, which a real keyboard does not. |
| A13 | Make the three browser tests marked `xfail(strict=False)` as flaky reliable, and remove the marks: `test_sorter_shows_sheet_column_names` and `test_sheet_formula_journeys` (`tests/e2e/test_sheet_browser.py`), and `test_arrow_repeat_moves_calculator_caret_and_sheet_cursor` (`tests/e2e/test_key_repeat_browser.py`; a held arrow moved the caret fewer than 2 places once in the full suite, passing alone; marked by Simon's request 2026-11-23, with the formula test, which failed on main too). Its shared steps (`check_shared_column`) lose typed keys under load: a Down pressed just after switching back to the sheet never registers, and `=a[]^2` on the formula row sometimes bounces the cursor between the formula and name rows instead of computing. Wait for the page after a switch, add a "move to cell" helper that presses until the `CASSIM: SHEET` log shows the target, and instrument the formula entry if it still fails. Check whether a user pressing a key the instant a page appears can lose it too. | Review in the next session (Simon, 2026-11-22): do not leave it marked. | Marked flaky on 2026-11-22 so `local_ci` can pass; the other test using `check_shared_column` (`test_sheet_formula_journeys`) and the key-repeat test were marked on 2026-11-23 after failing the same way. Review all three together. Same failure class as A12 and the Finance Solver fill now retried with `AppPage.until`. |
| A11 | Draw the variable sidebar's values and the Graphs function labels from the editor tree (`editor_ast.result_latex`), as Calculator results are (decision 0035 stage 3), instead of SymPy's LaTeX. | Work on the sidebar or Graphs labels, or a report that they look different from the history (products without `·`, bold `or`, `@n1`). | Accepted as is for now (Simon, 2026-11-20): revisit, do not forget. |

**Keeping the map in sync.** `tests/test_architecture.py` fails if a package under `src/cassim/` is missing from the map in section 3, or still tagged `[placeholder]` after it has code. AGENTS.md instructs agents to update the map in the same commit as any package move. Review the table above when a trigger is met and delete the row when done.

## 13. Future: native builds (Would, NFR-PORT-004)

Only the static web site is built and tested today (`python -m tools.publish`, output `build/web`). `flet build` can also make `windows`, `macos`, `linux`, `apk`, `aab`, `ipa` and `ios-simulator` packages from the same code. None has been tried. What each needs, so the work can be picked up later:

1. **Project setup.** A `[tool.flet]` section in `pyproject.toml` and a thin `src/main.py` that calls `cassim.app.main.run`; today only `tools/publish.py` stages a web entry point. Run `flet build` with `PYTHONUTF8=1` on Windows (decision 0018).
2. **Cancel.** `make_runner()` uses the worker engine only in the browser; native builds run the engine in-process, where `LocalEngine.cancel()` returns False. Cancel within 1 s (SRS) needs the engine in a subprocess or isolate.
3. **Dependencies.** The core needs only SymPy, mpmath and PyYAML (pure Python). SciPy and NumPy are not used by the app (decision 0031), so they do not block Android or iOS.
4. **Browser-only code.** The service worker, install prompt, share-link base URL and the engine worker assume a browser. File open and save, storage and the clipboard need a native check.
5. **Toolchains.** Flutter (the Flet CLI installs it). Windows needs Visual Studio with the C++ workload; Android needs the Android SDK and a JDK; macOS and iOS need a Mac with Xcode, and an Apple developer account beyond the simulator; Linux needs Linux. CI would need a runner per platform.
6. **Release.** Signing, store listings and updates are out of scope until a target is chosen.

## 14. Hosting on Cloudflare Pages (done 2026-11-13)

The site moved from GitHub Pages to Cloudflare Pages, and the repository is private. `.github/workflows/deploy.yml` builds and deploys three projects with `wrangler pages deploy`:

| Project | Address | Deployed on |
|---|---|---|
| `cassim-app` (stable) | <https://cassim-app.pages.dev/> | a published GitHub release, or a manual run with target `stable` |
| `cassim-calc` (testing) | <https://cassim-calc.pages.dev/> | every push to `main` |
| `cassim-wiki` (help) | <https://cassim-wiki.pages.dev/> | every push to `main`; `docs/wiki/` built by `python -m tools.wiki_site` |

Notes:

1. **Built at the root.** `tools.publish` now defaults to `--base-url ''`; `tests/e2e/test_pwa.py` still boots the site under `/CASSim/` so a sub-path build stays tested.
2. **Secrets.** The workflow needs `CLOUDFLARE_API_TOKEN` (Cloudflare Pages: Edit) and `CLOUDFLARE_ACCOUNT_ID` as repository secrets.
3. **Moving users.** Share links, installed apps and autosaved documents belong to an origin, so they do not carry over from the GitHub Pages address or between the stable and testing sites: save a document to a file and open it on the new site.
4. **Releasing.** `gh release create vX.Y.Z --generate-notes` deploys the current `main` to the stable site. The steps are in the README (Publishing).
5. **Verified.** The workflow deployed the testing site and the help pages from GitHub Actions on 2026-11-13.

## 15. Pluggable devices and separate bundles (decided 2026-11-13)

Simon's direction, now implemented for the first two devices: `cassim-app` (stable) and
`cassim-calc` (testing) are **all-in-one** apps that always open to a Home chooser.
Nspire, Pseudocode & Python and Scientific are enabled; ClassPad, Prime and later devices remain
visible in Home when not built. Home renders before a device UI loads. Each built device can also be
published as its own **bundle** on its own site, so someone who needs one device downloads only that
one. The Nspire bundle's cold start is still dominated by Pyodide, SymPy and the Flet app; the
pseudocode bundle does not need SymPy. Requirements: FR-PROF-001 to FR-PROF-018 and FR-RUN-009 in
the SRS.

### 15.1 Devices, bundles and sites

| Device id (package `devices/<id>/`) | Bundle | Product name | Site (Cloudflare Pages project) | When |
|---|---|---|---|---|
| every built device, with the Home chooser | `all` | CASSim | `cassim-app` (stable), `cassim-calc` (testing) | live with Nspire, Pseudocode & Python and Scientific |
| `nspire` | `tin` | CASSim-TIN | `cassim-tin` | M2x |
| `pseudocode` | `pseudo` | CASSim-pseudo | `cassim-pseudo` | M5; deploys with each release (wired 2026-11-25) |
| `scientific` | `sci` | CASSim-Sci | `cassim-sci` | SDD-14; deploys with each release (wired 2026-11-25) |
| `classpad` | `cp` | CASSim-CP | `cassim-cp` | M8 |
| `prime` | `prime` | CASSim-Prime | `cassim-prime` | M9, if go |

- Ids and package names in the code are the long ones; bundle and site names are the short ones.
- Single-device sites are **stable only**: they deploy on a release, like `cassim-app`. Testing happens on `cassim-calc`, which holds every device.
- A single-device site's icon carries its Home symbol where the testing icon carries β (ℕ for the Nspire, < > for Pseudocode & Python, a flask for Scientific; `tools.publish.draw_mark`), so each installed app is distinct from the all-in-one app and from the others (2026-11-25).
- The help site (`cassim-wiki`) stays one site, with a section per device, and lists every site.
- All eight Cloudflare Pages projects exist (the four single-device ones were reserved, empty, on 2026-11-13, and cassim-sci on 2026-11-25); a single-device site has no content until its bundle is first built.

### 15.2 Architecture: pluggable modules, separable UIs

1. **A device is a plug-in.** A device profile (FR-PROF-001) is a package, `src/cassim/devices/<id>/`, that exposes one `Device` object: id and title; the engine it needs (worker module and the Pyodide packages it loads); its page types; keymap, menus, skin and presets; its document schema namespace; and its help section. It depends on the shared layers and never on another device.
2. **Shared layers stay shared.** `core/` (maths, values, Pratt-parser framework), `runtime/` (interpreters), `device/` (key layers, menu and screen frameworks), the document model and storage, and the shell (`app/`: window, switcher, storage, share links, PWA, themes). Core still never imports Flet.
3. **Separable UIs.** Each device's Flet views live with the device (`devices/<id>/ui/`) and talk to the shell through a small interface: mount, unmount, menu and toolbar contributions, and dialogs. The shell knows device ids, not device classes.
4. **Registry by build, not by discovery.** Pyodide has no reliable entry points, so `tools.publish` writes a generated `bundle.py` that lists the devices in the bundle. The shell imports only what that file lists; a test checks that no device package imports another.
5. **One engine worker per device kind.** The Nspire engine boots SymPy; the pseudocode engine is pure Python and boots without it. The all-in-one Home screen starts no device worker; the app starts a device's worker only when that app is first opened.
6. **Documents name their device.** `.cassim.json` and share links carry the device id. Any bundle that contains that device opens them; one that does not names the site that does and links to it (FR-PROF-009). Storage namespaces are per device (FR-PROF-004, Q20), and each site is its own origin, so documents move between sites as files or share links.

### 15.3 Build, cache and deploy

- `python -m tools.publish --bundle all|tin|pseudo|cp|prime` builds one bundle. A bundle's packages, archives and service-worker list come from its devices.
- In the all-in-one app each device is its own archive (`device-<id>.zip` and its engine packages), fetched on first use. The service worker always precaches the shell. It also precaches each device once that device has been opened, so the device works offline from then on. The first visit can show Home without fetching a device; opening an app then fetches that device. An "Available offline" setting can fetch every device in advance.
- `deploy.yml` grows a matrix: `main` deploys `all` to `cassim-calc`; a release deploys `all` to `cassim-app` and each single-device bundle to its own project.
- Download size and cold start are measured per bundle and reported (no budgets, as in the SRS).

### 15.4 Order of work

Steps 1 to 3 are milestone M2x and come **before M3** (decided 2026-11-13), while only the Calculator page exists, so that Graphs, Lists & Spreadsheet and Statistics are built inside the new structure and never need moving. They change structure, not behaviour.

1. ADR on the device interface and bundle format: `docs/decisions/0032` (written 2026-11-13). It replaces the ADR planned for 8a, and splits step 2 into three PRs: `doc/` and registered page types; `devices/nspire/` with the profile data and the Calculator page model; the shell and `devices/nspire/ui/`. Its item 7 leaves the split of `core/` to M8a (agreed 2026-11-13).
2. Move the Nspire into `devices/nspire/` behind the interface, together with decision 0031's A4 (the document model moves to `doc/`, page types are registered). Gate: every corpus case replays unchanged, the e2e suite passes, and coverage targets hold.
3. Bundle-aware `tools.publish`, the `tin` bundle and its site, and download-size reporting. **Steps 1 to 3 done 2026-11-13** (decision 0032). `cassim-tin` gets its first content at the next release. The `tin` and `all` bundles are the same size today (90 MB, of which Flutter 57, Pyodide 16, the engine archive 11 and the app archive 2); the sizes differ once a second device is built.
4. **Done.** The all-in-one Home chooser shell (FR-PROF-010 to -018), with the stable choice order shown and future unbuilt choices greyed.
5. **Done as the standalone M5 slice.** The `pseudocode` device is the second enabled Home choice and has a single-device bundle. Full Python execution, translation and some editor/file features remain M5 work.
6. (M8/M9) Add ClassPad and Prime as plug-ins; complete the per-device lazy asset and offline cache plan when those downloads make it material.

### 15.5 Decisions (Simon, 2026-11-13)

- Pseudocode is its own device and site, and also an entry in the all-in-one app. This revises SRS Q23 and FR-RUN-009, which had the Code view as a mode inside one app.
- Steps 1 to 3 go before M3.
- Single-device sites are stable only.
- Long ids in code (`nspire`, `classpad`, `pseudocode`, `prime`); short names for bundles and sites.
