# CASSim: Software Requirements Specification

Status: **DRAFT 0.9** (2026-11-25: Open and Save are browser storage and Import and Export are files in every app: FR-DOC-010 widened, FR-FX-SHR-006 reworded; 2026-11-25: consistency pass with the design documents: the CASSim Scientific requirements FR-FX moved from after section 10 into 4.12, FR-FX-STA-006 corrected, FR-DOC-009 allows up to four panes (decision 0034), SciPy and NumPy no longer listed as shipped, screenshot locations and appendix A brought up to date; 2026-11-18: milestones resequenced so Python/pseudocode is M5, TI-Basic and extensions are M6, and polish is M7; current implementation status refreshed; spreadsheet navigation, range-selection and formula point-mode requirements FR-SHEET-004 to FR-SHEET-008 added; 2026-11-13: pluggable devices and bundles, PLAN.md section 15: FR-PROF-008 and FR-PROF-009 added, FR-PROF-003, FR-PROF-005 and FR-RUN-009 reworded, Q23 revised, and the device interface comes before M3; earlier the same day: M3 and M4 planned, decision 0031: FR-DOC-008, FR-DOC-009, FR-STAT-005, FR-NOTE-001 and NFR-PERF-006 added, FR-STAT-004 no longer names SciPy; earlier, 2026-11-08: implementation status added as appendix B, storage and editor wording brought into line with what is built; earlier, 2026-11-04; Q1–Q15 answered; Q16–Q41 are new and concern the later programming and profile scope in 4.12. **The Code part (M5: Python and pseudocode, 4.12 Code view, runtime, pseudocode, translation, trace, settings, syntax and editor) is finalised: every question it depends on is answered.** Only the ClassPad and HP Prime questions, Q17, Q18, Q19 and Q22, remain open). Structure follows ISO/IEC/IEEE 29148. Source material: `PLAN.md`, `AGENTS.md`, `docs/decisions/`, `docs/testing/TESTING.md`. Items marked **[Q#]** depend on an open question in section 10. Items marked **[TBC]** are inferred, not yet confirmed.

Requirement IDs are stable (`FR-CAS-012`). Priority is MoSCoW (M/S/C/W). "Mx" is the milestone in PLAN.md section 8. Verification: **T** test (unit/corpus/device), **E** E2E (Playwright), **I** inspection, **D** demonstration, **A** analysis (measurement).

---

## 1. Introduction

### 1.1 Purpose
Defines what CASSim must do and the constraints it must meet. It is the baseline for the design documents (SDD, `docs/design/`) and for acceptance testing.

### 1.2 Scope
CASSim is a static, installable (PWA) browser simulation of the TI-Nspire CX CAS for teaching, practice and demonstration. The maths engine (SymPy and mpmath; SciPy is not shipped, decision 0031) runs client-side in Pyodide. There is no server component. CASSim reproduces the *behaviour* and *workflow* of the handheld/teacher software, not its ROM, artwork or branding. It reproduces the device's *layout, menu structure and vocabulary* so that students can transfer to the real handheld, but not its artwork or prose (decision 0028).

CASSim is a **simulator, not a hardware-level emulation**: it need not match TI output exactly, but must be close enough not to confuse students or teachers. CASSim is released under the MIT licence (decision 0042).

**Later scope.** After the core page set (M0–M4), CASSim adds a web-based Python and pseudocode environment in M5, with translation between the two and a stepwise forwards-and-backwards trace table, standalone and as page types (Should). TI-Basic and library extensions follow in M6, polish in M7, then a device switcher with a Casio ClassPad profile in M8 (Could), and possibly an HP Prime profile in M9 (Would) (4.12). The requirements and priority of each feature are unchanged by the resequencing.

Out of scope: Geometry page; approved-exam-calculator status; TI, Casio and HP ROM/OS/firmware code, logos or artwork; loading `.tns` libraries (the `mm_`/`sm_`/`gm_` UDFs are ported natively instead); server-side accounts or sync.

### 1.3 Definitions
| Term | Meaning |
|---|---|
| CAS | Computer algebra system |
| TI simulator | TI-Nspire CX CAS Premium Teacher Software, the behavioural oracle that CASSim is compared against |
| Corpus | Golden test cases captured from the simulator (`corpus/`) |
| Document / Problem / Page | TI hierarchy: a document holds Problems; Problems share variables; each holds Pages (Calculator, Graphs, ...) |
| Device model | Headless model of keys, menus, cursor and screen, independent of Flet |
| VCE | Victorian Certificate of Education (Methods, Specialist, General Mathematics) |
| Canonical equality | Two results are equal if symbolically/numerically equal, regardless of text form |
| Device profile | The bundle that makes one calculator behave like itself: dialect, catalogue, display conventions, document/page model, keys, menus, skin and corpus. The TI-Nspire CX CAS is the first |
| Oracle | The reference implementation a profile's corpus is captured from: the TI simulator for the Nspire; the manufacturer's PC emulator for ClassPad and Prime [Q17, Q18] |
| Pseudocode | A structured, language-neutral notation for algorithms; CASSim implements one dialect [Q16] |
| Code view | The standalone Python/pseudocode environment, with no device skin; it is the `pseudocode` device |
| Bundle | One published build of the app: `all` (every built device, with the switcher) or a single device (`tin`, `pseudo`, `sci`, `cp`, `prime`), each on its own site (PLAN.md section 15) |
| Trace table | A table recording variable values as a program runs: **vertical** (one row per executed line) or **horizontal** desk check (code down the side, one column per loop pass) |
| Syntax file | The user-editable data file that defines which spellings, optional tokens and block terminators the pseudocode parser accepts and which style the printer writes |

### 1.4 References
`PLAN.md`; `AGENTS.md`; `docs/decisions/`; `docs/design/` (the design documents; `docs/design/README.md` says what is kept where); `docs/command_matrix.md`; `docs/testing/TESTING.md`; `references/` (TI Reference Guide, the scientific calculators' manuals, VCE resources, LazyMath guides; not in the repository); `docs/design/reference/<device>/` (layout screenshots of each maker's software, kept locally and not committed).

### 1.5 Stakeholders
| Role | Interest |
|---|---|
| Owner/developer (Simon Tyler) | Accuracy, maintainability, scope control |
| Maths teachers | Demonstration to a class; preparing worked solutions |
| Students (Years 10-12, VCE) | Practising calculator workflow outside class and without a device |
| School IT | Hosting, device compatibility (Chromebooks, iPads), privacy |
| Library authors (LazyMath) | Licence compliance for ported UDFs |
| Texas Instruments, Casio, HP | Trademark/IP boundary (no marks, artwork, ROM or firmware) |

---

## 2. Overall description

### 2.1 Product perspective
A self-contained web app: Flet UI (Flutter web, canvas rendered) over a pure-Python core (`src/cassim/core`) that never imports Flet. The engine runs in its own Pyodide worker so the UI stays responsive and evaluation can be cancelled by terminating that worker (decision 0005). Persistence is in the browser: autosave and System Settings use IndexedDB (with a legacy localStorage reader), and named Code files also use IndexedDB in M5. Hosted as static files.

### 2.2 Product functions (summary)
Calculator page with TI syntax; Graphs and Table; Lists & Spreadsheet; Data & Statistics; Finance; Notes; Program Editor and TI-Basic; documents and Problems; three display modes (Computer, Tablet/demo, Handheld); offline use. From M5: a Python and pseudocode environment, standalone and as page types. Later, as Could and Would: a device switcher with Casio ClassPad and HP Prime profiles.

### 2.3 Users and classes
1. **Student**: knows the handheld; wants identical keystrokes and results.
2. **Teacher presenting**: needs readable large display, optional keystroke display, fast recovery from mistakes.
3. **Teacher authoring**: builds documents, programs, Python scripts; shares files with students.
4. **Developer/maintainer**: runs corpus, adds commands.
5. **Student programmer** (from M5): writes and runs short Python or pseudocode programs, standalone or on a calculator page.
6. **Student or teacher on another CAS calculator** (from M8): wants the Casio or HP workflow rather than the Nspire's.

### 2.4 Operating environment
Evergreen desktop and mobile browsers. Primary: Chromebooks, Chrome, Safari. Secondary: Edge, Firefox. Python 3.14 / Pyodide 314.0.7. Static hosting on Cloudflare Pages or any other free or cheap static host, with correct MIME types (`.mjs`) and no server-side code. Share links must stay within typical URL limits (about 2,000 characters is safe across browsers). Dev: Windows 11, uv, Ruff, Ty, pytest, Hypothesis, Playwright.

### 2.5 Constraints
- C-1 Core is pure Python, fully typed, Ty strict; SymPy is touched only in `core/compat/sympy_adapter.py`.
- C-2 No TI, Casio or HP logos, artwork, ROM or firmware content. Product name is CASSim. CASSim reproduces each device's layout, menu structure and vocabulary so that students can transfer to the real handheld, but not its artwork or prose (decision 0028, NFR-LEG-008, NFR-LEG-009).
- C-3 TI syntax is parsed by a real tokenizer + Pratt parser, never regexes. The same holds for every other device dialect and for pseudocode.
- C-4 Canonical text is Unicode (`ⅇ ⅈ ᴇ π ∞ ᵀ ʳ ᵍ ° ∠ ▶`); ASCII is an input/REPL spelling only. These conventions are fixed.
- C-5 Statistics follow the TI/school convention (quartiles as medians of halves; `sx` uses n-1, `σx` uses n); `numpy.percentile` is not used.
- C-6 The Flet static build needs a post-publish step (vendor wheels, patch `index.html`) for offline use (decision 0002).
- C-7 Must not auto-run user Python or pseudocode from a loaded document, import or link.
- C-8 The symbol and statistics conventions in C-4 and C-5 belong to the Nspire profile. Other profiles take theirs from their own oracle and must not change the Nspire's.
- C-9 Introducing device profiles must not change any Nspire behaviour (FR-PROF-002).

### 2.6 Assumptions and dependencies
Pyodide continues to bundle SymPy and mpmath at compatible versions (SciPy is not shipped, decision 0031); Flet static publishing remains viable (fallback: thin custom web front-end over the same engine); simulator access remains available for corpus capture; LazyMath stays Unlicense (to be recorded in a decision before porting). For M8/M9: the manufacturers' PC emulator software for ClassPad and Prime stays available and its terms allow corpus capture [Q17, Q18].

---

## 3. Fidelity and correctness model

This cross-cuts every functional area.

- **FID-1** (M, T) Correctness is judged by canonical equality against the simulator corpus, not by TI's exact output text. Maths is rendered from LaTeX/layout tree.
- **FID-2** (S, T) Output must be close enough not to confuse a student or teacher used to the handheld: same mathematical content, familiar form (e.g. `x=-2 or x=2`, fractions stay exact in Auto mode). Exact text match is not required. Where the corpus marks an area `compare: exact` (typically number display and simple forms), the text matches the simulator.
- **FID-3** (M, T) Every claimed behaviour has at least one corpus case with provenance (`simulator` or `hand-verified`) and evidence where simulator-captured. No behaviour change ships without a test.
- **FID-4** (M, T) Known divergences are `xfail(strict=True)` with a reason, so fixing one forces removing the marker.
- **FID-5** (M, T) Documented simulator behaviours are matched (TESTING.md section 14), including: Approximate mode shows decimals inside symbolic results; Float 3/Fix 2 switch to `ᴇ` notation for extreme values; `1/0` and `ln(0)` give `undef`; undefined variables echo unchanged; `int(-2.5) = -3`; `sinh⁻¹(1)` is unevaluated in Auto mode.
- **FID-6** (S, T) TI-specific solution forms are reproduced: general solutions with `@n1` constants, `cSolve`, `x=-2 or x=2`, domain constraints via `|`.
- **FID-7** (S, T) Each device profile has its own oracle and corpus (`corpus/<device>/`), and FID-1 to FID-4 apply to it unchanged. The behaviours listed in FID-5 and FID-6 are the Nspire's. Python semantics are CPython's (Pyodide); pseudocode semantics are the chosen dialect's written specification, pinned by golden programs (FR-RUN-006).

---

## 4. Functional requirements

### 4.1 Language and evaluation (core) — M1
| ID | Requirement | Pri | Ver |
|---|---|---|---|
| FR-LANG-001 | Tokenise and parse TI input: `:=`, `→`/`->`, `|` constraint (lowest precedence), implicit multiplication (`2x(x-1)`, `f(x)` call vs `ax`), `^` with TI unary-minus rules, `√`, `π`, `ᵀ`/`@t`, `≤ ≥ ≠`, `and or not xor`, lists `{}`, matrices `[1,2;3,4]`, strings, `lib\fn`, `@n1`, `#` indirection, primes, units `_m`. | M | T |
| FR-LANG-002 | Typed ASCII input spellings are accepted (`@e @i @E @t @r @g @d @< @> pi infinity`); outputs use Unicode forms. | M | T |
| FR-LANG-003 | Printer round-trips: parse -> print -> parse is the identity on the AST (Hypothesis). | M | T |
| FR-LANG-004 | Plain `e`, `i`, `E` are ordinary variables; `2e3` is `2*e3`. | M | T |
| FR-EVAL-001 | Evaluate to a typed Value (Number, Expr, List, Matrix, Str, Bool, Eq, Void, Unit). | M | T |
| FR-EVAL-002 | Settings: angle (Radian/Degree/Gradian), calculation mode (Auto/Exact/Approximate), Real/Rectangular/Polar, float digits (Float n / Fix n), exponential format, base. | M | T |
| FR-EVAL-003 | VCE presets: General (Degree/Approximate/Real), Methods (Radian/Auto/Real), Specialist (Radian/Auto/Rectangular), Float 8. | M | T |
| FR-EVAL-004 | Exact vs approximate follows TI rules (mode, and a decimal point forces approximation); `Ans` and last-answer insertion behave as on the handheld. | M | T |
| FR-EVAL-005 | Errors use TI error codes/messages where known; engine errors never crash the UI. Calculator error results use straight ASCII double quotes, and the red error card can be dismissed by clicking it or pressing a key. | M | T |
| FR-EVAL-006 | Evaluation is cancellable (On/Esc equivalent) within a bounded time; state is restored after cancel. | M | T/E |
| FR-SCOPE-001 | Document > Problem > Pages scoping; `Define`, `:=`, `→`, `DelVar`, `ClearAZ`, `Local`; library functions are document-wide and read-only. | M | T |
| FR-SCOPE-002 | A new Problem is a blank variable scope. | M | T |

### 4.2 Command catalogue — M1d (tiered)
| ID | Requirement | Pri | Ver |
|---|---|---|---|
| FR-CAT-001 | **Tier 1 (VCE core)**: solve/cSolve/zeros, factor/expand/propFrac/completeSquare, derivative/integral/limit/nInt/deSolve, trig/exponential/log, lists and matrices (det, inverse, rref), norm/binom/inv distributions, `tvm*`/`eff`/`nom`, regressions, OneVar/TwoVar. | M | T |
| FR-CAT-002 | **Tier 2**: remainder of the Reference Guide CAS commands, per `docs/command_matrix.md`. | S | T |
| FR-CAT-003 | **Tier 3**: unusual conversions and templates. | C | T |
| FR-CAT-004 | Catalog is data-driven and powers tab-completion, the Catalog dialog and help text. | S | T |
| FR-CAT-005 | The command coverage matrix is published and kept current. | M | I |
| FR-CAT-006 | Unsupported commands fail with a clear, TI-like error rather than a wrong answer. | M | T |

### 4.3 Calculator page — M2
| ID | Requirement | Pri | Ver |
|---|---|---|---|
| FR-CALC-001 | History of input/result pairs (input left, result right), scrollable, with `Ans`. | M | D/E |
| FR-CALC-002 | Evaluate (Enter) and force-approximate (ctrl+Enter). | M | T |
| FR-CALC-003 | Results rendered as 2D maths (fractions, powers, roots, matrices, summations). | M | D |
| FR-CALC-004 | Input is a structured 2D template editor, as on the handheld: a typed `/` stays linear and is stacked after Return; the fraction template (palette, ctrl+/ on a computer keyboard, ctrl+÷ on the handheld keypad) takes the preceding term, `^` and `√` open a slot, Right and Tab leave or move between slots, Backspace highlights a template then deletes it (decisions 0015 and 0017). The handheld's editing shortcuts (Tab and shift+Tab between fields, shift+arrows to select, shift+plus and shift+minus for the derivative and integral templates, ctrl+1 to ctrl+9 for jumps) are listed in `references/TI-Nspire CX II Family Shortcuts 2026.pdf`; each one CASSim supports is to be recorded in a shortcut table in `docs/design/`. Matrices and lists as templates follow. | M | D |
| FR-CALC-005 | Templates palette, Catalog, variable menu, copy/paste of inputs and results, up-arrow recall/edit of history. | M | D |
| FR-CALC-006 | Undo/redo of edits and of deleted history. | S | T |
| FR-CALC-007 | Warning triangle: an entry that completes with a caution shows a yellow triangle beside it, and hovering it (or tapping it on a touch screen) shows the message. It is a shared component, not calculator-only: the device also uses it elsewhere (for example Graphs and Lists & Spreadsheet). First use: Real mode `√(-1)·√(-1)` and `real(3+4·√(-1))` give a value with the warning "Non-real calculation" (decision 0026, `docs/testing/emulator-domain-results.md`). Needs a `warnings` field on the engine result, so it reaches the UI through the worker. | S | D/T |

### 4.4 Documents, Problems and pages — M2
| ID | Requirement | Pri | Ver |
|---|---|---|---|
| FR-DOC-001 | Multiple documents; add/delete/reorder Problems and Pages; page sorter. | M | D |
| FR-DOC-002 | Document and system settings dialogs. | M | D |
| FR-DOC-003 | Autosave to browser storage; recover after reload or crash. Since M3 slice 3.0 the autosave is in IndexedDB, written half a second after the last change (and at once when the tab is hidden); a document autosaved in localStorage by an earlier build is still opened. The desktop app uses Flet `SharedPreferences`. | M | E |
| FR-DOC-004 | Export/import native plain-text `.cassim.json` with a versioned schema and migrations. | M | T |
| FR-DOC-007 | Share a document as a URL: the document is compressed and encoded into the URL fragment (so nothing reaches any server); opening the link loads it after a confirmation. Documents too large for a link fall back to file export. | S | T/E |
| FR-DOC-008 | Within a Problem, every page shares one set of variables. A spreadsheet column linked to a list, a plot of that list and a graph of a function are views of the same variable: a change made on one page shows on every other page of the Problem when it is next seen, and nothing crosses between Problems (decision 0031). | M | T |
| FR-DOC-010 | **Applies to every app** (Nspire, Pseudocode & Python, Scientific and later devices; the code files of FR-EDT-002 and the calculations of FR-FX-SHR-006 follow it): Open, Save and Save As never show a file dialog, and files on disk are Import and Export only. On the desktop the same storage is the app's own preferences. Documents are saved by name in browser storage: Save (asks for a name the first time), Save As and Open (a list of the saved documents, each of which can be deleted). The title bar shows the page number next to the document name, with `*` appended to the displayed name while there are unsaved changes; the centre stays clear and long names are ellipsized. The autosave keeps the working state (with the name and the marker) but never writes the named copy. New, Open and Import ask before dropping unsaved changes (decision 0033). | S | T |
| FR-DOC-009 | A page can be split into two panes, each holding one app (side by side, or one above the other), with focus moved between them; Quick Graph, Summary Plot and the Graphs table use it. Shade P Value and Shade area add a pane, so a page holds up to four (three panes, then 2×2; decision 0034 item 2). Custom Split is greyed. | M | T/D |
| FR-DOC-005 | Page types in scope: Calculator, Graphs, Lists & Spreadsheet, Data & Statistics, Notes, Program Editor, Python; Pseudocode is added in M5 (FR-RUN-010). Geometry excluded. | M | I |
| FR-DOC-006 | `.tns` interop, if built, lives under **File ▸ Import…** and **File ▸ Export…**, never under Open/Save. Open and Save work on the documents kept in the browser (FR-DOC-010); files on disk are native `.cassim.json` through Import and Export. The format may be worked out only from public documentation or black-box comparison of `.tns` files Simon created with TI software he is licensed to use, never by decompiling TI software (NFR-LEG-008). An import that cannot be read fails with a clear message. No other feature depends on it. | W | T/D |

### 4.5 Lists & Spreadsheet — M3
| ID | Requirement | Pri | Ver |
|---|---|---|---|
| FR-SHEET-001 | Cells, named columns that are shared Problem list variables, formula columns, fill, sort. | M | T |
| FR-SHEET-002 | Whole-column references `a[]`; dependency graph with recalculation. | M | T |
| FR-SHEET-003 | CSV import/export; xlsx via `openpyxl` if it loads in Pyodide (decision 0003). | S | T |
| FR-SHEET-004 | When the spreadsheet is not editing a cell, an arrow key without Shift moves the active cell one position in that direction, replaces an existing range selection with that single cell and keeps the active cell visible. At a sheet edge the cursor does not wrap. | M | T |
| FR-SHEET-005 | In spreadsheet grid-navigation mode, Shift plus an arrow key starts or extends a contiguous rectangular selection. The starting cell is the anchor; further Shift+arrow presses move the other corner so the range can grow or shrink in any direction, including both endpoint cells. Holding Shift on a physical keyboard and latching Shift before an arrow press on the on-screen keypad behave equivalently. Selection is bounded by the sheet edges and remains visible. | M | T/E |
| FR-SHEET-006 | A mouse click in the spreadsheet grid selects that single cell and clears a previous range. A drag from one cell to another selects and continuously updates the inclusive rectangular range between the press and current pointer cell, regardless of direction; a later click collapses it. Shift+click, where offered, extends the current range to the clicked cell with the same result as keyboard range extension. | M | T/E |
| FR-SHEET-007 | Selecting a row heading selects the complete logical row, and selecting a column heading selects the complete logical column. Keyboard range extension that reaches a row heading at the left of the grid converts the selection to whole-row selection; extension that reaches a column heading above the grid converts it to whole-column selection. Subsequent actions treat these as whole rows or columns, not only their visible or populated cells. | M | T/E |
| FR-SHEET-008 | While a cell formula is being edited, when a cell reference is accepted at the caret, arrow-key pointing or a mouse/touch cell selection enters point mode: a single selected cell inserts or replaces the current reference at the caret, and a multi-cell selection inserts or replaces it with the inclusive reference range (for example `a1:b3`). Extending, shrinking or changing that selection updates the same reference rather than adding another formula or moving the destination being edited. The selected reference remains highlighted independently of the edited cell, which stays fixed until the formula is committed or cancelled; selection inside an ordinary text edit or inside a quoted formula string does not create references. | M | T/E |

### 4.6 Data & Statistics and Finance — M3
| ID | Requirement | Pri | Ver |
|---|---|---|---|
| FR-STAT-001 | Plots of numeric data: dot plot, histogram, box plot, scatter and XY line; regression overlays and residuals. | M | T/D |
| FR-STAT-005 | Plots of categorical data, as General Maths uses them: dot chart, bar chart and pie chart, from a list of categories or from a category list with a summary (count) list; Force Categorical X; split by a second category. | M | T/D |
| FR-STAT-002 | OneVar/TwoVar with TI quartile and sd conventions (constraint C-5). | M | T |
| FR-STAT-003 | Regressions (linear, quadratic, cubic, exponential, power, logistic, etc.) per the corpus. | M | T |
| FR-STAT-004 | Distributions, hypothesis tests and intervals, in pure Python and mpmath; SciPy is not shipped and is used only by the tests as an independent check (decision 0031). | M | T |
| FR-FIN-001 | Finance Solver dialog and `tvm*`/`eff`/`nom` with the TI argument order. | M | T |

### 4.7 Graphs and Table — M4
| ID | Requirement | Pri | Ver |
|---|---|---|---|
| FR-GRAPH-001 | Function, parametric, polar, sequence, conic and differential-equation entry types. | M | T/D |
| FR-GRAPH-002 | Window settings, zoom, pan, trace; coordinates labelled to three significant figures (decision 0034). | M | D |
| FR-GRAPH-003 | Analyse Graph: zero, minimum/maximum, intersection, integral (typed bounds accepted), dy/dx. | M | T |
| FR-GRAPH-004 | Asymptotes and discontinuities handled (no spurious joining lines). | M | T |
| FR-GRAPH-005 | Sliders; Table view of graph functions. | S | D |
| FR-GRAPH-006 | The graph engine emits a backend-neutral scene; one `Points` canvas shape per curve (decision 0004). | M | I |
| FR-GRAPH-007 | Pan/zoom of a 2000-point curve stays interactive on a mid-range phone and a Chromebook. | S | A |
| FR-GRAPH-008 | Graphs Actions menu, numbered as on the device: Attributes (line weight, line style, label style, continuous or discrete with its number of points), Text, Coordinates and Equations, and Calculate; a curve dragged by the pointer is translated (`2·sin(x)` becomes `2·sin(x-0.91)-0.044`). Graph Entry/Edit lists every entry type and Equation Template in its place; those CASSim cannot plot yet are greyed (emulator check 6, run 7). | S | T/D |

### 4.7a Notes — M4
| ID | Requirement | Pri | Ver |
|---|---|---|---|
| FR-NOTE-001 | A Notes page holding plain text, saved with the document. Maths boxes are a later Could. | S | T |

### 4.8 Programming and extensions — M6
| ID | Requirement | Pri | Ver |
|---|---|---|---|
| FR-PROG-001 | TI-Basic interpreter: `Prgm`/`Func`, control flow, `Disp`/`Request`/`Text`, `Try`, `Local`. | C | T |
| FR-PROG-002 | Program Editor page; `Define LibPub` libraries and `lib\fn` namespace. | C | T |
| FR-PY-001 | A `py("script","fn",args)` call from the CAS and a small `cassim` API (read/write Problem variables, evaluate TI expressions). **Changed 2026-11-02:** the Python page itself is FR-RUN-010 (M5); this bridge is a later extra, not part of M5, and not something the handheld does (see FR-RUN-011). | C (later, after M5) | T |
| FR-PY-002 | If Python pages are built (FR-RUN-010): scripts run sandboxed in the browser, with no permission prompt (decision 0040); scripts in loaded documents or shared links never auto-run. | M (conditional) | T/E |
| FR-LIB-001 | Native Python ports of `mm_`, `sm_`, `gm_` UDFs registered as `lib\fn`, each checked against the simulator with the library installed. LazyMath is also Unlicense, so redistribution is permitted. | C | T |

### 4.9 Device model and display modes — M2
| ID | Requirement | Pri | Ver |
|---|---|---|---|
| FR-DEV-001 | Headless device model (key layers shift/ctrl/var/menu/doc, data-driven menu tree, input editor, screen buffer) fully testable without a GUI. | M | T |
| FR-DEV-002 | **Computer** mode: page/problem sidebar, large 2D pane, templates/catalog/variable panels, physical keyboard first. Equal top priority with Handheld. | M | D |
| FR-DEV-003 | **Tablet/demo** mode: screen plus on-screen keyboard (portrait/landscape), large touch targets, optional "show keystrokes". | S | D |
| FR-DEV-004 | **Handheld** mode: faithful 320x240 layout and keypad, scales to fullscreen on phones, hardware keyboard mapped. Equal top priority with Computer. | M | D |
| FR-DEV-005 | Key layout and key labels, including the secondary ctrl/shift labels, match the real device so students can transfer to it. The artwork is CASSim's own, drawn from scratch to match positions and layout, never traced from screenshots or photographs (decision 0028). | S | I |
| FR-THEME-001 | **Dark** is the default theme. | M | D |
| FR-THEME-002 | Themes (at least Dark, Light, Outline) are selectable in the UI and defined in a config file (colours for keypad, screen, accents) that users can edit; invalid config falls back to Dark with a message. Config persists in browser storage and can be exported/imported. | S | T/D |
| FR-DEV-006 | All three modes use the same device model; they differ only in layout components. | M | I |
| FR-DEV-007 | Framework code in `device/` and `cassim.app` holds no Nspire-specific constants: key layers, menu trees, page types, skin and theme values come from data or registries supplied by the (Nspire) profile, and page types are registered rather than hard-coded. This is the M2 guard for FR-PROF-001 and adds no features. | S | I |
| FR-DEV-008 | **Menus follow the device.** The Calculator Menu and the Doc menu, the trig, templates, relations, punctuation and symbol grids and the Catalog keep the device's order and numbering (decision 0022), so keystroke habits transfer. An item CASSim cannot do yet is shown greyed as a placeholder, never omitted, and does nothing. Every item is also reachable by mouse and touch. | S | T/D |
| FR-DEV-009 | The multi-argument commands (distributions, statistics, regressions, Finance Solver, derivative at a point, matrices, systems, polynomial roots) have data-driven dialogs that paste or run as on the device (decision 0022). | S | T/D |
| FR-DEV-010 | System Settings are persisted per browser (start view, maths size, keypad letters ABC or QWERTY) and apply to every mode. | C | T |

### 4.10 Teacher and class features
| ID | Requirement | Pri | Ver |
|---|---|---|---|
| FR-TCH-001 | Large-text/projection mode and "show keystrokes". | S | D |
| FR-TCH-002 | Exam-restriction mode, teacher-configurable (e.g. disable Python page, programs, selected commands). Clearly not an approved exam device. | C | T |
| FR-TCH-003 | Share documents by file or by URL link (see FR-DOC-004, FR-DOC-007). No server. | S | D |

### 4.11 Installation and offline — M2e
| ID | Requirement | Pri | Ver |
|---|---|---|---|
| FR-PWA-001 | Installable PWA (manifest, icons, service worker). | M | E |
| FR-PWA-002 | Fully functional offline after offline setup completes, with no external network requests (Pyodide, wheels, CanvasKit, fonts all vendored). The app indicates readiness and reports failed setup; browser storage can be cleared or evicted. | M | E |
| FR-PWA-003 | Loading screen with progress during cold start. | M | D |
| FR-PWA-004 | App shows its version and offers update when a new service worker is available. | S | E |

### 4.12 Programming environments and later device profiles — M5, M8–M9
The last table of this section holds the CASSim Scientific requirements (FR-FX, the `scientific` device), which belong to no numbered milestone. M5 starts after the M0–M4 core page set; M6 extensions and M7 polish follow. Multi-device profile implementation remains M8–M9, with the M2 guard FR-DEV-007 and the device interface and bundle build (FR-PROF-001, FR-PROF-002, FR-PROF-008) already completed early through M2x. M5 adds only the minimal Nspire/Pseudocode selector needed for FR-RUN-009 and its own Code site; M8 generalises it into the lazy-loading profile switcher of FR-PROF-003 to FR-PROF-005. **Priorities confirmed 2026-11-02:** Python and pseudocode (Code view and page types) are Should; the ClassPad and the profile infrastructure that exists to serve it are Could; HP Prime is Would (not planned). Order: Code, TI-Basic/extensions, polish, then ClassPad and possibly HP. Question numbers refer to section 10. FR-PY-002 (the sandbox; no prompt since decision 0040) applies to every Python and pseudocode page, and the Python page itself is FR-RUN-010 (M5).

**Device profiles (M8)**
| ID | Requirement | Pri | Ver |
|---|---|---|---|
| FR-PROF-001 | Device-specific behaviour (input dialect, command catalogue and its behaviour differences, display conventions, settings and presets, document/page model, key layers, menu tree, keymap and skin, error table, corpus) is packaged as a **device profile**; common maths-engine pieces stay shared. | C | I |
| FR-PROF-002 | The TI-Nspire CX CAS is the first profile. Moving it onto the profile interface changes no behaviour: the full Nspire corpus replays unchanged and the coverage targets in NFR-MAINT-004 still hold. | M (conditional on FR-PROF-001) | T |
| FR-PROF-003 | The all-in-one app (the `all` bundle) switches between profiles at run time from a visible switcher. A single-device bundle has no switcher. | C | E |
| FR-PROF-004 | Each profile has its own documents, settings and theme namespace in browser storage; switching never mixes or overwrites another profile's data. Sharing data between profiles is not required [Q20]. | C | T |
| FR-PROF-005 | Profile assets (grammar tables, catalogue data, skins) load lazily and are cached for offline use on first use, so a user who only opens the Nspire profile does not download the others. Cold start and download size (NFR-PERF-001, -005) are reported per bundle. | C | A |
| FR-PROF-006 | Each profile declares its page/app types. Page types are registered, not hard-coded, so a type (Python, Pseudocode) can be offered by any profile that opts in [Q22]. | S | I |
| FR-PROF-007 | The display modes in 4.9 apply to every profile; Handheld mode uses the profile's own layout and artwork. A profile may need a touch-first interaction model [Q19]. | C | D |
| FR-PROF-008 | Each profile can be published as its own **bundle** on its own site, holding the shell and that one profile and nothing another profile needs (the pseudocode bundle ships no SymPy or SciPy). A profile is a plug-in package that imports the shared layers and never another profile; the build lists the profiles in a bundle. Single-device sites are published on a release only. | C | T |
| FR-PROF-009 | A document file and a share link carry the id of their profile. A bundle that holds that profile opens them; a bundle that does not names the site that does, links to it, and changes nothing. | C | T |
| FR-PROF-010 | The `all` bundle has a shell-level **Home** screen which owns no calculator document and is drawn without importing a device's Flet UI or engine. | C | E/I |
| FR-PROF-011 | Home displays an original CASSim icon and the exact message “Hi! Choose a CAS Calculator or other tool to start” | C | D/E |
| FR-PROF-012 | Home presents the choices **Nspire**, **Classpad**, **Prime**, **Pseudocode & Python** and **Scientific**, in that order, whether or not they are implemented or included in the build. | C | E |
| FR-PROF-013 | Only an implemented profile included in the bundle is enabled. An unavailable Home choice is greyed out and marked coming soon; pointer, keyboard and programmatic activation cannot open it. | C | E |
| FR-PROF-014 | Selecting an enabled choice mounts it. Every normal launch of the `all` bundle opens Home; no last-used device is remembered (revised 2026-11-21). | C | T/E |
| FR-PROF-015 | A direct app route (`#/app/<id>`) or a share link opens its bundled device; a route naming a device that is not bundled shows Home. | C | T/E |
| FR-PROF-016 | The CASSim menu has a **Home** action from every mounted app in the `all` bundle. It unmounts the app without discarding its saved document or settings. | C | E |
| FR-PROF-017 | Home has a CASSim Settings control which can change shell appearance without loading a device UI. Appearance is shared with the device system settings when the same setting is supported. | C | E |
| FR-PROF-018 | A single-device bundle mounts its one device directly and has neither Home nor an app chooser. | C | E |

**Python and pseudocode runtime (M5)**
| ID | Requirement | Pri | Ver |
|---|---|---|---|
| FR-RUN-001 | A language-neutral `Interpreter` interface: run source against an I/O context, stream output, accept input, report errors with line and column, and cancel. Python and pseudocode implement it, and so does the Nspire Python page (FR-RUN-010). | S | I/T |
| FR-RUN-002 | Python runs on CPython in Pyodide in a dedicated worker, separate from the CAS engine. Cancel terminates that worker within 1 s (NFR-PERF-004) and leaves CAS state intact. | S | T/E |
| FR-RUN-003 | Python environment: the standard library plus only the libraries that are needed (SymPy is shipped for the CAS; numpy and scipy are not assumed); plotting options are decided by a spike (Q21). User code has no network access and no access to the host page. How this is enforced is settled by a spike before the build; any gap that cannot be closed is documented in the SDD and told to the user before the build ships, since there is no run prompt (decision 0040). | S | T/E |
| FR-RUN-004 | The sandbox rule of FR-PY-002 applies to pseudocode as well as Python: Run runs at once, without a prompt (decision 0040); code from documents, imports or links never auto-runs (C-7, NFR-SEC-002). | M (conditional) | T/E |
| FR-RUN-005 | **Pseudocode** interpreter: own tokenizer, parser and interpreter (no regexes, no translation by string substitution) implementing the dialect in `docs/pseudocode/dialect.md` (VCAA pseudocode as extended by the author's conventions document); errors reported in pseudocode terms, not Python tracebacks; an execution-step limit that stops runaway programs with a clear message. | S | T |
| FR-RUN-006 | The golden programs in `corpus/pseudocode/seed.yaml` (VCAA and the author's examples, each with a reference Python translation and an expected output) are replayed in CI; known failures are `xfail(strict=True)` as for the CAS corpus (FID-3, FID-4). | S | T |
| FR-RUN-007 | Step-through or trace of a pseudocode run, with a variables panel, for teaching: specified in full by FR-TRC-001 to -008. | S | D |
| FR-RUN-008 | A shared editor and console component: line numbers, indentation, error highlighting, Run/Stop, adjustable text size, keyboard-only operation, usable at 360 px width; the settings bar of FR-SET-001 sits at the top of it. | S | D |
| FR-RUN-009 | **Code view**: standalone environment with no device skin; files, undo and download as in FR-EDT-001 to FR-EDT-004; imported files never auto-run. It is the `pseudocode` device: an entry in the all-in-one app's switcher (FR-PROF-003) and its own bundle and site (FR-PROF-008), with its own storage like any profile (FR-PROF-004) (Q23, revised 2026-11-13). | S | E |
| FR-RUN-010 | **Page types**: Python and Pseudocode pages can be added to a document in the Nspire profile (FR-DOC-005). Adding them bumps the document schema version with a migration (FR-DOC-004). | S | T |
| FR-RUN-011 | A script on a Python or Pseudocode page can read and write the Problem's variables and evaluate TI expressions through the `cassim` API of FR-PY-001, by name and without evaluating strings outside the engine's parser (NFR-SEC-004). The real TI-Nspire does not allow this, so it is a CASSim extension, scheduled after M5 and only if wanted. Until then the pages are self-contained. | C (later, after M5) | T |
| FR-RUN-012 | A **Stop** button is visible whenever code is running and stops the run within 1 s (NFR-PERF-004), keeping the output and trace so far. It works for pseudocode and Python and does not depend on the run limits of FR-SET-009. | S | T/E |

**Pseudocode language (M5)** — dialect in `docs/pseudocode/dialect.md`
| ID | Requirement | Pri | Ver |
|---|---|---|---|
| FR-PSE-001 | Data: integer, rational, real, complex and basic strings; booleans only as comparison results; function values as arguments; lists (FR-PSE-006). Tuples, sets and dictionaries are Could (FR-PSE-008) and until then produce a "not supported yet" diagnostic naming the construct. | S | T |
| FR-PSE-002 | Function parameters written `f(x)`; an argument may be an expression in that variable or the name of a defined function. **Both forms are required** (2026-11-04): the expression form `trapezium(f(x), x, a, b, n)` called with an expression and its variable, and the first-class form `trapezium(f, a, b, n)` with `f` defined first. Corpus and examples never use `lambda`. **Binding rule (Q40, decided 2026-11-04):** `f(x)` in the header declares `f` an expression in the variable named by the next parameter; the call's variable argument must name the variable the expression uses (a mismatch is an error naming both); inside the function `f(t)` evaluates the expression with that variable set to `t`; assigning to `x` inside the function is local. | S | T |
| FR-PSE-003 | Tolerant input, defined by the syntax file (FR-SYN-001): the default accepts case-insensitive keywords; `end` keywords decide structure while indentation is advisory; optional `then`, `do` and closing `end`; `=` or `<-` for assignment (with a warning); juxtaposed print items (with a warning); Unicode and ASCII operator spellings. Warnings never stop a run. | S | T |
| FR-PSE-004 | Diagnostics in pseudocode terms with line numbers, including a close-name suggestion for an undefined variable. | S | T |
| FR-PSE-005 | Built-ins: abs, sqrt, exp, loge, trigonometric functions honouring the angle setting, rounding, and seeded random functions. | S | T |
| FR-PSE-006 | Lists in pseudocode: literals `[1, 2, 3]`, `[]`, indexing `a[i]` and assignment to an element, `len(a)`, `Append x to a` / `append`, `Sum a`, `for each x in a`, and nested lists of numbers or strings (for tables and tallies). The index base is **1 by default** with a … menu toggle to 0, saved with the program (decided). Translation to Python adjusts indexing. | S | T |
| FR-PSE-007 | Random numbers: `rand()` (uniform on [0, 1)), `randint(a, b)` (inclusive) and `seed(n)`, as in the author's materials. A seed makes a run, its trace and its tests repeatable. Seeded runs reproduce CPython's `random` module exactly (MT19937 with CPython's seeding, `random()` and `randint`/`randrange` algorithms; decided), so seeded programs, including the author's `seed(42)` examples, have exact golden outputs; unseeded programs are tested by properties. A test compares the runtime against CPython for many seeds. | S | T |
| FR-PSE-008 | Could: sets and set builders (`{factors of c}`, `for each m ∈ A`, union, intersection, difference, power set), dictionaries, tuples and tuple return (VCAA `maximum_SA`), `∑` and derivative notation `x'(t)`, and printing of pairs `(t, x)`. | C | T |
| FR-PSE-009 | Could: random distributions beyond `rand` and `randint` (e.g. `rand_norm`), and Counter-style tallies. | C | T |
| FR-PSE-010 | Could: structured-English steps (prose pseudocode such as the middle-square description) can be written in a program; they are shown in the code pane and trace as comments and are never executed. | C | I |
| FR-PSE-011 | **Complex literals**: `1+2i`, `1+2ⅈ` and `complex(1,2)` are accepted (Q28, decided 2026-11-04). The Real/Complex domain is a setting in the … menu (FR-SET-003), Real by default. | S | T |
| FR-PSE-012 | **Symbolic (exact) pseudocode**, promoted from Could to Should on 2026-11-07: the Number mode control (FR-SET-001) works as on the CAS. **Approx** is numeric as now. **Exact** keeps `π`, `ⅇ`, surds, fractions and index forms unevaluated (`√2`, `π/6`, `2^(1/3)`, `3/4`), so `sqrt`, `exp`, `loge`, trigonometry of exact angles and the constants go through the engine (SymPy only inside `core/compat/sympy_adapter.py`) and stay exact through `+ − × ÷` and powers. **Auto** is exact when every input is exact and numeric as soon as a decimal enters (`0.5`, `rand()`, a float). Exact values show in trace cells, in `print` and in the translated Python's comment (the Python itself uses `sympy` when a program needs exact mode). Pure-integer programs are unchanged: `÷` of integers stays a real in Approx and a fraction in Exact and Auto, so Exact and Auto change `7/2` from `3.5` to `7/2`. Loop and `if` tests compare numerically. The default stays Approx in the standalone Code view, so every golden program is unchanged; Exact variants get their own corpus cases. | S | T |

**Translation between Python and pseudocode (M5)**
| ID | Requirement | Pri | Ver |
|---|---|---|---|
| FR-XLT-001 | Pseudocode to Python for the whole dialect, following the author's translation table (assignment, input, print, define/def, if/elif/else, while, for with step, repeat n times, repeat-until as `while True` with a break). Current settings are honoured (`Fraction` in Auto and Exact modes, `radians()` wrapping in Degree mode); `input` becomes a generated `read_value()` helper that infers number or string. Python to pseudocode is written in the style of the syntax file's emit section (FR-SYN-005). The Python is readable and idiomatic. | S | T |
| FR-XLT-002 | Python to pseudocode for the subset that has a pseudocode form: assignment, if/elif/else, while, for over `range`, functions, print, input, and `while True` with an `if c: break` as repeat-until; strings limited to concatenation, comparison and length (Q31, decided 2026-11-04). | S | T |
| FR-XLT-003 | Python outside that subset is refused with the line and construct named; the translator never guesses. | S | T |
| FR-XLT-004 | Semantic equivalence: for every golden program, the pseudocode run by CASSim's interpreter and the translated Python run by CPython agree (differential test; reals compared numerically, integers and strings exactly). | S | T |
| FR-XLT-005 | Round trip: pseudocode to Python to pseudocode gives an equal program tree (comments and layout aside), property-tested on generated programs. | S | T |
| FR-XLT-006 | Names that clash with Python built-ins or keywords (`sum`, `list`, `lambda`, ...) are renamed in the translation, with a comment. | S | T |

**Stepwise trace tables (M5)** — layouts in `docs/pseudocode/trace-tables.md`
| ID | Requirement | Pri | Ver |
|---|---|---|---|
| FR-TRC-001 | Any run (pseudocode, or Python in the supported subset) records its events so the user can step forwards and backwards, return to the start, run to the end and jump to any row, without re-executing (random numbers and input replay identically). | S | T/E |
| FR-TRC-002 | **Vertical** layout: one row per executed line; columns for line number, variables (a value shown on the row where it changes), evaluated conditions, and calculations/output; repeated lines repeat their numbers. | S | T/D |
| FR-TRC-003 | **Horizontal** desk-check layout: the code down the left, an Init column then one column per loop pass, values substituted, ✔/❌ for conditions, "(skip)" for branches not taken, final output in the last column. Offered when the run has exactly one loop and no nesting. | S | T/D |
| FR-TRC-004 | Layout choice: Auto (horizontal when eligible, otherwise vertical) with a manual switch; switching never re-runs and keeps the cursor. | S | T |
| FR-TRC-005 | The run limits of FR-SET-009 (visible, adjustable maximum loop iterations and recursion depth) stop infinite loops; the recorded trace stays steppable and ends in a "stopped after N steps" row. Memory use of the record is bounded and the cap is shown. | S | T |
| FR-TRC-006 | The code pane highlights the current line; a variables panel shows all variables at the cursor; rows after the cursor are hidden until reached, with "show all". | S | D |
| FR-TRC-007 | The same trace engine serves Python in the supported subset (through the shared program tree), so Python and pseudocode give the same table for a translated program. | S | T |
| FR-TRC-008 | Trace cell values follow the settings (Exact/Approx, angle, display digits). | S | T |
| FR-TRC-009 | Fill-in mode: a blank table the student completes, with per-cell checking against the recording. | C | D |
| FR-TRC-010 | Export a trace as CSV, Markdown or an image. | C | D |
| FR-TRC-011 | A third, per-iteration view (one row per loop pass, variables as columns), after the vertical and horizontal views are done (Q33, decided 2026-11-04). | C | D |
| FR-TRC-012 | Line-by-line variable trace for Python outside the supported subset. | C | D |
| FR-TRC-013 | In the vertical layout a call to a function defined in the code is one row, which opens a modal window that can be moved and resized: the function's code (highlighting the current line) beside that call's own trace (its variables as resizable columns, Step / First / Last, rows up to the cursor), stacked in one column when the window is narrow; its starting values are in the title. A call made inside it opens the same way (added 2026-11-22). | S | T |

**Settings bar (M5)**
| ID | Requirement | Pri | Ver |
|---|---|---|---|
| FR-SET-001 | The Code view's editor has a clear settings bar at the top with two controls, **Number mode** (Approx / Auto / Exact) and **Angle** (Radian / Degree), plus a **…** menu that holds every other setting (FR-SET-003, FR-SET-006, FR-SYN-003). The controls are always visible, show the current state, and are saved with the program. | S | D |
| FR-SET-002 | The settings apply to pseudocode runs, traces and translation (dialect.md section 8). A Python run executed directly by CPython cannot honour them: the affected toggles are shown disabled with the reason, never silently ignored. | S | T/D |
| FR-SET-003 | Further settings, in the **…** menu, each Could: Real/Complex domain (Real by default, so `sqrt(-4)` is an error; Complex gives `2ⅈ`), Gradian, random seed. (The step limit is now FR-SET-009.) | C | T |
| FR-SET-004 | On a Nspire Python or Pseudocode page the bar starts from the document's settings (FR-EVAL-002) and can be overridden for that page. | S | T |
| FR-SET-005 | VCE course presets (General, Methods, Specialist; FR-EVAL-003) as a one-click preset on the bar. | C | T |
| FR-SET-006 | Printed real numbers show **6 significant digits** by default (Mathematica style; trailing zeros dropped), adjustable in the … menu (Fix n, Full). Integers and rationals always print exactly. The display never changes the stored value. It applies to pseudocode output and trace cells; a Python run by CPython prints natively. A real with a whole value prints with a trailing point (`5.`), as in Mathematica, so it differs from the integer `5`; this is display only. | S | T |
| FR-SET-007 | **Print ends the line** by default. The … menu (and the syntax file, `print.end`) can change what `print` appends after its output: new line (default), a space, or nothing. The setting applies to the whole program; it cannot express the author's book convention (one `print` of a string followed by a second `print` joined onto the same line), which should be written as a single `print`. Saved with the program. | S | T |
| FR-SET-008 | **Euler's number toggle** in the … menu: when on, an unassigned `e` is the constant 2.71828… (and `e^x` reads naturally); when off, `e` is an ordinary name. A variable the program assigns always shadows the constant either way, so `e ← 0.001` is safe. Saved with the program alongside the number mode and angle. **Default: on** (decided 2026-11-06, revising Q39). | S | T |
| FR-SET-009 | **Run limits** in the … menu, low by default and user-adjustable: a maximum number of passes for any one loop run and a maximum recursion depth. Reaching either stops the run with a clear message naming the limit, the line and the setting to change it, keeps the output so far, and leaves the trace steppable (FR-TRC-005). Applies to pseudocode and, where CPython allows, to Python runs. **Defaults: 1,000 passes per loop, 20,000 recorded trace steps and recursion depth 100** (decided 2026-11-06, revising Q39). | S | T |

**Configurable syntax (M5)** — default in `docs/pseudocode/syntax-default.yaml`
| ID | Requirement | Pri | Ver |
|---|---|---|---|
| FR-SYN-001 | The pseudocode syntax is defined by a **syntax file**, not hard-coded: keyword and symbol spellings, which tokens are optional, how each block may end, comment markers, and the style the printer writes. The built-in default accepts every spelling in `docs/pseudocode/dialect.md`. | S | T |
| FR-SYN-002 | The same construct can be written several ways, and each spelling can be set to accepted, accepted with a warning, or rejected. Must work: `if` with `then` required, optional or forbidden; a `for` loop ending with `end for`, `endfor` or `next` (with or without the variable); a function ending with `end`, `end define`, `end function` or a dedent. | S | T |
| FR-SYN-003 | The file is stored in browser storage per profile, editable in the app (… menu, Syntax) with validation, a live check against a sample program, reset to default, and export/import as a file. An invalid file falls back to the default with a message (as FR-THEME-002). | S | T/D |
| FR-SYN-004 | Validation rejects files that make the grammar ambiguous or contradictory: one spelling mapped to two constructs, a bare `end` accepted for several constructs without the innermost-block rule, no spelling left for a required construct. A new reserved word that collides with a name in the user's saved programs is reported. The message names the entry at fault. | S | T |
| FR-SYN-005 | The file's **emit** section controls what the printer writes (Python to pseudocode, formatting, examples): keyword case (lower, UPPER, Capitalised), indent width, terminator spellings, whether `then` and `do` are written, the assignment, multiplication and division symbols, and the comment marker. | S | T |
| FR-SYN-006 | Code is displayed exactly as the user typed it; the code pane and trace tables refer to the user's own lines and never show a normalised reprint. | S | T/D |
| FR-SYN-007 | Property tests: for every built-in preset and for generated valid syntax files, printing a program tree in that file's style and parsing it again gives the same tree; every golden program survives restyling under every built-in preset. | S | T |
| FR-SYN-008 | Built-in presets: Default (tolerant), VCAA, the author's conventions, and Strict (one spelling per construct, warnings become errors). A user's file starts as a copy of a preset. | C | D |
| FR-SYN-009 | The file is data only (no code, no regular-expression hooks), schema-validated and size-limited on import (NFR-SEC-003). A program shared by file or link may carry its non-default syntax settings; opening it asks first and never changes the viewer's own file (decided 2026-11-02). | S | T |
| FR-SYN-010 | **Regularise** button in the editor toolbar. It takes a program whose syntax is unambiguous under the current syntax file but not in the standard style (for example `=` for assignment, keyword case, `endfor` or `next` instead of `end for`, a missing `then`, `define` versus `function`, juxtaposed print items, an unclosed inner block that an outer closer ends) and rewrites it in the standard in use: the emit section of the syntax file (FR-SYN-005) or a preset chosen in the button's menu. It shows a before/after diff and applies on confirmation as a single undo step (FR-EDT-001). Comments, blank lines and meaning are preserved. It refuses, with the reason and line, when the program is ambiguous or has errors, and never guesses. Tests: the program tree is unchanged by regularising; regularising twice changes nothing; property-tested across every preset and generated syntax files; every golden program, deliberately mis-styled, regularises to its canonical form. Python programs use the same button to apply a consistent layout (indentation, spacing) without changing the tree. | S | T |
| FR-SYN-011 | **Symbol equivalents.** Wherever the language has a mathematical symbol, the ASCII spelling and the Unicode symbol are interchangeable on input, in any mix, each marked ok, warn or no in the syntax file. The default table: `<-` `:=` `←`; `*` `×` `·`; `/` `÷`; `<=` `≤`; `>=` `≥`; `!=` `<>` `≠`; `sqrt(x)` `√(x)` `√x`; `pi` `π`; `inf` `∞`; `abs(x)` `|x|`; `x^2` `x**2` `x²` (integer exponents of the form `^n`, `^-n` and `⁻ⁿ` superscripts); `and` `∧`; `or` `∨`; `not` `¬`; `-` `−` `–`; `ln` `loge`. Strings and comments are never reinterpreted. | S | T |
| FR-SYN-012 | **Convert symbols** button (toggle) in the editor toolbar: rewrites the selection, or the whole program, to Unicode symbols or to ASCII, and a second press converts back. It works on tokens from the tokenizer, never by text search, so strings, comments and names are untouched; a user variable that happens to be called `pi` is left alone and reported. It previews the change as a diff, applies as one undo step (FR-EDT-001), keeps the program tree unchanged, and is idempotent (property-tested: ASCII to Unicode to ASCII returns the original for programs written in the standard ASCII spellings). The target style also feeds Regularise (FR-SYN-010) and the printer's emit section as `symbols: unicode | ascii | keep` (FR-SYN-005). Superscript conversion applies only to integer-literal exponents; `x^(n+1)` stays as typed. | S | T |
| FR-SYN-013 | Typing aid (setting, off by default): as the user types, unambiguous multi-character ASCII sequences become symbols (`<-` to `←`, `<=` to `≤`, `>=` to `≥`, `!=` to `≠`) and a LaTeX-style `\pi`, `\sqrt`, `\le`, `\ge`, `\theta` followed by space or Tab becomes its symbol. Plain words such as `pi` or `sqrt` are never auto-replaced while typing (they may be names); that is what FR-SYN-012 is for. Each replacement is undoable on its own. | C | T |

**Code editor: undo, files, download (M5)** — applies to the shared editor (FR-RUN-008) in the Code view and on Nspire Python and Pseudocode pages
| ID | Requirement | Pri | Ver |
|---|---|---|---|
| FR-EDT-001 | **Unlimited undo and redo** per file: no fixed depth, Ctrl/Cmd+Z, Shift+Ctrl/Cmd+Z and Ctrl+Y, plus toolbar buttons. History is stored compactly (as diffs, with typing coalesced into word-sized steps) and Regularise, Translate, paste, Open and Revert each form one step. Undo never touches output or trace results, which are marked stale instead. The history survives reload and crash where storage allows, is kept per file, and is trimmed oldest-first only when the storage quota is reached, with a visible message and never silently. | S | T/D |
| FR-EDT-002 | **Save to browser storage**: named files in IndexedDB, available in the Code view and from Python and Pseudocode pages: list, open, new, save, save as, rename, duplicate and delete (with confirmation). Unsaved edits autosave as a draft and are recovered after reload or crash (FR-DOC-003). Each file records its language, its list index base and any non-default syntax or settings overrides (FR-SYN-009). A quota warning is shown before saves fail, with a link to export everything. | S | T/D |
| FR-EDT-003 | **Download and upload**: download the current file, or all files as one archive, as plain text with the extension `.py` for Python and `.pseudo.txt` for pseudocode (decided 2026-11-02; opens in any text editor, and the app also accepts `.pseudo` and `.txt` on upload); uploading or dropping a file adds it to the list. The header carrying settings and syntax overrides is a comment block so the file still reads, and runs as Python, elsewhere. Downloads work offline and use the platform's save mechanism, with a fallback on browsers lacking one. | S | T/D |
| FR-EDT-004 | Uploaded or imported files, and files arriving in a shared document or link, are opened but never run until the user chooses Run (FR-RUN-004, C-7, NFR-SEC-002). Overrides in the header are shown and need acceptance (FR-SYN-009). File size and name length are limited and names are sanitised. | S | T |
| FR-EDT-005 | Undo history and files are exported and restored with the rest of the user's data (FR-DOC-004 backup), so clearing the browser is recoverable from a backup file. | C | T |
| FR-EDT-006 | **Symbol palette**: a button opens a panel of tappable symbols that insert at the cursor (or wrap the selection), so students on a phone or a plain keyboard can enter them. Groups: arithmetic and relations (`× ÷ ± ≤ ≥ ≠ ← ≈`), powers and roots (`² ³ ⁿ ⁻¹ √ ^ π e ∞`), logic (`∧ ∨ ¬`), bars and brackets (`|x| ( ) [ ]`), Greek letters (`θ α β` and so on), a Recently used row, and keyword templates (`if`, `for`, `while`, `repeat`, `define`) that insert a block in the user's own syntax style. Each button shows its ASCII equivalent and keyboard shortcut on hover or long press. The contents come from the syntax file (only symbols the current syntax accepts are shown). Keyboard operable, at least 44 px targets, usable at 360 px, and a Python editor gets an ASCII-only variant (`**`, `//`, `%`, `!=`, `<=`). | S | T/D |

**Casio ClassPad (M8)**
| ID | Requirement | Pri | Ver |
|---|---|---|---|
| FR-CPD-001 | A ClassPad profile with its own dialect, catalogue (Tier 1 VCE core first, tiers as in FR-CAT-001 to -003), settings presets, display conventions and error table, each pinned by a corpus captured from the oracle [Q17]. Nothing is inherited from the Nspire profile unless the corpus confirms it. | C | T |
| FR-CPD-002 | The corpus lives in `corpus/classpad/` with the same provenance, status and `xfail(strict=True)` rules as FID-3 and FID-4; Tier 1 passes (canonical) before any exact-text work. | C | T |
| FR-CPD-003 | App/page set as the oracle shows it (calculation, graph and table, statistics, spreadsheet) [TBC], reusing the shared sheet, stats and graph engines through the profile. Geometry is excluded. | C | T/D |
| FR-CPD-004 | Handheld skin and keypad (or touch interface, per Q19): key layout and labels match the device; the artwork is CASSim's own and not traced (decision 0028). | C | D |
| FR-CPD-005 | VCE setting presets for Methods, Specialist and General, and scripted exam-style flows, as for the Nspire. | C | T/E |

**HP Prime (M9, optional)**
| ID | Requirement | Pri | Ver |
|---|---|---|---|
| FR-HPP-001 | A go/no-go review after M8 against oracle availability and terms [Q18], the actual effort of M8, and demand. Nothing else in this specification depends on a "go". | W | I |
| FR-HPP-002 | If go: an HP Prime profile built by the same recipe as FR-CPD-001 to -005, with its programming language handled as a separate dialect on the FR-RUN-001 interface if wanted. | W | T |

**CASSim Scientific (SDD-14; added 2026-11-25)**
The `scientific` device (FR-PROF-012). The device as a whole is Could; the priorities below rank its parts. Details, the keypad and the keyboard map are in `docs/design/SDD-14-scientific-calculator-fx.md`.
| ID | Requirement | Pri | Ver |
|---|---|---|---|
| FR-FX-MOD-001 | Support `COMP` mode (Mode 1) for general arithmetic, functions, fraction simplification, and trigonometry. | M | T/E |
| FR-FX-MOD-002 | Support `STAT` mode (Mode 2) with 1-variable (`1: 1-VAR`) and 2-variable regression options (`2: A+BX`, `3: _+CX^2`, `4: ln X`, `5: e^X`, `6: A*B^X`, `7: A*X^B`, `8: 1/X`). | M | T/E |
| FR-FX-MOD-003 | Support `TABLE` mode for generating a table of values for $f(x)$ given Start, End, and Step parameters. It is a CASSim extra, off until Settings ▸ CASSim extras switches it on, because the fx-82AU PLUS II and SX-II have no TABLE mode; when on it is Mode 4 (decision 0041, 2026-11-27). | M | T/E |
| FR-FX-MOD-004 | Support `VERIFY` mode (Mode 3, listed as `VERIF`) evaluating relational equality/inequality expressions to `TRUE` or `FALSE` (Mode 3 per the fx-82AU PLUS II manual and emulator; decision 0041). | S | T/E |
| FR-FX-MOD-005 | (fx-100 extension) Support `CMPLX` mode (Complex numbers $a+bi$ and $r\angle\theta$) and `VECTOR` mode (2D/3D vectors). | C | T |
| FR-FX-CFG-001 | Support Setup selection of display format: `MthIO` (MathO natural output or LineO linear output) vs `LineIO`. The default after a reset is MthIO-LineO on the fx-82 and SX-II: an answer is a decimal first unless the entry has a fraction (decision 0041). | M | T/E |
| FR-FX-CFG-002 | Support Angle unit configuration: Degrees (`Deg`), Radians (`Rad`), Gradians (`Gra`). Active unit indicated on screen annunciator. | M | T/E |
| FR-FX-CFG-003 | Support Numerical display rounding modes: `Norm 1` / `Norm 2` (exponential threshold), `Fix 0..9` (fixed decimal places), `Sci 0..9` (scientific significant figures). | M | T/E |
| FR-FX-CFG-004 | Support Fraction result format: Mixed number $a\frac{b}{c}$ vs Improper fraction $\frac{d}{c}$. | M | T/E |
| FR-FX-CFG-005 | Support `STAT` frequency table toggle in Setup (`Shift+MODE` $\to$ `▼` $\to$ `STAT` $\to$ `1: ON`, `2: OFF`). | M | T/E |
| FR-FX-CFG-006 | Support Initialisation/Reset via `Shift+9 (CLR)` with options: `1: Setup`, `2: Memory`, `3: All`. Reset restores factory defaults and clears memories. | M | T/E |
| FR-FX-CFG-007 | **Exact surds and π** (a CASSim extra, off by default): in MathO, answers with square roots (up to two terms) and multiples of π are shown exactly, as the more advanced scientific calculators do (fx-8200 AU, fx-991ES PLUS, HP 300s+, TI MultiView). The four calculators behind the layouts show them as decimals. Saved with the calculation (decision 0041). | S | T |
| FR-FX-DSP-001 | Screen simulates a two-line LCD: a natural-display input line and an answer line, with the whole calculator scaled to fit the window. | M | E/D |
| FR-FX-DSP-002 | Render top annunciator status icons: `S` (Shift), `A` (Alpha), `M` (Independent memory active), `STO` (Store), `RCL` (Recall), `STAT` (Stat mode), `D`/`R`/`G` (Angle unit), `FIX` (Fixed d.p.), `SCI` (Scientific), `Math` (MthIO active), `▲▼` (Replay history available); and CASSim's own `hyp` while hyp waits (FR-FX-UI-008). | M | E/I |
| FR-FX-DSP-003 | Natural input editing: fractions $\frac{\Box}{\Box}$, mixed numbers $\Box\frac{\Box}{\Box}$, square root $\sqrt{\Box}$, cube root $\sqrt[3]{\Box}$, $n$-th root $\sqrt[\Box]{\Box}$, power $x^\Box$, absolute value $\|\Box\|$, logarithmic with base $\log_{\Box}(\Box)$. | M | T/E |
| FR-FX-DSP-004 | 4-way D-pad navigation: cursor movement through slots and nested templates, history navigation (`▲`/`▼`), and multi-statement browsing. | M | T/E |
| FR-FX-DSP-005 | `S⇔D` button toggles result between exact form (a fraction; a surd or $\pi$-multiple with FR-FX-CFG-007 on) and decimal representation. | M | T/E |
| FR-FX-DSP-006 | `Shift + S⇔D` toggles between mixed number ($a\frac{b}{c}$) and improper fraction ($\frac{d}{c}$). | M | T/E |
| FR-FX-DSP-007 | `ENG` key adjusts decimal exponent down by 3 ($10^{-3}, 10^{-6}$); `Shift + ENG` ($\leftarrow$) adjusts exponent up by 3 ($10^3, 10^6$). | M | T |
| FR-FX-DSP-008 | DMS key (`° ' "`) inputs sexagesimal angles and converts decimal degrees to degrees, minutes, and seconds on result. An entry of sexagesimal values joined by + − × ÷ answers in degrees, minutes and seconds. | M | T |
| FR-FX-DSP-009 | `Shift + ° ' "` (`FACT`) performs prime factorisation of integer results (e.g. $1050 \to 2 \times 3 \times 5^2 \times 7$). | M | T |
| FR-FX-MEM-001 | Automatic `Ans` register stores the result of the last completed calculation and updates on `=`. | M | T |
| FR-FX-MEM-002 | 9 variable registers: `A, B, C, D, E, F, M, X, Y`. Stored via `Shift+RCL (STO)` + variable key; recalled via `RCL` + key or typed via `ALPHA` + key in expressions. | M | T |
| FR-FX-MEM-003 | Independent memory `M`: `M+` adds current value to $M$; `Shift+M+ (M-)` subtracts current value from $M$. Annunciator `M` lights when $M \ne 0$. | M | T |
| FR-FX-MEM-004 | (fx-100 extension) `PreAns` memory holds the second-to-last answer for recurrence relations. | C | T |
| FR-FX-FNC-001 | Standard trigonometry: $\sin, \cos, \tan$ and inverses $\sin^{-1}, \cos^{-1}, \tan^{-1}$ respecting active angle unit (`Deg`, `Rad`, `Gra`). | M | T |
| FR-FX-FNC-002 | Hyperbolic functions via `hyp`: $\sinh, \cosh, \tanh, \sinh^{-1}, \cosh^{-1}, \tanh^{-1}$. | M | T |
| FR-FX-FNC-003 | Powers and roots: $x^2, x^3, x^{-1}, x^y, \sqrt{\Box}, \sqrt[3]{\Box}, \sqrt[y]{x}$. | M | T |
| FR-FX-FNC-004 | Logarithms and exponentials: natural $\ln, e^x$, common $\log, 10^x$, and arbitrary base $\log_a(b)$. | M | T |
| FR-FX-FNC-005 | Combinatorics & Probability: Permutations $n\text{Pr}$, Combinations $n\text{Cr}$, Factorial $n!$, Random decimal $\text{Ran\#} \in [0, 1)$, Random integer $\text{RanInt\#}(a, b) \in [a, b]$. | M | T |
| FR-FX-FNC-006 | Coordinate conversions: $\text{Pol}(x, y)$ returns $(r, \theta)$ with $r$ in $X$ and $\theta$ in $Y$; $\text{Rec}(r, \theta)$ returns $(x, y)$. | M | T |
| FR-FX-FNC-007 | Number theory: $\text{GCD}(a, b)$ (Greatest Common Divisor) and $\text{LCM}(a, b)$ (Least Common Multiple). | M | T |
| FR-FX-FNC-008 | Percent calculations (`%`): basic percent, percentage increase, percentage decrease, each in the chosen calculator's own way: on the fx-82 and SX-II `%` divides by 100 (an increase is typed `250+250×15%`); on the EL-531 and 10s `+` and `−` add or take off the percentage (decision 0041). | M | T |
| FR-FX-FNC-009 | Rounding function `Rnd(x)`: rounds argument to current display precision (`Fix` or `Sci`). | M | T |
| FR-FX-STA-001 | Data entry grid: 1-VAR single column (or two-column with FREQ enabled); 2-VAR bivariate two-column (X, Y) (or three-column with FREQ). | M | T/E |
| FR-FX-STA-002 | Single-variable summary statistics: $n, \bar{x}, \sum x, \sum x^2, s_x, \sigma_x$. | M | T |
| FR-FX-STA-003 | 5-number summary: $\min X, Q_1, \text{med}, Q_3, \max X$. Quartiles strictly computed using TI/Australian school median-split convention (median excluded when $n$ is odd). | M | T |
| FR-FX-STA-004 | Bivariate linear regression: $y = A + Bx$, calculating $A$ (intercept), $B$ (gradient), Pearson's correlation coefficient $r$. | M | T |
| FR-FX-STA-005 | Regression estimation: predicting $\hat{x}$ for given $y$, and $\hat{y}$ for given $x$. | M | T |
| FR-FX-STA-006 | Statistical variables menu (`Shift+1 (STAT)`): `1: Type`, `2: Data`, `3: Sum`, `4: Var`, then `5: MinMax` for 1-VAR, or `5: Reg`, `6: MinMax` for the two-variable types (order corrected 2026-11-25; SDD-14 section 4.2). | M | T/E |
| FR-FX-TUT-001 | **User-Driven Execution**: The tutorial does not lock the keypad or advance on an automatic timer. The user must press the highlighted key or enter the required input on the keypad (or the computer keyboard) to progress. | M | E/D |
| FR-FX-TUT-002 | **Spotlight & Hinting**: The target key is outlined with a calm accent glow. When a multi-key sequence is required (e.g. `Shift` then `MODE`), the immediate next key is highlighted. | M | E/D |
| FR-FX-TUT-003 | **Validation & Error Correction**: If the student presses an incorrect key, the system gives an immediate non-punitive hint naming the right key, and the wrong key does not change the calculator. | M | E/D |
| FR-FX-TUT-004 | **Step-by-Step Explanation**: Each step shows the key to press, the reason for it, and what the screen should then show (computed by running the lesson, never written by hand). | M | E/I |
| FR-FX-TUT-005 | **Three Instructional Modes**: <br>1. *Guide Me (Interactive)*: Step-by-step user-driven execution with key highlights.<br>2. *Show Me (Demonstration)*: Automated playback at 0.5×–2× for a stuck student or a whiteboard.<br>3. *Test Me (Challenge)*: Practical problem prompt with key highlights disabled; verifies the student's final screen and result. | M | E/D |
| FR-FX-TUT-006 | **Offline & Private**: Tutorials and student progress run 100% locally in browser storage without network calls or telemetry. | M | T |
| FR-FX-SHR-001 | **Automatic Browser Persistence**: Calculator state is saved to browser storage (the shell's storage, under the device prefix `scientific.`) shortly after each key press. On reload the mode, settings, variables, STAT data, table and recent history are restored. A tutorial never overwrites the student's own saved work. | M | T/E |
| FR-FX-SHR-002 | **URL Fragment State Sharing**: The calculator is serialised as a CASSim document naming the device, compressed with zlib and URL-safe Base64 into the shared `#/doc=` fragment (decision 0032 item 4). Loading a share link recreates the calculator; the shell routes it to CASSim Scientific by its `device`. | M | T/E |
| FR-FX-SHR-003 | **Privacy by Construction**: The shared state payload resides strictly in the URL fragment (`#...`), which web browsers never send to an HTTP server (NFR-SEC-001). No student data or teacher problem data is ever uploaded or logged. A link holds key names and numbers only; nothing in it is executed. | M | I/T |
| FR-FX-SHR-004 | **Compact Link Budget**: A typical calculator link is 80–300 characters, well within the 2,000-character ceiling (`MAX_FRAGMENT`); history is left out of links and default settings are omitted. | M | T |
| FR-FX-SHR-005 | **Teacher Pre-Populated Problem Sets**: Teachers can share a single link that pre-loads a data set (e.g. a 25-row bivariate table) or a TABLE-mode function, so students begin solving immediately. | S | D/E |
| FR-FX-SHR-006 | **Named calculations**: Doc ▸ Save, Save as and Open keep calculations by name in the app's storage, as in every CASSim app (FR-DOC-010); Open lists them and each can be deleted, and Open and Import ask before dropping unsaved changes. Doc ▸ Import file… and Export file… read and write `.cassim.json`, the one CASSim file format (FR-DOC-004). Changed 2026-11-25: Save and Open used to download and pick files. | S | T/E |
| FR-FX-UI-001 | **Top bar**: the CASSim and Doc menus of every CASSim app (section 5.1) and status chips for the mode, angle unit and input mode, readable in every theme. Clicking a chip opens MODE, changes the angle unit, or switches MthIO/LineIO. | M | T/E |
| FR-FX-UI-002 | **Presentation mode**: the top bar can be hidden; a floating button or Esc brings it back. | S | T/E |
| FR-FX-UI-003 | **Tutorial panel**: quiet styling, a step counter, the instruction and reason, the expected screen, and a close button; it sits beside the calculator, or below it when the window is narrow. CASSim ▸ Show tutorials / Hide tutorials shows or hides it on every screen size. | S | T/D |
| FR-FX-UI-004 | **Computer keyboard**: every key can be reached from the computer keyboard (section 4.1): digits and operators directly, common functions by letter, SHIFT and ALPHA as F1 and F2, MODE as Ctrl+M. Each keypad key's tooltip names its shortcut, and CASSim ▸ Keyboard shortcuts lists them. Keyboard input is ignored while a dialog is open. | M | T/E |
| FR-FX-UI-005 | **Calculator layouts**: CASSim ▸ Appearance ▸ Calculator shows the keys of a chosen class of school calculator (Casio fx-82 series, the default; Abacus SX-II series; Sharp EL-531 series; HP 10s series): their names, legends, SHIFT and ALPHA key names and arrangement, in CASSim's own artwork and fonts. The maths behind the keys is the same, but the key sequences are that calculator's own (its MODE and SETUP menus, CLR, STAT data entry and recall, %, fraction keys), so teachers can demonstrate and students can learn their device. A layout lists only the modes that calculator has and starts from its default SETUP, and its lessons are written in its keys; a lesson for something it lacks (TABLE unless that extra is on, quartiles, FACT) is not offered. The choice is remembered. | S | T/E |
| FR-FX-UI-006 | **fx-100 series layout** (Could; deferred 2026-11-25): a Casio fx-100 series layout (the fx-100AU class), with its keypad and key sequences, whose MODE menu reaches CMPLX and VECTOR (FR-FX-MOD-005). None of the four current calculator classes has those modes, so they wait for this layout. | C | T/E |
| FR-FX-UI-007 | **Phones**: on a phone-sized window (a short side under 600 px, as the Nspire app) the calculator fills the width and its keys grow taller to use the height, the tutorial panel starts hidden, and the menu bar keeps the model and mode chips. Every dialog fits the screen. In the installed app, CASSim ▸ Avoid cutout / Use cutout keeps the calculator clear of the camera cutout, as in the Nspire app. | S | T/E |
| FR-FX-UI-008 | **hyp shows that it is waiting**: after hyp (its menu on the fx-82 and SX-II, a prefix on the 10s and EL-531) the hyp key is lit, a `hyp` mark shows, and sin, cos, tan and their SHIFT legends read sinh, cosh, tanh; a trig key then picks that function, and hyp pressed again cancels. A learning aid, on by default; Settings can turn the names off (decision 0041). | S | T/E |

---

## 5. Non-functional requirements

### 5.1 Performance
| ID | Requirement | Pri | Ver |
|---|---|---|---|
| NFR-PERF-001 | Cold start (no cache) has no hard limit (baseline 15 s vendored, 35 s CDN); it is measured and reported, and shows a progress screen. | C | A |
| NFR-PERF-002 | Warm start (cache populated) is noticeably faster than cold start; measured and tracked, no fixed target. | S | A |
| NFR-PERF-003 | Typical Tier 1 operation (solve, factor, diff, integrate) returns in <= 1 s after import; a slower operation is shown as busy. | S | A |
| NFR-PERF-006 | Switching pages draws the new page from what the UI already holds and does not wait for the engine. The time from the key press to the page drawn is measured and reported (`tools/switchtime.py`); the aim is 100 ms on a desktop and 250 ms on a mid-range phone, with no fixed limit. | S | A |
| NFR-PERF-007 | In an `all` bundle, Home can render before any device UI, device assets or engine worker starts. A device's UI and worker begin loading only when that device is selected or named by a direct route or share link. | C | A/E |
| NFR-PERF-004 | UI remains responsive during evaluation; Cancel takes effect within 1 s. | M | E |
| NFR-PERF-005 | Total download is measured and reported. Baseline 22 MB (CDN) / 95 MB (vendored); no fixed budget. | C | A |

### 5.2 Reliability and data safety
- NFR-REL-001 (M) No data loss on reload, crash or worker restart: document state is restorable from storage.
- NFR-REL-002 (M) A worker kill (cancel) restores the document's variables and settings.
- NFR-REL-003 (S) Autosave failure (quota/blocked storage) is reported and export is offered.

### 5.3 Security and privacy
- NFR-SEC-001 (M) No server component; **no telemetry or analytics of any kind**; no student data leaves the device. Share links carry data in the URL fragment, which browsers do not send to servers.
- NFR-SEC-002 (M) User Python and pseudocode run in a sandbox that cannot reach the network, the page, storage or the computer (decision 0040: CASSim's own interpreter, no permission prompt); imported documents and share links never auto-run code (Python, pseudocode or programs).
- NFR-SEC-003 (M) Imported `.cassim.json` files and share links are schema-validated and size-limited; malformed input is rejected without side effects.
- NFR-SEC-004 (S) No eval of document-supplied strings outside the engine's parser/interpreter.

### 5.4 Usability and accessibility
- NFR-USE-001 (M) Keystroke-for-keystroke workflows match the handheld where the key exists.
- NFR-USE-002 (S) Accessibility is Should-have, applied where cheap. Keyboard-only operation in Computer mode and visible focus are required. Screen-reader support is hard because Flet renders to a canvas: where it is not easy, the gap is flagged in `docs/accessibility.md` and stubbed (labels and semantics hooks in place, behaviour to follow), not silently skipped.
- NFR-USE-003 (S) Adjustable text size; built-in themes meet WCAG AA contrast.
- NFR-USE-004 (C) Localisation-ready strings (English first).

### 5.5 Portability and compatibility
- NFR-PORT-001 (M) **Primary** test targets: Chromebooks (ChromeOS), Chrome, Safari (macOS, iOS, iPadOS). Every release is tested on these. **Secondary** (best effort, smoke-tested): Edge, Firefox.
- NFR-PORT-002 (M) Touch, mouse and hardware keyboard.
- NFR-PORT-003 (S) Handheld mode usable at 360 px wide and in both orientations.
- NFR-PORT-004 (W) Native builds of the same app with `flet build`: Windows, macOS and Linux desktop, and Android (APK, AAB) and iOS. The static web site is the only release target until M7 is done; see PLAN.md section 13 for what each build needs.

### 5.6 Maintainability and quality
- NFR-MAINT-001 (M) Ruff clean; Ty strict on `core/`; the checks (lint, types, tests with coverage, traceability, web build, Playwright) green before merge. They run locally as `tools.local_ci` before a branch merges, and once on GitHub Actions for each batch pull request (AGENTS.md, "Development workflow").
- NFR-MAINT-002 (M) Core never imports Flet (lint rule); SymPy only in the adapter.
- NFR-MAINT-003 (M) Conventional commits; small commits; decisions recorded in `docs/decisions/`.
- NFR-MAINT-004 (S) Line and branch coverage of at least 90% on `src/cassim/core/` and 80% on the other non-UI packages (`device`, `doc`, `sheet`, `stats`, `graph`). `cassim.app` (Flet UI) is excluded and covered by Playwright. The checks fail when a package falls below its floor in `pyproject.toml` (`[tool.cassim.coverage]`, checked by `tools/coverage_check.py`): 90 for `core`, `runtime` and `cli`; 80 for `device`, `devices`, `doc`, `sheet`, `stats` and `graph`. Device UI packages (`devices/*/ui`) are excluded with `cassim.app`.
- NFR-MAINT-006 (M) Every requirement ID appears in at least one test (marker or docstring) or is listed as untested with a reason. A generated traceability table (`docs/traceability.md`) is checked in CI.
- NFR-MAINT-005 (S) Dependency versions pinned (uv lockfile); Pyodide upgrade procedure documented.

### 5.7 Legal and licensing
- NFR-LEG-001 (M) No TI marks, artwork, ROM content or screenshots shipped. Screenshots of TI software are never in the build: layout references (`docs/design/reference/nspire/`) and result evidence (`corpus/shots/` and `docs/testing/*-shots/`) are kept at those paths in the separate evidence repository (decision 0039), not in this one.
- NFR-LEG-002 (M) A visible disclaimer: not affiliated with or endorsed by TI; not an approved exam calculator.
- NFR-LEG-003 (M) CASSim is released under the MIT licence, copyright (c) 2026 Simon Tyler and CASSim contributors (decision 0042). Third-party notices (Flet, Pyodide, SymPy BSD, mpmath BSD, CodeMirror, Flutter and the vendored fonts) ship with the build.
- NFR-LEG-004 (S) Before porting LazyMath UDFs, record the licence check (LazyMath Unlicense) in `docs/decisions/`.
- NFR-LEG-005 (M) From M8, the disclaimer in NFR-LEG-002 also covers Casio and HP. No Casio or HP marks, artwork, ROM, firmware or emulator software is shipped; their screenshots are kept as in NFR-LEG-001 (`docs/design/reference/<device>/` for layout, `docs/testing/` for evidence), never in the build. The same holds for the scientific calculators that CASSim Scientific follows.
- NFR-LEG-006 (M for TI, C for Casio and HP) Before capturing a corpus from a manufacturer's emulator software, record its licence terms and why they allow this use in a decision record kept with the evidence (decision 0039). Must for TI because a corpus has already been captured from the TI-Nspire CX CAS Premium Teacher Software; the terms are recorded in decision 0029 (Q42), which is in the evidence repository: capture is by ordinary use, and screenshots of results are kept with the evidence, never in the build.
- NFR-LEG-007 (M) Corpus cases taken from VCAA material are marked `third_party: true` and keep their attribution in `source`. They hold the pseudocode listings and CASSim's own answers, never VCAA's question prose, and stay in the public repository (decision 0012, update 2026-11-12); if VCAA objects to any, those cases are removed. The corpus is never part of the app build.
- NFR-LEG-008 (M) Clean room. Device behaviour is learned only by observing the TI, Casio or HP software and handhelds in normal use (typing inputs, recording outputs and screenshots). No decompiling, disassembly, debugging, unpacking or patching of their binaries, and no inspection of their memory or network traffic. Data tables are never extracted from them. Reference material in `references/` is consulted, not copied (decision 0028).
- NFR-LEG-009 (M) All help, catalog and explanatory text in the app is original. Short functional labels (menu items, error names such as "Domain error") and command names may match the device; nothing is copied verbatim from `references/` (decision 0028). Checked before public release by an audit of the in-app strings against the Reference Guide.

---

## 6. External interfaces
- **User interface**: three display modes (4.9); own-branded skin; reference screenshots in `docs/design/reference/<device>/`.
- **Files**: Open and Save work on documents kept by name in the browser; files on disk are the native `.cassim.json` (versioned), through Import and Export (decision 0033). CSV and optionally xlsx come in and go out through Import and Export, which is the general home for foreign formats; `.tns` is deferred and, if built, goes there too (FR-DOC-006).
- **Browser APIs**: IndexedDB, Service Worker, Web Workers, Clipboard, File System / download, fullscreen, Web App Manifest.
- **Software**: Pyodide 314.0.7, SymPy 1.14, mpmath, Flet 1.0.x, and openpyxl for xlsx (SciPy and NumPy are not shipped; SciPy only checks the statistics in tests, decision 0031); the 2D editor is CASSim's own template editor drawn from Flet controls (decisions 0015, 0018, 0019); MathLive and MathQuill are not used.
- **Internal**: engine worker protocol (request/response/cancel/restore); device-model API consumed by Flet; scene format for graphs.

## 7. Data requirements
- Document JSON schema: document -> Problems -> Pages -> page state; variables with Value serialisation; settings; library definitions; schema version; migration chain.
- Corpus YAML case schema (`id`, `course`, `tags`, `steps`, `provenance`, `status`, `compare`) as in PLAN.md section 6.
- Retention: all data local to the browser; user can export and delete everything.

## 8. Verification and acceptance
- **Unit/property** (pytest, Hypothesis): lexer, parser round-trip, values, settings, catalog functions.
- **Golden corpus**: replayed through the engine; `python -m tools.replay` reports progress. Status flow: `pending` -> `pass` / `xfail(reason)` / `hand-verified`, with Simon's review.
- **Device-model tests**: key sequence -> screen/state.
- **Render snapshots** (Playwright): per mode at fixed viewport, tolerance-based diff.
- **E2E/PWA**: build, serve, load, evaluate, install, go offline.
- **Acceptance gates** map to milestone exits in PLAN.md section 8: M1 Tier 1 corpus passes (canonical), strict types on `core/`, matrix published; M2 install on a phone and run scripted exam-style flows; M3 the General Maths workflows pass and data-page timing is reported; M4 graph snapshots and performance measurements pass; M5 the Python and pseudocode golden programs pass in both languages and agree (FR-XLT-004), the trace tables for the reference bisection example match the author's vertical and horizontal tables, all golden programs round-trip under each built-in syntax preset (FR-SYN-007), and cancel and trust-prompt E2E pass; M8 the Nspire corpus replays unchanged after the profile refactor and the ClassPad Tier 1 corpus passes (canonical); M9 as M8 if a go is given.

## 9. Requirement traceability
Each FR maps to: milestone (above), corpus tags (e.g. `solve`, `tier1`), tests, and design component (SDD section). A script in `tools/` generates `docs/traceability.md` from the requirement IDs in this file and the markers in tests and corpus tags (NFR-MAINT-006).

---

## 10. Open questions
Q1-Q15 are answered and folded into the text above. Q16-Q41 were added on 2026-11-02 and 2026-11-04 with the later programming and profile scope (4.12); none blocks M0–M4 or the start of M5. Q42 was added on 2026-11-12 with decision 0028. New ones will be added as the design docs surface them.

| # | Question | Needed by |
|---|---|---|
| Q16 | ~~Which pseudocode dialect?~~ **Answered 2026-11-02:** the VCAA pseudocode as extended by the author's conventions document; specification in `docs/pseudocode/dialect.md`, numeric types and basic strings only. | done |
| Q17 | Which ClassPad model(s), and is the manufacturer's PC emulator the oracle? Do its licence terms allow corpus capture? | 8c |
| Q18 | The same for HP Prime (its PC emulator), plus the go/no-go criteria for M9. | 9a |
| Q19 | ClassPad interaction: reproduce stylus/touch operation (tap menus, soft keyboard), or approximate it with the key-driven device model? | 8f |
| Q20 | ~~State shared between profiles?~~ **Answered 2026-11-02:** completely separate environments. Each profile has its own documents, variables, files, settings and theme; nothing is shared or copied between profiles (FR-PROF-004). | done |
| Q21 | ~~Python environment contents~~ **Partly answered 2026-11-02:** import only the libraries that are needed; numpy and scipy are skipped unless something in M5 needs them (the engine's `src` imports neither today, so this also shrinks the download; measure in the 5a spike). **Graphing:** undecided; test the options in a spike first (Flet's own charts, the canvas used in spike 3, matplotlib as the heavy fallback), and prefer Flet's built-in plotting if it is good enough. Device-style modules such as `ti_system` and `ti_plotlib` are still open. | 5a |
| Q22 | Should Python and Pseudocode pages exist on the ClassPad and Prime profiles? Which real models have native Python (not checked), and how do scripts reach CAS variables there? | 8g |
| Q23 | ~~Code view: a mode or its own entry point?~~ **Answered 2026-11-04:** a mode inside the one app. **Revised 2026-11-13:** its own device, in the all-in-one app's switcher and also on its own site, with its own storage (FR-RUN-009, FR-PROF-008; PLAN.md section 15). | done |
| Q24 | ~~Number modes~~ **Answered 2026-11-02:** yes, the TI "Auto" rule is added as a third number mode (Approx / Auto / Exact; `dialect.md` section 8). Default in the standalone Code view stays Approx (as proposed; say if you want otherwise). | done |
| Q25 | ~~Real display~~ **Answered 2026-11-02:** Mathematica style, 6 significant digits by default, adjustable in the … menu; applies to reals only (integers and rationals print exactly) and to pseudocode output and traces; Python run by CPython prints natively. | done |
| Q26 | ~~`print a, b` output format~~ **Answered 2026-11-04:** items separated by one space, as every expected output in the corpus shows; `print(a, b)` is the same statement with optional parentheses, not a pair, so it prints the same. | done |
| Q27 | ~~`input x` typing~~ **Answered 2026-11-02:** infer. Anything that can be a number (including a fraction) is a number, otherwise a string; revisit after real usage. | done |
| Q28 | ~~Complex numbers~~ **Answered 2026-11-04:** `1+2i`, `1+2ⅈ` and `complex(1,2)` are all accepted (FR-PSE-011); Real/Complex is a setting in the … menu, Real by default (FR-SET-003). | done |
| Q29 | ~~Are `e` and `π` predefined?~~ **Answered 2026-11-04:** `π` and `pi` are always the constant; `e` is Euler's number only when the toggle of FR-SET-008 is on (default on from 2026-11-06). A name the program assigns always shadows either. | done |
| Q30 | ~~Settings bar contents~~ **Answered 2026-11-02:** the bar has Number mode and Angle; everything else sits behind a **…** menu. | done |
| Q31 | ~~Python to pseudocode scope~~ **Answered 2026-11-04:** the subset with a pseudocode form, as listed in FR-XLT-002; anything else is refused with the line and construct named (FR-XLT-003). | done |
| Q32 | ~~VCAA question text~~ **Answered 2026-11-02:** accepted for development; decision 0012 records VCAA's terms. **Revised 2026-11-12:** the cases are generic maths and algorithms with attribution and stay in the public repository (0012 update). | done |
| Q33 | ~~Per-iteration table as a third trace view~~ **Answered 2026-11-04:** a Could (FR-TRC-011), after the vertical and horizontal views. | done |
| Q34 | ~~Whole-valued reals~~ **Answered 2026-11-02:** copy Mathematica. A real with a whole value prints with a trailing point (`5.`), so reals and integers look different; integers and rationals never get one. Applies to the display only (FR-SET-006). | done |
| Q35 | ~~Syntax settings in shared programs~~ **Answered 2026-11-02:** yes. A shared program carries its non-default syntax settings; opening it asks first and never changes the viewer's own file (FR-SYN-009). | done |
| Q36 | ~~Does `print` end the line?~~ **Answered 2026-11-02:** yes by default, and changeable in the … menu (FR-SET-007) and the syntax file. The setting is all-or-nothing, so the book's linear-search example (two `print` statements shown as one line, split only to fit the page) is kept in the corpus as a single `print` (reviewed 2026-11-04); the two-print original was removed. | done |
| Q37 | ~~List index base~~ **Answered 2026-11-02:** 1-based by default (as the VCAA and the author's book), with a toggle in the … menu to switch to 0-based; the choice is saved with the program, and translation to Python adjusts indexing either way. | done |
| Q38 | ~~Match CPython's seeded random~~ **Answered 2026-11-02:** yes. The pseudocode runtime reproduces CPython's `random` module exactly for `seed(n)`, `rand()` and `randint(a, b)` (MT19937, same seeding and algorithms), so the author's seeded results can be golden tests. | done |
| Q39 | ~~Defaults for the run limits and the Euler toggle~~ **Answered 2026-11-04:** 10,000 loop iterations, recursion depth 100, `e` off (FR-SET-008, FR-SET-009). **Revised 2026-11-06:** 1,000 passes per loop, 20,000 trace steps, depth 100, `e` on. | done |
| Q40 | ~~How does the variable argument bind in the expression form?~~ **Answered 2026-11-04:** the name must match the variable the expression uses, `f(t)` evaluates the expression at `t`, assignments to the variable inside the function are local (FR-PSE-002). | done |
| Q41 | ~~Exact values in Auto and Exact modes~~ **Answered 2026-11-04, revised 2026-11-07:** first decided as not in the first release; Simon then made it a Should (FR-PSE-012), with the same Approx / Auto / Exact toggle as the CAS. | done |
| Q42 | ~~Licence terms of the Teacher Software used for corpus capture~~ **Answered 2026-11-12:** the TI-Nspire CX/CX CAS Software EULA (rev20231107), named by the installed 6.0.3.374; recorded in decision 0029 (kept in the evidence repository, decision 0039). Capture is by ordinary use; screenshots are kept with the evidence, not in the build. | done |

---

## Appendix A. Design-document set (`docs/design/`)
Seven of the sixteen are written (2026-11-26). Until the others are, their material is in the decisions named and in the code. `docs/design/README.md` lists the other files kept in `docs/design/`.

| Doc | Content | Status |
|---|---|---|
| `SDD-00-overview.md` | Architecture views, layering, dependency rules, data flow | Not written; PLAN.md section 3 |
| `SDD-01-engine.md` | Lexer/parser/AST, values, evaluator, scope, SymPy adapter, errors | Not written; decisions 0007 to 0010 |
| `SDD-02-worker-and-cancel.md` | Pyodide worker protocol, cancel/restore, loading | Written |
| `SDD-03-display-and-format.md` | Number display rules, layout tree, LaTeX rendering | Not written; decisions 0008, 0014 and 0035 |
| `SDD-04-device-model.md` | Key layers, menu tree, input editor, screen buffer | Written |
| `SDD-05-ui-flet.md` | Layout modes, renderer, keypad, themes, 2D editor integration | Written |
| `SDD-06-document-and-storage.md` | Schema, versioning, IndexedDB, import/export | Not written; decisions 0003 and 0033, SDD-04 "Saving and sharing" |
| `SDD-07-data-pages.md` | Spreadsheet, statistics, finance | Written |
| `SDD-08-graphing.md` | Scene format, sampling, analysis tools, performance | Not written; decisions 0004 and 0031 |
| `SDD-09-programming-and-python.md` | TI-Basic, sandbox model (decision 0040) | Not written (M6) |
| `SDD-10-pwa-and-build.md` | Build pipeline, vendoring, service worker, deploy | Written |
| `SDD-11-test-strategy.md` | Corpus, replay, device and E2E tests, CI | Not written; `docs/testing/TESTING.md` |
| `SDD-12-device-profiles.md` | Profile interface, shared vs per-profile layers, storage namespaces, lazy loading, refactor plan for the Nspire | Not written; decision 0032 and PLAN.md section 15 |
| `SDD-13-runtime-python-pseudocode.md` | `Interpreter` interface, Python worker and sandbox, pseudocode dialect and interpreter, translation, trace engine and tables, settings bar, configurable syntax file, page-type integration (the variable bridge is a later Could) | Not written; decisions 0020, 0021 and 0037, `docs/pseudocode/` |
| `SDD-14-scientific-calculator-fx.md` | CASSim Scientific: modes, natural display, exact values, statistics, tutorials, keypad and keyboard, files and links | Written |
| `SDD-15-shared-interface.md` | CASSim's own interface in every app: CASSim and Doc menus, themes and Appearance, toggles, update and install items, views and touch, dialogs and wording | Written |

---

## Appendix B. Implementation status (2026-11-18; CASSim Scientific row 2026-11-25)

A summary, not a substitute for the traceability table (`docs/traceability.md`, NFR-MAINT-006).

| Area | Requirements | Status |
|---|---|---|
| Language, evaluation, scope | 4.1 | Built (M1). |
| Command catalogue | 4.2 | Tier 1 built; Tier 2 per the matrix; FR-CAT-005 matrix published (`docs/command_matrix.md`). |
| Calculator page, device model | 4.3, 4.9 | Built through 2h; exam-style flows pass headless and in the browser (decision 0025). M2 exit remains open for primary-browser/device checks, non-US keyboard capture, Tablet mode and simulator follow-up. |
| Documents, files, share links | 4.4 | Built (IndexedDB autosave, `.cassim.json`, share links, Page Sorter and split pages). Named documents and save/open/import workflows are implemented; M2's external verification gates still apply. |
| PWA, offline, engine worker | 4.11, FR-EVAL-006 | Built and tested on Chromium; the Cloudflare Pages site passed a headless smoke test with an offline reload; Safari, iOS and Chromebook not yet run. |
| Device interface and bundles | FR-PROF-001/002/008/009 | Complete through M2x; the Nspire package boundary, registered page types and bundle-aware publishing are implemented. |
| Lists & Spreadsheet, Data & Statistics, Finance page | 4.5, 4.6, FR-DOC-008, FR-DOC-009 | Mostly met (M3): sheet and data page models/UI, categorical and numeric plots, inference, split panes, Quick Graph/Summary Plot, CSV/XLSX, and the Finance Solver are built. Remaining exit work is General Maths flows, timing reports and simulator checks of selected defaults/save-reload behaviour. |
| Graphs, Table and Notes | 4.7, 4.7a | M4 is in progress: the function Graphs page now has worker compilation, adaptive plotting, one-row expression navigation, curve labels, view controls and save/load. Trace/Analyze UI, other entry types, Table/sliders and Notes remain. |
| Pseudocode runtime and Code view | 4.12 (FR-RUN-005/006/009, FR-PSE, FR-TRC, FR-SYN-001 to 009) | Built ahead of schedule as M5b; 58 golden programs are green. The standalone device now has editor and file workflows, responsive and resizable panes, Symbols and scrolling/resizable trace tables, settings, typing/display controls, supported-subset Python/Pseudocode translation, examples and console/trace polish. Direct CPython execution and Nspire Code page types remain incomplete. |
| Python runtime | FR-RUN-002/003 | Not started; the sandbox spike in 5a comes first. |
| TI-Basic, libraries | 4.8 | Not started (M6, Could). |
| CASSim Scientific scientific calculator | FR-FX (4.12) | Built in `devices/scientific` (COMP, STAT with all eight types, TABLE, VERIFY, natural display, exact answers, tutorials, keyboard, files and links); CMPLX/VECTOR, multi-statements and a Playwright test remain; no behaviour has been compared with a physical calculator (SDD-14 section 8). |
| Multi-app shell, ClassPad, HP Prime | FR-PROF, FR-CPD, FR-HPP | Home, device switching, bundle-specific device lists and the Nspire/Pseudocode device boundary are built. Per-device lazy caching is follow-up; ClassPad remains M8 and HP Prime M9. |
| Non-functional | 5 | Traceability, accessibility notes and per-package coverage floors exist. Primary-browser matrix gaps and the M7 release audits remain open. |
